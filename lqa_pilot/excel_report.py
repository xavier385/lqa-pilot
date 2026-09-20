"""Portable Excel review reports with untouched full-screen evidence inside the border."""
from __future__ import annotations

import math
import os
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

from .util import PilotError, digest, process, write_json

REVIEW_OPTIONS = ["Pass", "Bug", "Bug (partial)", "Incomplete", "Recheck", "Accepted", "Dismissed"]


def annotate(source, target, bbox):
    """Draw OUTSIDE the text bounding box, preserving every pixel inside it."""
    with Image.open(source) as original:
        im = original.convert("RGB")
    w, h = im.size
    x, y, bw, bh = (bbox[k] for k in ("x", "y", "width", "height"))
    if not all(math.isfinite(v) for v in (x, y, bw, bh)) or min(x, y) < 0 or min(bw, bh) <= 0 or x+bw > 1.001 or y+bh > 1.001:
        raise PilotError("Riquadro evidenza non valido")
    left, top = max(0, math.floor(x*w)), max(0, math.floor(y*h))
    right, bottom = min(w, math.ceil((x+bw)*w)), min(h, math.ceil((y+bh)*h))
    protected = im.crop((left, top, right, bottom))
    stroke = max(3, round(min(w, h)/200))
    margin = stroke * 2
    rectangle = (max(0, left-margin), max(0, top-margin), min(w-1, right+margin), min(h-1, bottom+margin))
    ImageDraw.Draw(im).rectangle(rectangle, outline="#FF0000", width=stroke)
    # A bbox at the image edge must never cause a stroke to cover the text.
    im.paste(protected, (left, top))
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    im.save(target)
    return {"path": str(target), "text_box_pixels": [left, top, right, bottom], "border_pixels": list(rectangle), "stroke": stroke}


def artifact_runtime():
    """Optional Codex document runtime; no machine or account-specific fixed paths."""
    root = Path(os.environ.get("LQA_ARTIFACT_RUNTIME", Path.home()/".cache/codex-runtimes/codex-primary-runtime/dependencies/node"))
    node = root/"bin/node.exe" if os.name == "nt" else root/"bin/node"
    library = root/"node_modules/@oai/artifact-tool"
    if node.is_file() and library.is_dir():
        return node, library
    return None


def build_payload(folder, run, cases, bugs, client_headers, client_rows):
    from .report import BUG_HEADERS, CLIENT_HEADERS
    folder = Path(folder)
    rows, images = [], []
    for case in cases:
        spec, result = case["spec"], case["result"]
        associated = [b for b in bugs if b["case_id"] == spec["id"]]
        for bug in associated:
            row = list(bug["row"])
            ev = bug.get("evidence") or run["evidence"][bug["evidence_id"]]
            target = folder/"evidence"/(bug["id"]+"-annotated.png")
            annotation = annotate(folder/ev["path"], target, bug["bbox"])
            row[3] = ""
            row[6] = bug["id"]
            row[15] = "Bug" if result.get("coverage") == "complete" else "Bug (partial)"
            row[16] = ""
            rows.append(row)
            images.append({"row": len(rows), "column": 3, **annotation})
        if not associated:
            row = [""] * len(BUG_HEADERS)
            row[1], row[2] = spec["title"], spec["id"]
            row[15] = "Pass" if result.get("status") == "PASS" else "Incomplete"
            rows.append(row)
    return {"title": run["project"]["name"], "started_at": run["started_at"],
            "run_id": digest([run["project_hash"], run["started_at"]])[:24],
            "mode": run["project"].get("mode", "full"),
            "sheets": [{"name": "Bug list", "headers": CLIENT_HEADERS, "rows": rows, "review_col": 15,
                        "widths": [102,230,120,306,190,480,180,125,100,140,74,105,140,115,150,120,230,130],
                        "images": images}], "review_options": REVIEW_OPTIONS}


def export_excel(folder, run, cases, bugs, client_headers, client_rows):
    folder = Path(folder).resolve()
    target = folder/"report.xlsx"
    if target.exists():
        # Preserve reviewers' edits when refreshing HTML or report data.
        backup = folder/"review-backups"
        backup.mkdir(exist_ok=True)
        import time
        shutil.copy2(target, backup/f"report-{time.time_ns()}.xlsx")
    payload = build_payload(folder, run, cases, bugs, client_headers, client_rows)
    write_json(folder/"excel-payload.json", payload)
    runtime = artifact_runtime()
    if runtime:
        node, library = runtime
        # Execute the builder next to a local module link; never modify shared dependencies.
        work = folder/".excel-build"
        work.mkdir(exist_ok=True)
        builder = work/"build.mjs"
        shutil.copy2(Path(__file__).with_name("excel_builder.mjs"), builder)
        modules = work/"node_modules"
        if not modules.exists():
            if os.name == "nt":
                # Junction created via native PowerShell, with literal arguments.
                script = work/"link.ps1"
                script.write_text("param($LinkPath, $TargetPath)\n$ErrorActionPreference='Stop'\n$null = New-Item -ItemType Junction -Path $LinkPath -Target $TargetPath\n", encoding="utf-8")
                process(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script, str(modules), str(library.parent.parent)])
            else:
                modules.symlink_to(library.parent.parent, target_is_directory=True)
        process([node, builder, folder/"excel-payload.json", target], timeout=180)
        backend = "artifact-tool"
    else:
        # Public, redistributable fallback for colleagues without Codex's document runtime.
        from .excel_portable import write_workbook
        write_workbook(payload, target)
        backend = "openpyxl (artifact-tool unavailable)"
    from .workbook_meta import write_metadata
    write_metadata(target, {"LQA_Run_ID": payload["run_id"], "LQA_Mode": payload["mode"]})
    write_json(folder/"excel-export.json", {"backend": backend, "file": target.name, "sheets": [s["name"] for s in payload["sheets"]]})
    return target
