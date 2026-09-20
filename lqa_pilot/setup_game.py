"""Observe-act setup (e.g. language selection), kept separate from LQA results."""
from pathlib import Path
import json

from .engine import Engine
from .schema import AUDIT
from .util import FileLock, PilotError, digest


def setup_game(project, folder, resume=False):
    e = Engine(project, folder, resume=resume)
    case = project["cases"][0]
    result = e.state["cases"].get(case["id"], {"title": case["title"], "steps": [], "checks": {}, "screens": [], "findings": [], "transcriptions": []})
    e.state["mode"] = "setup_only_not_lqa"
    e.state["status"] = "running"
    e.state.pop("run_error", None)
    e.state["cases"][case["id"]] = result
    try:
        serial = e.driver.connect()
        with FileLock(Path.home() / ".lqa-pilot/locks" / f"{digest(serial)[:24]}.lock"):
            for _ in range(max(0, int(project["budgets"]["max_actions"]) - e.state["actions"])):
                evidence = e.capture(case["id"])
                if evidence["package"] != e.driver.package:
                    raise PilotError("Gioco non in primo piano durante il setup")
                nav = e.navigate(case, result, evidence)
                record = {"evidence_id": evidence["id"], **nav}
                result["steps"].append(record)
                if nav["screen_name"] not in result["screens"]:
                    result["screens"].append(nav["screen_name"])
                e.event("setup_decision", message=f"{nav['screen_name']}: {nav['action']['kind']} {nav['action']['target']}")
                if nav["action"]["kind"] == "blocked":
                    raise PilotError(nav["blocker"] or nav["rationale"])
                if nav["action"]["kind"] == "finish":
                    fresh = e.capture(case["id"], "setup-check")
                    check = e.ask("audit", "Verify only that this setup objective is visibly satisfied. This is not an LQA PASS. Return the supplied check IDs.\n" + json.dumps({"case": case, "recent_steps": result["steps"][-5:]}, ensure_ascii=False), AUDIT, [fresh["path"]])
                    result["audit"] = check
                    expected = {c["id"] for c in case["checks"]}
                    returned = {c["check_id"] for c in check["checks"]}
                    if (check["scope_complete"] and not check["missing_areas"] and returned == expected
                            and len(check["checks"]) == len(expected) and all(c["covered"] for c in check["checks"])):
                        e.state["status"] = "setup_complete"
                        break
                if nav["action"]["kind"] not in {"inspect", "finish"}:
                    e.budget()
                    e.state["actions"] += 1
                    record["execution"] = e.driver.act(nav["action"], evidence, e.folder / "evidence" / f"{evidence['id']}-guard.png", allow_game_progress=project["policy"].get("allow_game_progress", False))
                    e.event("setup_action", message=str(record["execution"]))
            else:
                raise PilotError("Budget setup esaurito")
    except (PilotError, OSError, KeyboardInterrupt) as error:
        e.state["status"] = "setup_incomplete"
        e.state["run_error"] = str(error)
        e.event("setup_stopped", message=str(error))
    finally:
        e.save()
    return e.state
