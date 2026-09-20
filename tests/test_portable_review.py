import copy
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageChops

from lqa_pilot.codex import Codex
from lqa_pilot.excel_report import annotate, build_payload
from lqa_pilot.portable import pack_project
from lqa_pilot.project import load_project
from lqa_pilot.recheck import selected_cases
from lqa_pilot.util import PilotError, digest, read_json, write_json


class AnnotationTests(unittest.TestCase):
    def test_full_screen_preserves_every_text_pixel(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp)/"source.png", Path(tmp)/"annotated.png"
            im = Image.new("RGB", (800, 1400), "#DDEECC")
            im.save(a)
            info = annotate(a, b, {"x": .15, "y": .35, "width": .55, "height": .15})
            with Image.open(b) as marked:
                self.assertEqual(marked.size, im.size)
                box = tuple(info["text_box_pixels"])
                self.assertIsNone(ImageChops.difference(im.crop(box), marked.crop(box)).getbbox())
                self.assertIsNotNone(ImageChops.difference(im, marked).getbbox())
                self.assertIn((255, 0, 0), [color for _, color in marked.getcolors()])

    def test_edge_text_is_never_overpainted(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp)/"source.png", Path(tmp)/"annotated.png"
            Image.new("RGB", (100, 100), "white").save(a)
            info = annotate(a, b, {"x": 0, "y": 0, "width": .5, "height": .5})
            with Image.open(b) as im:
                self.assertEqual(im.crop(tuple(info["text_box_pixels"])).getcolors(), [(2500, (255,255,255))])


class PortableTests(unittest.TestCase):
    def test_recheck_uses_pinned_references_after_move(self):
        import shutil
        from lqa_pilot.engine import Engine
        from lqa_pilot.demo import DemoAndroid, DemoModel
        from lqa_pilot.recheck import prepare_recheck
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = root/"original.png"
            Image.new("RGB", (40,40), "red").save(reference)
            p = read_json(Path(__file__).parents[1]/"examples/project-template.json")
            p["reference_images"] = [str(reference)]
            p["reference_images_all"] = [str(reference)]
            p["device"]["adb"] = "C:/OldOperator/adb.exe"
            p["codex"] = {"executable":"C:/OldOperator/codex.exe"}
            write_json(root/"project.json", p)
            engine = Engine(load_project(root/"project.json"), root/"run", driver=DemoAndroid(), model=DemoModel())
            shutil.copytree(root/"run", root/"moved")
            reference.unlink()
            workbook = root/"selection.xlsx"; workbook.write_bytes(b"review fixture")
            cid = p["cases"][0]["id"]
            with patch("lqa_pilot.recheck.selected_cases", return_value={cid:[]}):
                target = prepare_recheck(workbook, root/"moved", root/"recheck")
            loaded = load_project(target)
            self.assertTrue(Path(loaded["reference_images"][0]).is_file())
            self.assertTrue(Path(loaded["reference_images"][0]).is_relative_to(root/"moved"))
            self.assertNotIn("adb", loaded["device"])
            self.assertNotIn("executable", loaded["codex"])

    def test_pack_relocates_references_and_drops_machine_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/"source"; source.mkdir()
            p = read_json(Path(__file__).parents[1]/"examples/project-template.json")
            p["device"]["adb"] = "C:/OtherUser/adb.exe"
            p["device"]["endpoint"] = "127.0.0.1:16384"
            p["codex"] = {"executable": "C:/OtherUser/codex.exe"}
            Image.new("RGB", (50,50)).save(source/"reference.png")
            p["reference_images"] = [str(source/"reference.png")]
            p["materials"] = [{"path": "reference.png", "purpose": "journey"}]
            write_json(source/"project.json", p)
            archive = pack_project(source/"project.json", root/"project.zip")
            with zipfile.ZipFile(archive) as z:
                self.assertFalse(any("auth" in n or "venv" in n for n in z.namelist()))
                z.extractall(root/"other-machine")
            relocated = root/"other-machine/project.json"
            self.assertNotIn("OtherUser", relocated.read_text(encoding="utf-8"))
            loaded = load_project(relocated)
            self.assertTrue(all(Path(v).is_file() for v in loaded["reference_images"]))
            self.assertEqual(loaded["device"]["serial"], "auto")
            self.assertNotIn("endpoint", loaded["device"])

    def test_credentials_are_never_packaged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(root/"auth.json", {"fake": "credentials"})
            write_json(root/"project.json", {"materials": ["auth.json"]})
            with self.assertRaises(PilotError):
                pack_project(root/"project.json", root/"bad.zip")

    def test_auth_uses_current_operator_without_api_keys(self):
        model = object.__new__(Codex)
        with patch.dict("os.environ", {"CODEX_HOME": "C:/Colleague/codex-profile", "OPENAI_API_KEY": "fake", "CODEX_API_KEY": "fake"}):
            env = model.environment()
        self.assertEqual(env["CODEX_HOME"], "C:/Colleague/codex-profile")
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn("CODEX_API_KEY", env)


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.run = {"project": {"name":"Demo", "language":"German", "cases":[{"id":"A"},{"id":"B"}]}, "started_at":"2026-09-18", "project_hash":"HASH",
                    "cases":{"A":{"findings":[{"id":"BUG-A"}]},"B":{"findings":[]}}}
        self.label = {"A":"Run ID: "+digest(["HASH","2026-09-18"])[:24]}
        self.results = [(4,self.label),(5,{"A":"Case ID","D":"Revisione","E":"Note revisore"}),(6,{"A":"A","D":"Ricontrollare","E":"Rileggere frase"}),(7,{"A":"B","D":"Confermato"})]
        self.bugs = [(4,self.label),(5,{"A":"Bug ID","B":"Case ID","K":"Revisione","L":"Note revisore","M":"Origine"})]

    def rows(self, file, name):
        return self.results if name == "Risultati" else self.bugs

    def test_only_explicit_selection_is_retested(self):
        with patch("lqa_pilot.recheck.xlsx_rows", side_effect=self.rows):
            chosen = selected_cases("irrelevant.xlsx", self.run)
        self.assertEqual(set(chosen), {"A"})
        self.assertEqual(chosen["A"][0]["reviewer_note"], "Rileggere frase")

    def test_wrong_run_rejected(self):
        self.run["started_at"] = "different"
        with patch("lqa_pilot.recheck.xlsx_rows", side_effect=self.rows), self.assertRaises(PilotError):
            selected_cases("irrelevant.xlsx", self.run)

    def test_simulated_bug_cannot_enter_real_recheck(self):
        self.bugs.append((6,{"A":"BUG-A","B":"A","K":"Ricontrollare","M":"SIMULATO — demo"}))
        with patch("lqa_pilot.recheck.xlsx_rows", side_effect=self.rows), self.assertRaises(PilotError):
            selected_cases("irrelevant.xlsx", self.run)

    def test_unknown_case_rejected(self):
        self.results[2][1]["A"] = "invented"
        with patch("lqa_pilot.recheck.xlsx_rows", side_effect=self.rows), self.assertRaises(PilotError):
            selected_cases("irrelevant.xlsx", self.run)

    def test_pass_has_no_comment_or_screenshot(self):
        cases = [{"spec":{"id":"A","title":"Menu"},"result":{"status":"PASS","coverage":"complete","audit":{"explanation":"Internal only"}}}]
        payload = build_payload(Path.cwd(), self.run, cases, [], ["Client"], [])
        self.assertEqual(len(payload["sheets"]), 1)
        row = [""] * 18
        row[1], row[2], row[15] = "Menu", "A", "Pass"
        self.assertEqual(payload["sheets"][0]["rows"], [row])
        self.assertEqual(payload["sheets"][0]["images"], [])

    def test_reassessment_never_moves_game_and_keeps_original_dates(self):
        from lqa_pilot.demo import demo, DemoModel, DemoAndroid
        from lqa_pilot.reassess import reassess
        with tempfile.TemporaryDirectory() as tmp, patch("lqa_pilot.engine.Path.home", return_value=Path(tmp)):
            root = Path(tmp)
            demo(root/"original")
            source = read_json(root/"original/run.json")
            route = DemoAndroid().capture(root/"original/evidence/route-home.png")
            route["case_id"] = "DEMO-PASS"
            route["path"] = "evidence/route-home.png"
            source["evidence"][route["id"]] = route
            source["cases"]["DEMO-PASS"]["steps"].append({"evidence_id": route["id"], "screen_name": "Home after reading"})
            write_json(root/"original/run.json", source)
            state = reassess(source["project"], root/"original", root/"reassessed", model=DemoModel())
            self.assertEqual(state["actions"], 0)
            self.assertEqual(state["mode"], "evidence_only_reassessment")
            self.assertEqual({k:v["status"] for k,v in state["cases"].items()}, {"DEMO-PASS":"PASS","DEMO-BUG":"BUG","DEMO-BLOCKED":"INCOMPLETE"})
            final_step = state["cases"]["DEMO-PASS"]["steps"][-1]
            self.assertEqual(state["evidence"][final_step["evidence_id"]]["source_evidence_id"], "route-home")
            for e in state["evidence"].values():
                self.assertEqual(e["captured_at"], source["evidence"][e["source_evidence_id"]]["captured_at"])

    def test_reassessment_recovers_real_confirmation_when_one_id_referenced(self):
        from lqa_pilot.reassess import evidence_pairs
        evidence = {"A-0001-screen":{"case_id":"A"},"A-0002-confirmation":{"case_id":"A"}}
        self.assertEqual(evidence_pairs(["A-0001-screen"], evidence, "A"), tuple(evidence))

    def test_reassessment_cannot_duplicate_or_borrow_confirmation(self):
        from lqa_pilot.reassess import evidence_pairs
        evidence = {"A-0001-screen":{"case_id":"A"},"B-0002-confirmation":{"case_id":"B"}}
        self.assertEqual(evidence_pairs(["A-0001-screen"], evidence, "A"), ())


if __name__ == "__main__":
    unittest.main()
