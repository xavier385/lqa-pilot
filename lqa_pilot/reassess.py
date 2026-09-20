"""Reassess original evidence after review, without moving or changing the game."""
import copy
import shutil
from pathlib import Path

from .engine import Engine, final_status
from .util import PilotError, read_json


def evidence_pairs(ids, evidence, case_id):
    ordered = list(evidence)
    positions = {key:i for i,key in enumerate(ordered)}
    pairs = []
    for ident in ids:
        if ident not in positions or evidence[ident].get("case_id") != case_id:
            return ()
        index = positions[ident]
        first_index = index-1 if ident.endswith("-confirmation") else index
        if first_index < 0 or first_index+1 >= len(ordered):
            return ()
        pair = tuple(ordered[first_index:first_index+2])
        if not pair[1].endswith("-confirmation") or pair[0].endswith("-confirmation") or any(evidence[p].get("case_id") != case_id for p in pair):
            return ()
        if pair not in pairs:
            pairs.append(pair)
    return tuple(i for pair in pairs for i in pair)


class ArchivedFrames:
    def __init__(self, folder, source):
        self.folder, self.source = Path(folder).resolve(), source
        self.package = source["project"]["device"]["package"]
        self.queue = []

    def capture(self, path):
        if not self.queue:
            raise PilotError("Manca il secondo frame originale: non duplicare una prova per simulare conferma")
        ident = self.queue.pop(0)
        original = self.source["evidence"].get(ident)
        if not original:
            raise PilotError("Prova originale non trovata")
        source_path = (self.folder/original["path"]).resolve()
        if not source_path.is_relative_to(self.folder):
            raise PilotError("Il percorso della prova esce dalla cartella della run")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, path)
        return {**original,"id":path.stem,"path":str(path.resolve()),"source_evidence_id":ident}

    def act(self, *args, **kwargs):
        raise PilotError("Il riesame delle prove non può inviare input al gioco")


def reassess(project, source_folder, output, *, model=None):
    source = read_json(Path(source_folder)/"run.json")
    project = copy.deepcopy(project)
    project["name"] += " — riesame delle prove originali"
    project["case_source"] = "Riesame dei casi selezionati nell'Excel sulle prove della run " + source["started_at"] + "; nessun nuovo test sulla build corrente."
    driver = ArchivedFrames(source_folder, source)
    engine = Engine(project, output, driver=driver, model=model)
    engine.state["mode"] = "evidence_only_reassessment"
    engine.state["environment"] = source.get("environment", {})
    try:
        for case in project["cases"]:
            old = source["cases"].get(case["id"], {})
            result = {"title":case["title"],"steps":copy.deepcopy(old.get("steps", [])), "screens":old.get("screens", []),
                      "checks":{},"findings":[],"transcriptions":[]}
            engine.state["cases"][case["id"]] = result
            groups = {}
            for check in case["checks"]:
                referenced = old.get("checks", {}).get(check["id"], {}).get("evidence_ids", [])
                ids = evidence_pairs(referenced, source["evidence"], case["id"])
                if not ids:
                    result["checks"][check["id"]] = {"status":"not_observed","evidence_ids":[],"explanation":"Prove originali complete non disponibili"}
                    result["blocker"] = "Uno o più controlli non hanno coppie complete di prove originali; serve un ricontrollo --live."
                    continue
                groups.setdefault(ids, []).append(check["id"])
            source_to_new = {}
            for ids, check_ids in groups.items():
                for offset in range(0, len(ids), 2):
                    pair = ids[offset:offset+2]
                    if any(source["evidence"].get(i, {}).get("case_id") != case["id"] for i in pair):
                        raise PilotError("Prove associate a un caso diverso")
                    driver.queue = list(pair)
                    first = engine.capture(case["id"])
                    source_to_new[pair[0]] = first["id"]
                    engine.analyze(case, result, first, check_ids)
            for step in result["steps"]:
                original_id = step["evidence_id"]
                if original_id not in source_to_new:
                    if source["evidence"].get(original_id, {}).get("case_id") != case["id"]:
                        raise PilotError("Prova del percorso originale mancante o associata a un altro caso")
                    driver.queue = [original_id]
                    source_to_new[original_id] = engine.capture(case["id"], "route")["id"]
                step["source_evidence_id"] = original_id
                step["evidence_id"] = source_to_new[original_id]
            if groups:
                engine.audit(case, result)
            result["status"], result["coverage"] = final_status(case, result)
            engine.save()
        engine.state["status"] = "finished"
    except (PilotError, OSError, ValueError, KeyboardInterrupt) as error:
        engine.state["status"] = "interrupted"
        engine.state["run_error"] = str(error) or "Interrotto"
    finally:
        for case in project["cases"]:
            result = engine.state["cases"].setdefault(case["id"], {"title":case["title"],"checks":{},"findings":[],"blocker":"Riesame non eseguito"})
            result["status"], result["coverage"] = final_status(case, result)
        engine.save()
    return engine.state
