"""Offline checks: fake Android, fake model, fake recorder. No GPT/ADB calls."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lqa_pilot.demo import DemoAndroid, DemoModel
from lqa_pilot.engine import Engine
from lqa_pilot.modes import apply_mode, fast_allowed
from lqa_pilot.project import load_project
from lqa_pilot.report import export
from lqa_pilot.util import PilotError, read_json, write_json


def project(root, mode):
    source = {"name":"Offline mode fixture", "language":"English", "device":{"package":DemoAndroid.package},
              "mode":mode, "cases":[{"id":"DEMO-BUG", "title":"Fixture", "objective":"Display the settings panel",
              "journey":["Open settings"], "checks":[{"id":"BUG-C", "scope":"Settings panel", "instruction":"Read labels", "modality":"visual"}]}]}
    write_json(root/"project.json", source)
    return load_project(root/"project.json")


class FastModel(DemoModel):
    def __init__(self, variant="typo", eligible=True):
        self.variant, self.eligible, self.roles = variant, eligible, []

    def ask(self, role, prompt, schema, images=()):
        self.roles.append(role)
        result = super().ask(role, prompt, schema, images)
        if role == "analyze":
            candidate = result["candidates"][0]
            candidate.update(fast_kind=self.variant, meaning_impact=False, glossary_key="")
            if self.variant == "minor_style":
                candidate.update(observed="Version:1", expected="Version: 1")
        if role == "verify":
            result["fast_eligible"] = self.eligible
        return result


class FakeRecorder:
    def __init__(self, driver, folder, case_id, frame, config):
        self.folder, self.case_id = Path(folder), case_id

    def start(self):
        pass

    def stop(self):
        # Path is an explicit fixture, never presented as real video evidence.
        return {"path":f"videos/{self.case_id}.mp4", "fixture_only":True}

    def perform(self, operation):
        return operation()


class VideoModel(DemoModel):
    def __init__(self):
        self.roles = []

    def ask(self, role, prompt, schema, images=()):
        self.roles.append(role)
        if role in {"analyze", "verify"}:
            raise AssertionError("Video mode must not analyze LQA")
        return super().ask(role, prompt, schema, images)


class ModeTests(unittest.TestCase):
    def test_effort_and_navigator_are_selected_without_mutating_project(self):
        original = {"report_language":"Italiano"}
        full, fast, video = [apply_mode(original, m) for m in ("full","fast","video")]
        self.assertNotIn("mode", original)
        self.assertEqual(full["report_language"], "English")
        for p in (fast,video):
            self.assertEqual(p["codex"]["models"]["navigate"], full["codex"]["models"]["navigate"])
        self.assertEqual([fast["codex"]["models"][r]["reasoning"] for r in ("analyze","verify","audit")], ["low"]*3)
        self.assertEqual(video["codex"]["models"]["audit"]["reasoning"], "low")
        with self.assertRaises(PilotError):
            apply_mode({}, "unknown")

    def test_fast_scope_excludes_style_and_ungrounded_inconsistency(self):
        c = {"fast_kind":"typo", "observed":"Allianzmitglieder Versammlungshinweis", "expected":"Allianzmitglieder-Versammlungshinweis"}
        self.assertFalse(fast_allowed(c, {}))
        self.assertTrue(fast_allowed({**c, "observed":"Notifictions", "expected":"Notifications"}, {}))
        self.assertTrue(fast_allowed({**c, "fast_kind":"ui_layout"}, {}))
        self.assertFalse(fast_allowed({**c, "fast_kind":"glossary", "glossary_key":"army"}, {}))
        self.assertTrue(fast_allowed({**c, "fast_kind":"glossary", "glossary_key":"army"}, {"glossary":{"army":"Armee"}}))
        for kind in ("nonsense","meaning_grammar","reputation"):
            changed = {**c, "observed":"Meaning", "expected":"Different meaning", "fast_kind":kind}
            self.assertFalse(fast_allowed({**changed, "meaning_impact":False}, {}))
            self.assertTrue(fast_allowed({**changed, "meaning_impact":True}, {}))

    def run_fast(self, model):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("lqa_pilot.engine.Path.home", return_value=root):
                result = Engine(project(root,"fast"), root/"run", driver=DemoAndroid(), model=model).run(launch=False)
            return result["cases"]["DEMO-BUG"]

    def test_fast_only_style_is_clear_after_coverage_audit(self):
        model = FastModel("minor_style")
        result = self.run_fast(model)
        self.assertEqual(result["status"], "PASS")
        self.assertNotIn("verify", model.roles)
        self.assertEqual(len(result["excluded_by_mode"]), 1)

    def test_fast_confirmed_typo_is_bug(self):
        self.assertEqual(self.run_fast(FastModel())["status"], "BUG")

    def test_fast_verifier_excluded_candidate_does_not_block_pass(self):
        self.assertEqual(self.run_fast(FastModel(eligible=False))["status"], "PASS")

    def test_fast_uncertain_in_scope_bug_never_passes(self):
        class Uncertain(FastModel):
            def ask(self, role, *args, **kwargs):
                r = super().ask(role, *args, **kwargs)
                if role == "verify":
                    r["verdict"] = "uncertain"
                return r
        self.assertEqual(self.run_fast(Uncertain())["status"], "INCOMPLETE")

    def test_video_has_one_output_per_case_no_analysis_or_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = project(root,"video")
            second = copy.deepcopy(p["cases"][0]); second["id"] = "DEMO-BUG-SECOND"
            p["cases"].append(second)
            model = VideoModel()
            with patch("lqa_pilot.engine.Path.home", return_value=root), patch("lqa_pilot.video.CaseRecorder", FakeRecorder):
                state = Engine(p,root/"run",driver=DemoAndroid(),model=model).run(launch=False)
            self.assertEqual({c["status"] for c in state["cases"].values()}, {"RECORDED"})
            self.assertEqual(model.roles, ["navigate","audit"]*2)
            manifest = read_json(export(root/"run"))
            self.assertFalse(manifest["lqa_performed"])
            self.assertEqual(len({c["video"]["path"] for c in manifest["cases"]}), 2)
            self.assertFalse((root/"run/report.xlsx").exists())

    def test_video_partial_recording_is_incomplete_even_after_successful_journey(self):
        class Partial(FakeRecorder):
            def stop(self):
                return {**super().stop(), "partial":True, "error":"Encoder stopped"}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("lqa_pilot.engine.Path.home", return_value=root), patch("lqa_pilot.video.CaseRecorder", Partial):
                state = Engine(project(root,"video"),root/"run",driver=DemoAndroid(),model=VideoModel()).run(launch=False)
            self.assertEqual(state["cases"]["DEMO-BUG"]["status"], "INCOMPLETE")

    def test_recorder_failure_prevents_navigation(self):
        class Failed(FakeRecorder):
            def start(self):
                raise PilotError("Unsupported encoder")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); model = VideoModel()
            with patch("lqa_pilot.engine.Path.home", return_value=root), patch("lqa_pilot.video.CaseRecorder", Failed):
                state = Engine(project(root,"video"),root/"run",driver=DemoAndroid(),model=model).run(launch=False)
            self.assertEqual(model.roles, [])
            self.assertEqual(state["cases"]["DEMO-BUG"]["status"], "INCOMPLETE")
