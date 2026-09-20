from __future__ import annotations

import argparse
import functools
import http.server
import json
import sys
import time
import webbrowser
from pathlib import Path

from .android import Android
from .codex import Codex, DEFAULT_MODELS
from .engine import Engine
from .project import import_taxonomy, load_project, prepare
from .report import export
from .util import PilotError, read_json, write_json
from .modes import MODES


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="lqa-pilot", description="LQA Android autonoma tramite Codex / ChatGPT, senza API key")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("doctor", help="Verifica Codex, autenticazione ChatGPT e ADB")
    p.add_argument("--project")
    p.add_argument("--probe-models", action="store_true", help="Verifica accesso ai modelli con brevi chiamate GPT (usa quota)")
    sub.add_parser("login", help="Accedi a Codex con il TUO account ChatGPT")
    p = sub.add_parser("pack-project", help="Esporta progetto e materiali senza percorsi personali o credenziali")
    p.add_argument("project")
    p.add_argument("--output", required=True)
    p = sub.add_parser("recheck", help="Riesegue solo i casi marcati Recheck nell'Excel")
    p.add_argument("workbook")
    p.add_argument("--run", required=True, help="Cartella della run originale")
    p.add_argument("--output", required=True)
    p.add_argument("--prepare-only", action="store_true")
    p.add_argument("--live", action="store_true", help="Raccoglie nuove prove navigando nel gioco; di default rianalizza quelle originali")
    p = sub.add_parser("init", help="Crea un progetto da compilare")
    p.add_argument("directory")
    p = sub.add_parser("prepare", help="Compila obiettivi/materiali in test case")
    p.add_argument("project")
    p.add_argument("--output", required=True)
    for name in ("run", "resume"):
        p = sub.add_parser(name)
        p.add_argument("project")
        p.add_argument("--output", required=True)
        p.add_argument("--no-launch", action="store_true")
        p.add_argument("--mode", choices=MODES, help="full: controlli completi; fast: controlli essenziali; video: solo registrazione")
    p = sub.add_parser("report")
    p.add_argument("run")
    p = sub.add_parser("setup-game", help="Navigazione preparatoria, esclusa dai risultati LQA")
    p.add_argument("project")
    p.add_argument("--output", required=True)
    p.add_argument("--resume", action="store_true")
    p = sub.add_parser("review", help="Apre report locale con copia delle righe e degli screenshot")
    p.add_argument("run")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true")
    p = sub.add_parser("taxonomy")
    p.add_argument("workbook")
    p.add_argument("--output", required=True)
    p = sub.add_parser("demo", help="Verifica offline con schermate sintetiche, senza GPT/MuMu")
    p.add_argument("--output", required=True)
    p.add_argument("--gpt", action="store_true", help="Verifica un bug sintetico con GPT reale (consuma quota)")
    p = sub.add_parser("benchmark", help="Confronta Terra/Astra su schermate identiche, senza azioni Android")
    p.add_argument("run")
    p.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            output = Path(args.directory).resolve()
            output.mkdir(parents=True, exist_ok=True)
            target = output / "project.json"
            if target.exists():
                raise PilotError("project.json esiste già")
            sample = Path(__file__).parent / "data/project-template.json"
            write_json(target, read_json(sample))
            print(target)
        elif args.command == "login":
            import subprocess
            c = Codex(Path.cwd()/".lqa-doctor")
            return subprocess.call([c.exe, "login"], env=c.environment())
        elif args.command == "pack-project":
            from .portable import pack_project
            print(pack_project(args.project, args.output))
        elif args.command == "recheck":
            from .recheck import prepare_recheck
            project = prepare_recheck(args.workbook, args.run, args.output)
            if args.prepare_only:
                print(project)
            else:
                folder = Path(args.output)/"run"
                if args.live:
                    engine = Engine(load_project(project), folder)
                    state = engine.run()
                else:
                    from .reassess import reassess
                    state = reassess(load_project(project), args.run, folder)
                print(export(folder))
                return 2 if any(c["status"] == "INCOMPLETE" for c in state["cases"].values()) else 0
        elif args.command == "doctor":
            from .modes import apply_mode
            p = apply_mode(read_json(args.project) if args.project else {})
            c = Codex(Path.cwd() / ".lqa-doctor", p.get("codex"))
            print("Codex:", c.exe, "| login:", c.check_auth())
            d = Android(p.get("device", {}))
            print("ADB:", d.exe, "| device:", d.connect(), "| foreground:", d.foreground())
            print("Models:", json.dumps(p.get("codex", {}).get("models", DEFAULT_MODELS), indent=2))
            from .excel_report import artifact_runtime
            import PIL, openpyxl
            print("Excel:", "artifact-tool" if artifact_runtime() else "openpyxl", "| Python:", sys.version.split()[0])
            if args.probe_models:
                from .schema import obj, S
                seen = set()
                choices = {role: {**default, **p.get("codex", {}).get("models", {}).get(role, {})}
                           for role, default in DEFAULT_MODELS.items()}
                for role, choice in choices.items():
                    if p["mode"] == "video" and role not in {"navigate", "audit"}:
                        continue
                    pair = (choice["model"], choice["reasoning"])
                    if pair in seen:
                        continue
                    seen.add(pair)
                    answer = c.ask(role, 'Return {"status":"ok"}. This is an availability check.', obj(status=S))
                    if answer["status"] != "ok":
                        raise PilotError(f"Verifica modello non riuscita: {pair}")
                    print("Modello disponibile:", *pair)
        elif args.command == "prepare":
            print(prepare(args.project, args.output))
        elif args.command in {"run", "resume"}:
            engine = Engine(load_project(args.project, args.mode), args.output, resume=args.command == "resume")
            state = engine.run(launch=not args.no_launch)
            print(export(args.output))
            incomplete = any(c["status"] == "INCOMPLETE" or c["coverage"] != "complete" for c in state["cases"].values())
            return 2 if incomplete else 0
        elif args.command == "report":
            print(export(args.run))
        elif args.command == "setup-game":
            from .setup_game import setup_game
            result = setup_game(load_project(args.project), args.output, resume=args.resume)
            print(result["status"])
            return 0 if result["status"] == "setup_complete" else 2
        elif args.command == "review":
            root = Path(args.run).resolve()
            if not (root / "review.html").is_file():
                export(root)
            # Serve report/evidence only, not prompts/project files or parent directories.
            class ReviewHandler(http.server.SimpleHTTPRequestHandler):
                def do_GET(self):
                    from urllib.parse import unquote, urlsplit
                    rel = unquote(urlsplit(self.path).path).lstrip("/") or "review.html"
                    target = (root / rel).resolve()
                    allowed = {"review.html", "report.xlsx", "report.md", "results.json", "bugs.tsv", "bugs_paste.tsv", "test_results.tsv", "test_results_paste.tsv"}
                    if not target.is_relative_to(root) or not (rel in allowed or (rel.startswith("evidence/") and target.suffix.lower() in {".png", ".jpg"})):
                        self.send_error(403)
                        return
                    if not target.is_file():
                        self.send_error(404)
                        return
                    super().do_GET()
            server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), functools.partial(ReviewHandler, directory=str(root)))
            url = f"http://127.0.0.1:{server.server_port}/review.html"
            print(url, flush=True)
            if not args.no_browser:
                webbrowser.open(url)
            try:
                server.serve_forever()
            finally:
                server.server_close()
        elif args.command == "taxonomy":
            print(f"Importati {len(import_taxonomy(args.workbook, args.output)['entries'])} tipi di bug")
        elif args.command == "demo":
            from .demo import demo
            print(demo(args.output, real_model=args.gpt))
        elif args.command == "benchmark":
            from .benchmark import benchmark
            print(json.dumps(benchmark(args.run, args.output), indent=2))
        return 0
    except (PilotError, ValueError, OSError) as e:
        print(f"LQA Pilot: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrotto. La run salvata può essere ripresa.", file=sys.stderr)
        return 130
