import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,Mock

from lqa_pilot.android import Android
from lqa_pilot.diagnostics import DiagnosticLog,usage_totals,redact
from lqa_pilot.web_bridge import Jobs,Companion
from lqa_pilot.util import PilotError,write_json


class DiagnosticsTests(unittest.TestCase):
    def test_diagnostics_http_requires_paired_origin_and_bearer(self):
        import http.client
        with tempfile.TemporaryDirectory() as t:
            companion=Companion(t,'https://qa.example.com',port=0);companion.start()
            client=http.client.HTTPConnection('127.0.0.1',companion.port)
            try:
                client.request('GET','/diagnostics',headers={'Origin':'https://qa.example.com'})
                response=client.getresponse();self.assertEqual(response.status,401);response.read()
                token=companion.pair('https://qa.example.com',companion.code)
                client.request('GET','/diagnostics',headers={'Origin':'https://qa.example.com','Authorization':'Bearer '+token})
                response=client.getresponse();self.assertEqual(response.status,200)
                body=json.loads(response.read());self.assertIn('companion.started',body['log']);self.assertNotIn(token,body['log'])
            finally:client.close();companion.server.shutdown();companion.server.server_close()

    def driver(self,config=None):
        with patch('lqa_pilot.android.executable',return_value='C:/fixture/nx_main/adb.exe'):
            self.trace=Mock();return Android(config or {},diagnostics=self.trace)

    def test_empty_devices_has_actionable_message_and_logs_search(self):
        d=self.driver();d.adb=Mock(return_value=b'List of devices attached\n')
        with patch.object(Path,'glob',return_value=iter([])):
            with self.assertRaisesRegex(PilotError,'Nessun dispositivo Android'):d.connect()
        events=[call.args[0] for call in self.trace.call_args_list]
        self.assertIn('mumu.config.search',events);self.assertIn('adb.no_device',events)

    def test_unauthorized_and_offline_are_distinct(self):
        for state,expected in [('unauthorized','non autorizzato'),('offline','offline')]:
            d=self.driver();d.adb=Mock(return_value=f'List of devices attached\n127.0.0.1:12345 {state}\n'.encode())
            with patch.object(Path,'glob',return_value=iter([])):
                with self.assertRaisesRegex(PilotError,expected): d.connect()

    def test_manual_endpoint_connects_even_with_another_existing_device(self):
        d=self.driver({'endpoint':'127.0.0.1:23456'})
        d.adb=Mock(side_effect=[b'phone device\n',b'connected to 127.0.0.1:23456',b'phone device\n127.0.0.1:23456 device\n'])
        self.assertEqual(d.connect(),'127.0.0.1:23456')
        d.adb.assert_any_call('connect','127.0.0.1:23456',device=False)

    def test_remote_or_invalid_endpoint_is_rejected(self):
        for endpoint in ['192.168.1.2:5555','127.0.0.1:99999']:
            d=self.driver({'endpoint':endpoint});d.adb=Mock(return_value=b'')
            with self.assertRaises(PilotError):d.connect()
            self.assertEqual(d.adb.call_count,1)

    def test_bad_vm_config_does_not_hide_other_configs(self):
        with tempfile.TemporaryDirectory() as t:
            bad=Path(t)/'bad.json';bad.write_text('{bad')
            good=Path(t)/'good.json';write_json(good,{'adb.host_port':23456})
            d=self.driver();d.adb=Mock(side_effect=[b'',b'connected',b'127.0.0.1:23456 device\n'])
            with patch.object(Path,'glob',return_value=[bad,good]),patch('socket.create_connection'):
                self.assertEqual(d.connect(),'127.0.0.1:23456')
            self.assertIn('mumu.config.error',[c.args[0] for c in self.trace.call_args_list])

    def test_log_is_bounded_and_redacts_secrets_and_user_path(self):
        with tempfile.TemporaryDirectory() as t:
            log=DiagnosticLog(t)
            log.write('failure',message='Bearer secret api_key=sk-private '+str(Path.home()))
            self.assertNotIn('secret',log.read());self.assertNotIn('sk-private',log.read())
            self.assertNotIn(str(Path.home()),log.read())
            log.path.write_text('x'*(513*1024));log.write('rotated')
            self.assertLess(len(log.read()),1000);self.assertTrue(log.path.with_suffix('.previous.log').exists())

    def test_token_totals_include_import_and_testing_without_double_counting_cache(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            write_json(root/'project/planning/a.meta.json',{'usage':{'input_tokens':100,'cached_input_tokens':60,'output_tokens':20}})
            write_json(root/'run/model/b.meta.json',{'usage':{'input_tokens':200,'cached_input_tokens':120,'output_tokens':30}})
            write_json(root/'run/model/failed.meta.json',{'usage':{}})
            result=usage_totals(root,attempted=4)
            self.assertEqual(result['total_tokens'],350);self.assertEqual(result['cached_input_tokens'],180)
            self.assertEqual(result['reported_calls'],2);self.assertEqual(result['unreported_calls'],2)
            self.assertEqual(result['groups']['planning']['output_tokens'],20)

    def test_partial_metrics_are_not_reported_as_known_zero(self):
        with tempfile.TemporaryDirectory() as t:
            write_json(Path(t)/'run/model/a.meta.json',{'usage':{'input_tokens':False,'output_tokens':-1}})
            result=usage_totals(t,attempted=1)
            self.assertEqual(result['reported_calls'],0);self.assertEqual(result['unreported_calls'],1)

    def test_import_error_still_exposes_usage_after_restart(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            write_json(root/'latest.json',{'id':'demo','status':'error','downloads':[]})
            write_json(root/'demo/project/planning-progress.json',{'calls':2})
            write_json(root/'demo/project/planning/a.meta.json',{'usage':{'input_tokens':10,'output_tokens':5}})
            public=Jobs(root).public()
            self.assertEqual(public['usage']['total_tokens'],15);self.assertEqual(public['usage']['unreported_calls'],1)

    def test_detect_retains_selected_serial_for_the_real_job_without_a_model_call(self):
        with tempfile.TemporaryDirectory() as t,patch('lqa_pilot.android.Android') as android,patch('lqa_pilot.codex.Codex') as codex:
            android.return_value.serial='127.0.0.1:23456';android.return_value.foreground.return_value='com.demo.game'
            codex.return_value.check_auth.return_value='ChatGPT'
            companion=Companion(t)
            companion.detect({'port':'23456','serial':''})
            self.assertEqual(companion.device_config,{'serial':'127.0.0.1:23456','endpoint':'127.0.0.1:23456'})
            codex.return_value.ask.assert_not_called()
