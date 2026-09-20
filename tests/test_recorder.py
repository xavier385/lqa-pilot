"""Recorder lifecycle checks with no Android process or encoder invocation."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from lqa_pilot.util import PilotError, read_json
from lqa_pilot.video import CaseRecorder


class RecorderTests(unittest.TestCase):
    def recorder(self, root):
        with patch("lqa_pilot.video.executable", return_value="fake-ffmpeg"):
            return CaseRecorder(Mock(),root,"CASE",{"width":2160,"height":3840})

    def test_only_owned_recorder_pid_can_be_signalled(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = self.recorder(Path(tmp))
            r.proc = Mock(); r.proc.poll.return_value = None
            r.remote_pid, r.remote = 123, "/sdcard/lqa-own.mp4"
            r.driver.adb.return_value = b"screenrecord\x00/sdcard/someone-else.mp4"
            r._signal()
            self.assertEqual(r.driver.adb.call_count, 1)
            r.driver.adb.return_value = b"screenrecord\x00/sdcard/lqa-own.mp4"
            r._signal()
            self.assertEqual(r.driver.adb.call_args.args, ("shell","kill","-2","123"))

    def test_no_game_action_when_recording_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = self.recorder(Path(tmp)); op = Mock()
            r.ready.set(); r.proc = Mock(); r.proc.poll.return_value = 1
            with self.assertRaises(PilotError):
                r.perform(op)
            op.assert_not_called()

    def test_partial_and_resume_preserve_manifest_and_one_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); r = self.recorder(root)
            r.target.write_bytes(b"previous clip fixture"*100)
            segment = r.parts/"0001.mp4"; segment.write_bytes(b"new clip fixture"*100)
            r.segments = [{"path":str(segment)}]
            r.error = "Recording ended before coverage completed"
            def fake_concat(args, **kwargs):
                self.assertIn("copy", args)
                Path(args[-1]).write_bytes(b"merged clip fixture"*150)
            with patch("lqa_pilot.video.process", side_effect=fake_concat):
                info = r.stop()
            self.assertTrue(info["partial"])
            self.assertEqual(read_json(r.target.with_suffix(".json")), info)
            self.assertTrue(info["resumed_previous_video"])
            self.assertEqual(len((r.parts/"concat.txt").read_text().splitlines()), 2)
            self.assertEqual(info["path"], "videos/CASE.mp4")
            self.assertEqual(info["size"], [1080,1920])
