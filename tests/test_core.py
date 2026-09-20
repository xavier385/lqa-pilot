import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from lqa_pilot.android import Android, validate_action
from lqa_pilot.demo import action, demo
from lqa_pilot.engine import Engine, final_status
from lqa_pilot.project import load_project
from lqa_pilot.report import BUG_HEADERS, cell, tsv
from lqa_pilot.schema import NAV, obj, validate, N
from lqa_pilot.util import PilotError, read_json, write_json


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.case = {"checks": [{"id": "A"}, {"id": "B"}]}
        self.result = {"checks": {k: {"status": "clear", "evidence_ids": ["E"]} for k in ("A", "B")},
                       "audit": {"scope_complete": True, "missing_areas": [], "checks": [{"check_id": k, "covered": True} for k in ("A", "B")]}, "findings": []}

    def test_full_coverage_pass(self):
        self.assertEqual(final_status(self.case, self.result), ("PASS", "complete"))

    def test_missing_check_not_pass(self):
        del self.result["checks"]["B"]
        self.assertEqual(final_status(self.case, self.result)[0], "INCOMPLETE")

    def test_no_evidence_not_pass(self):
        self.result["checks"]["A"]["evidence_ids"] = []
        self.assertEqual(final_status(self.case, self.result)[0], "INCOMPLETE")

    def test_navigator_finish_without_audit_not_pass(self):
        del self.result["audit"]
        self.result["action"] = {"kind": "finish"}
        self.assertEqual(final_status(self.case, self.result)[0], "INCOMPLETE")

    def test_missing_submenu_not_pass(self):
        self.result["audit"]["missing_areas"] = ["second tab"]
        self.assertEqual(final_status(self.case, self.result)[0], "INCOMPLETE")

    def test_blocker_prevents_pass(self):
        self.result["blocker"] = "budget exhausted"
        self.assertEqual(final_status(self.case, self.result)[0], "INCOMPLETE")

    def test_uncertain_candidate_never_pass(self):
        self.result["findings"] = [{"verification": {"verdict": "uncertain"}}]
        self.assertEqual(final_status(self.case, self.result)[0], "INCOMPLETE")

    def test_confirmed_bug_with_partial_scope(self):
        self.result["findings"] = [{"check_id": "A", "verification": {"verdict": "confirmed"}}]
        self.result["audit"]["scope_complete"] = False
        self.assertEqual(final_status(self.case, self.result), ("BUG", "partial"))

    def test_unsupported_audio_is_incomplete(self):
        self.result["checks"]["A"]["status"] = "not_observed"
        self.assertEqual(final_status(self.case, self.result)[0], "INCOMPLETE")


class ActionTests(unittest.TestCase):
    def test_foreground_change_prevents_input(self):
        driver = object.__new__(Android)
        driver.package = "com.game"
        driver.capture = Mock(return_value={"package": "com.other"})
        driver.adb = Mock()
        self.assertEqual(driver.act(action("tap"), {}, "unused")["reason"], "foreground_changed")
        driver.adb.assert_not_called()

    def test_stale_target_prevents_input(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            before, after = Path(tmp) / "before.png", Path(tmp) / "after.png"
            Image.new("RGB", (100, 100), "black").save(before)
            Image.new("RGB", (100, 100), "white").save(after)
            driver = object.__new__(Android)
            driver.package, driver.config = "com.game", {}
            e = {"width": 100, "height": 100, "package": "com.game", "path": str(before)}
            driver.capture = Mock(return_value={**e, "path": str(after)})
            driver.adb = Mock()
            self.assertEqual(driver.act(action("tap", x=.5, y=.5), e, "unused")["reason"], "target_changed")
            driver.adb.assert_not_called()

    def test_out_of_bounds(self):
        with self.assertRaises(PilotError):
            validate_action(action("tap", x=1.01))

    def test_animated_overlay_retries_until_target_matches(self):
        driver = object.__new__(Android)
        driver.package, driver.config = "com.game", {"settle_seconds": 0}
        e = {"width": 100, "height": 100, "package": "com.game", "path": "original", "id": "guard"}
        driver.capture, driver.adb = Mock(return_value=e), Mock()
        with patch("lqa_pilot.android.visual_distance", side_effect=[.4, .3, .02]), patch("lqa_pilot.android.time.sleep"):
            self.assertTrue(driver.act(action("tap", x=.5, y=.5), e, "guard.png")["executed"])
        self.assertEqual(driver.capture.call_count, 3)
        driver.adb.assert_called_once_with("shell", "input", "tap", "50", "50")

    def test_animation_retry_rechecks_foreground(self):
        driver = object.__new__(Android)
        driver.package, driver.config = "com.game", {}
        e = {"width": 100, "height": 100, "package": "com.game", "path": "original"}
        driver.capture, driver.adb = Mock(side_effect=[e, {"package": "com.other"}]), Mock()
        with patch("lqa_pilot.android.visual_distance", return_value=.4), patch("lqa_pilot.android.time.sleep"):
            self.assertEqual(driver.act(action("tap", x=.5, y=.5), e, "guard.png")["reason"], "foreground_changed")
        driver.adb.assert_not_called()

    def test_nan(self):
        with self.assertRaises(PilotError):
            validate_action(action("tap", x=float("nan")))

    def test_spend_not_allowed(self):
        with self.assertRaises(PilotError):
            validate_action(action("tap", risk="spend"), True)

    def test_blocked_can_explain_forbidden_risk(self):
        validate_action(action("blocked", risk="spend"))

    def test_progress_requires_policy(self):
        with self.assertRaises(PilotError):
            validate_action(action("tap", risk="game_progress"))
        validate_action(action("tap", risk="game_progress"), True)

    def test_optional_consents_blocked(self):
        with self.assertRaises(PilotError):
            validate_action(action("tap", target="Pulsante Agree to all"))

    def test_no_arbitrary_shell_action(self):
        with self.assertRaises(PilotError):
            validate_action(action("shell"))

    def test_unicode_not_silently_dropped(self):
        a = action("type_text")
        a["text"] = "Città"
        with self.assertRaises(PilotError):
            validate_action(a)

    def test_package_injection_blocked(self):
        with self.assertRaises(PilotError):
            Android({"package": "com.game;rm -rf /", "adb": __file__})


class SchemaTests(unittest.TestCase):
    def test_review_comment_length_is_enforced(self):
        with self.assertRaises(PilotError):
            validate("x" * 401, {"type": "string", "maxLength": 400})

    def test_extra_fields_rejected(self):
        with self.assertRaises(PilotError):
            validate({"n": 1, "shell": "x"}, obj(n=N))

    def test_boolean_not_coordinate(self):
        with self.assertRaises(PilotError):
            validate({"n": True}, obj(n=N))


class ReportTests(unittest.TestCase):
    def test_client_columns_exact_count(self):
        self.assertEqual(len(BUG_HEADERS), 18)

    def test_formula_injection(self):
        for value in ("=HYPERLINK(x)", " @SUM(A1)", "+cmd", "-2"):
            self.assertTrue(cell(value).startswith("'"))

    def test_tsv_tabs_and_newlines(self):
        value = tsv(["a", "b"], [["hello\tworld", "line\n2"]], False)
        self.assertEqual(value.count("\t"), 1)
        self.assertEqual(value.count("\n"), 1)


class IntegrationTests(unittest.TestCase):
    def test_audit_receives_route_checkpoints_without_lqa_text(self):
        from lqa_pilot.demo import DemoAndroid, DemoModel
        with tempfile.TemporaryDirectory() as tmp:
            template = Path(__file__).resolve().parent.parent / "examples/project-template.json"
            p = load_project(template)
            case = p["cases"][0]
            e = Engine(p, Path(tmp)/"run", driver=DemoAndroid(), model=DemoModel())
            frames = [e.capture(case["id"]) for _ in range(3)]
            result = {"steps": [{"evidence_id": f["id"], "screen_name": name} for f,name in zip(frames,["Profile","Settings","Home"])],
                      "checks": {case["checks"][0]["id"]: {"evidence_ids": [frames[1]["id"]]}}, "findings": [], "transcriptions": []}
            answer = {"checks": [{"check_id": c["id"], "covered": True} for c in case["checks"]], "scope_complete": True, "missing_areas": [], "explanation": "Fixture"}
            with patch.object(e, "ask", return_value=answer) as ask:
                self.assertTrue(e.audit(case, result))
            images = ask.call_args.args[3]
            self.assertIn(frames[1]["path"], images)
            self.assertTrue(any(frames[0]["id"]+"-audit-nav" in f for f in images))
            self.assertTrue(any(frames[2]["id"]+"-audit-nav" in f for f in images))

    def test_interrupted_verification_can_resume_from_new_evidence(self):
        from lqa_pilot.demo import DemoAndroid, DemoModel
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            template = Path(__file__).resolve().parent.parent / "examples/project-template.json"
            p = load_project(template)
            case = {"id": "DEMO-BUG", "title": "Synthetic", "objective": "Read labels", "journey": [],
                    "checks": [{"id": "BUG-C", "scope": "Settings", "instruction": "Read all", "modality": "visual"}]}
            p["cases"] = [case]
            e = Engine(p, root/"run", driver=DemoAndroid(), model=DemoModel())
            result = {"title": "Synthetic", "steps": [{}], "screens": [], "checks": {}, "findings": [], "transcriptions": []}
            e.state["cases"][case["id"]] = result
            with patch.object(e, "verify", side_effect=PilotError("Stopped before verdict")), self.assertRaises(PilotError):
                e.analyze(case, result, e.capture(case["id"]), ["BUG-C"])
            self.assertEqual(result["findings"][0]["verification"]["verdict"], "uncertain")
            resumed = Engine(p, root/"run", driver=DemoAndroid(), model=DemoModel(), resume=True)
            result = resumed.state["cases"][case["id"]]
            fresh = resumed.capture(case["id"])
            resumed.analyze(case, result, fresh, ["BUG-C"])
            self.assertEqual(len(result["findings"]), 1)
            self.assertEqual(result["findings"][0]["verification"]["verdict"], "confirmed")
            self.assertEqual(result["findings"][0]["evidence_id"], fresh["id"])

    def test_disconnected_device_keeps_all_cases_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            from lqa_pilot.demo import DemoAndroid, DemoModel
            project = load_project(Path(__file__).resolve().parent.parent / "examples/project-template.json")
            device = DemoAndroid()
            device.connect = Mock(side_effect=PilotError("offline"))
            engine = Engine(project, Path(tmp) / "run", driver=device, model=DemoModel())
            state = engine.run()
            self.assertEqual(state["status"], "interrupted")
            self.assertTrue(all(c["status"] == "INCOMPLETE" for c in state["cases"].values()))

    def test_offline_three_outcomes_and_portable_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("lqa_pilot.engine.Path.home", return_value=Path(tmp)):
                report = demo(Path(tmp) / "demo")
            state = read_json(Path(tmp) / "demo/run.json")
            self.assertEqual({k: v["status"] for k, v in state["cases"].items()},
                             {"DEMO-PASS": "PASS", "DEMO-BUG": "BUG", "DEMO-BLOCKED": "INCOMPLETE"})
            self.assertTrue(report.is_file())
            bugs = (Path(tmp) / "demo/bugs_paste.tsv").read_text(encoding="utf-8-sig").splitlines()
            self.assertEqual(len(bugs), 1)
            self.assertEqual(len(bugs[0].split("\t")), 18)
            for evidence in state["evidence"].values():
                self.assertFalse(Path(evidence["path"]).is_absolute())
                self.assertTrue((Path(tmp) / "demo" / evidence["path"]).is_file())

    def test_budget_reservation_survives_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            from lqa_pilot.demo import DemoAndroid, DemoModel
            template = Path(__file__).resolve().parent.parent / "examples/project-template.json"
            project = load_project(template)
            project["budgets"]["max_calls"] = 1
            e = Engine(project, Path(tmp) / "run", driver=DemoAndroid(), model=DemoModel())
            e.reserve_call("navigate")
            e2 = Engine(project, Path(tmp) / "run", driver=DemoAndroid(), model=DemoModel(), resume=True)
            with self.assertRaises(PilotError):
                e2.reserve_call("navigate")

    def test_changed_scope_cannot_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            from lqa_pilot.demo import DemoAndroid, DemoModel
            template = Path(__file__).resolve().parent.parent / "examples/project-template.json"
            project = load_project(template)
            Engine(project, Path(tmp) / "run", driver=DemoAndroid(), model=DemoModel())
            project["cases"][0]["objective"] = "different scope"
            with self.assertRaises(PilotError):
                Engine(project, Path(tmp) / "run", driver=DemoAndroid(), model=DemoModel(), resume=True)


if __name__ == "__main__":
    unittest.main()
