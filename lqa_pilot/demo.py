"""Deterministic offline integration fixture. No claim of real-game or model validation."""
from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .engine import Engine
from .project import load_project
from .report import export
from .util import digest, now, read_json, write_json


def action(kind, target="", risk="navigation", x=0, y=0):
    return {"kind": kind, "x": x, "y": y, "x2": 0, "y2": 0, "duration_ms": 0, "text": "",
            "target": target, "expected_change": "Demo only", "risk": risk}


def make_fixture(path, typo=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (800, 1100), "#142538")
    d = ImageDraw.Draw(im)
    font_path = "C:/Windows/Fonts/arial.ttf"
    font = ImageFont.truetype(font_path, 32) if Path(font_path).exists() else ImageFont.load_default(size=32)
    small = ImageFont.truetype(font_path, 18) if Path(font_path).exists() else ImageFont.load_default(size=18)
    d.text((40, 30), "SYNTHETIC LQA TEST FIXTURE", fill="#8baccc", font=small)
    d.text((40, 140), "Settings", fill="white", font=font)
    for y, text in [(290, "Sound effects"), (420, "Music volume"), (550, "Notifictions" if typo else "Notifications"), (680, "Language: English"), (900, "Back")]:
        d.rounded_rectangle((25, y-15, 770, y+62), radius=10, fill="#253e58")
        d.text((50, y), text, fill="white", font=font)
    im.save(path)
    return path


class DemoAndroid:
    package = "com.example.demo"
    serial = "offline-demo"

    def connect(self):
        return self.serial

    def launch(self):
        pass

    def capture(self, path):
        typo = "BUG" in Path(path).name
        make_fixture(path, typo)
        return {"id": Path(path).stem, "path": str(Path(path).resolve()), "width": 800, "height": 1100,
                "sha256": digest(Path(path).read_bytes()), "visual_hash": "demo", "package": self.package, "captured_at": now()}

    def act(self, *args, **kwargs):
        return {"executed": True, "reason": "synthetic"}


class DemoModel:
    last_usage = {}

    def ask(self, role, prompt, schema, images=()):
        self.before_call(role)
        is_bug = "DEMO-BUG" in prompt
        check = "BUG-C" if is_bug else "PASS-C"
        if role == "navigate":
            blocked = "DEMO-BLOCKED" in prompt
            return {"screen_name": "DEMO Settings", "visible_text": ["Notifictions" if is_bug else "Notifications"],
                    "observed_scopes": ["Settings panel"], "uncovered_areas": ["Locked screen"] if blocked else [],
                    "inspect_checks": [] if blocked else [check], "action": action("blocked" if blocked else "finish"),
                    "rationale": "Deterministic synthetic fixture", "blocker": "Demo: modulo bloccato" if blocked else ""}
        if role == "analyze":
            ident = Path(images[0]).stem
            candidate = {"check_id": check, "taxonomy_id": "client-r19", "evidence_id": ident,
                         "bbox": {"x": .05, "y": .49, "width": .45, "height": .07}, "observed": "Notifictions",
                         "expected": "Notifications", "explanation": "Demo: missing a", "confidence": 1}
            return {"checks": [{"check_id": check, "status": "issue" if is_bug else "clear", "evidence_ids": [ident], "explanation": "DEMO synthetic"}],
                    "candidates": [candidate] if is_bug else [], "transcriptions": [{"evidence_id": ident, "text": "Notifictions" if is_bug else "Notifications"}]}
        if role == "verify":
            return {"verdict": "confirmed", "observed": "Notifictions", "expected": "Notifications", "explanation": "DEMO synthetic typo", "report_comment": "The word is missing the letter ‘a’.", "confidence": 1}
        return {"checks": [{"check_id": check, "covered": True, "explanation": "Entire synthetic screen"}],
                "scope_complete": True, "missing_areas": [], "explanation": "DEMO synthetic audit"}


def demo(folder, real_model=False):
    folder = Path(folder).resolve()
    project_file = folder.parent / f"{folder.name}-project.json"
    p = {"name": "DEMO SINTETICA — non sono risultati di un gioco", "language": "English", "device": {"package": DemoAndroid.package},
         "launch_wait_seconds": 0, "cases": []}
    p["demo_model"] = "GPT reale" if real_model else "simulato, nessuna chiamata GPT"
    for name in (("BUG",) if real_model else ("PASS", "BUG", "BLOCKED")):
        p["cases"].append({"id": f"DEMO-{name}", "title": f"DEMO {name}", "objective": "Inspect synthetic settings panel", "journey": [],
                           "checks": [{"id": f"{name}-C", "scope": "Settings panel", "instruction": "Read all labels", "modality": "visual"}]})
    write_json(project_file, p)
    engine = Engine(load_project(project_file), folder, driver=DemoAndroid(), model=None if real_model else DemoModel())
    engine.run()
    return export(folder)
