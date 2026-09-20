"""Replay the same visual requests on two models; never executes Android actions."""
from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from .codex import Codex
from .demo import make_fixture
from .schema import ANALYSIS, NAV
from .util import read_json, write_json


def benchmark(run_folder, output):
    run_folder, output = Path(run_folder).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    run = read_json(run_folder / "run.json")
    records = []
    # First two unique observed navigation states; identical prompt/images across models.
    prompts = sorted((run_folder / "model").glob("*-navigate.prompt.txt"))
    samples = []
    seen = set()
    for path in prompts:
        original = path.read_text(encoding="utf-8")
        start = original.find('"current_evidence":')
        if start < 0:
            continue
        text = original[start:]
        ident = text.split('"id": "', 1)[1].split('"', 1)[0]
        if ident not in run["evidence"]:
            continue
        evidence = run["evidence"][ident]
        if evidence["visual_hash"] in seen:
            continue
        seen.add(evidence["visual_hash"])
        prompt = original + "\nFor this benchmark: never opt in to optional ads, analytics or marketing. Use minimum required terms only."
        samples.append((ident, "navigate", prompt, NAV, [run_folder / evidence["path"]]))
        if len(samples) == 2:
            break
    for typo in (False, True):
        image = make_fixture(output / f"synthetic-{'typo' if typo else 'clear'}.png", typo)
        label = image.stem
        prompt = """Analyze this synthetic settings screen as an English LQA check. Check spelling, grammar,
overflow, truncation and readability of all labels. Only report objective defects, not stylistic preferences.
Use check_id EN-01 and evidence_id IMAGE-01. Provide normalized bbox for any defect and a valid taxonomy ID.
For this benchmark a single static fixture is provided; persistence is not applicable. Return clear if no defect.
Taxonomy: """ + json.dumps(run["project"]["taxonomy_snapshot"]["entries"], ensure_ascii=False)
        samples.append((label, "analyze", prompt, ANALYSIS, [image]))
    for name, model in (("terra", "gpt-5.6-terra"), ("astra", "gpt-6-astra")):
        config = {"timeout_seconds": 180, "models": {"navigate": {"model": model, "reasoning": "low"}, "analyze": {"model": model, "reasoning": "medium"}}}
        c = Codex(output / name, config)
        for ident, role, prompt, schema, images in samples:
            started = time.monotonic()
            answer = c.ask(role, prompt, schema, images)
            elapsed = round(time.monotonic() - started, 2)
            score = None
            if ident == "synthetic-clear":
                score = not answer["candidates"] and all(x["status"] == "clear" for x in answer["checks"])
            elif ident == "synthetic-typo":
                score = any("notifictions" in x["observed"].lower() and "notifications" in x["expected"].lower() for x in answer["candidates"])
            records.append({"model": model, "reasoning": config["models"][role]["reasoning"], "sample": ident,
                            "role": role, "seconds": elapsed, "usage": c.last_usage, "fixture_correct": score, "answer": answer})
            write_json(output / "benchmark.json", {"method": "same prompts and screenshots, no Android inputs; synthetic checks have known labels", "records": records})
            print(f"{name} {ident}: {elapsed}s; fixture_correct={score}", flush=True)
    summary = []
    for name in ("gpt-5.6-terra", "gpt-6-astra"):
        selected = [r for r in records if r["model"] == name]
        summary.append({"model": name, "navigation_median_seconds": statistics.median(r["seconds"] for r in selected if r["role"] == "navigate"),
                        "analysis_median_seconds": statistics.median(r["seconds"] for r in selected if r["role"] == "analyze"),
                        "synthetic_correct": sum(r["fixture_correct"] is True for r in selected), "synthetic_total": 2})
    write_json(output / "summary.json", summary)
    return summary
