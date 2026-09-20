"""Import only explicitly selected review rows; never treat workbook text as commands."""
import copy
from pathlib import Path

from .project import xlsx_rows
from .util import PilotError, digest, read_json, write_json


def selected_cases(workbook, run):
    cases = {s["id"]: s for s in run["project"]["cases"]}
    bugs = {b["id"]: cid for cid, result in run["cases"].items() for b in result.get("findings", [])}
    selected = {}
    from .workbook_meta import read_metadata
    metadata = read_metadata(workbook)
    if "LQA_Run_ID" in metadata:
        if metadata["LQA_Run_ID"] != digest([run["project_hash"], run["started_at"]])[:24]:
            raise PilotError("L'Excel non appartiene alla run indicata")
        rows = xlsx_rows(workbook, "Bug list")
        from .report import BUG_HEADERS, CLIENT_HEADERS
        canonical = dict(zip(CLIENT_HEADERS, BUG_HEADERS))
        headers = ({c: canonical.get(v, v) for c,v in r.items()} for _,r in rows)
        header = next((r for r in headers if "LQA Status" in r.values()), None)
        if not header or not {"LQA Status", "Bug Module", "Error Key", "Localizer Notes"} <= set(header.values()):
            raise PilotError("Intestazioni WeCom mancanti")
        columns = {v:k for k,v in header.items()}
        for _,row in rows:
            if row.get(columns["LQA Status"], "").strip().casefold() not in {"recheck", "ricontrollare"}:
                continue
            cid = row.get(columns["Bug Module"], "")
            ident = row.get(columns["Error Key"], "")
            if cid not in cases or (ident and bugs.get(ident) != cid):
                raise PilotError("Case ID/Bug ID non corrispondono alla run originale")
            selected.setdefault(cid, []).append({"result_id": ident or cid, "reviewer_note": row.get(columns["Localizer Notes"], "")})
        if not selected:
            raise PilotError("Scegliere Recheck nella colonna LQA Status e salvare l'Excel")
        return selected
    for name, id_header in (("Risultati", "Case ID"), ("Bug", "Bug ID")):
        rows = xlsx_rows(workbook, name)
        expected_run = "Run ID: " + digest([run["project_hash"], run["started_at"]])[:24]
        if not any(expected_run in cells.values() for _, cells in rows):
            raise PilotError("L'Excel non appartiene alla run indicata o manca il Run ID")
        headings = next((r for _, r in rows if id_header in r.values() and "Revisione" in r.values()), None)
        if not headings:
            raise PilotError(f"Intestazioni mancanti in {name}")
        columns = {v: k for k, v in headings.items()}
        for _, row in rows:
            if row.get(columns["Revisione"], "").strip().casefold() != "ricontrollare":
                continue
            ident = row.get(columns[id_header], "")
            if name == "Bug" and row.get(columns.get("Origine", ""), "").startswith("SIMULATO"):
                raise PilotError("Una dimostrazione simulata non può essere inviata come bug reale")
            cid = ident if name == "Risultati" else bugs.get(ident)
            if cid not in cases:
                raise PilotError(f"ID sconosciuto nel report: {ident}. Usare la run originale.")
            if name == "Bug" and row.get(columns.get("Case ID", "")) != cid:
                raise PilotError("Bug ID e Case ID non corrispondono alla run originale")
            selected.setdefault(cid, []).append({"result_id": ident, "reviewer_note": row.get(columns.get("Note revisore", ""), "")})
    if not selected:
        raise PilotError("Nessuna riga selezionata: scegliere Ricontrollare nella colonna Revisione")
    return selected


def prepare_recheck(workbook, run_folder, output):
    run_folder, output = Path(run_folder).resolve(), Path(output).resolve()
    run = read_json(run_folder/"run.json")
    selected = selected_cases(workbook, run)
    p = copy.deepcopy(run["project"])
    p.pop("project_file", None)
    if p.get('client_workbook'):
        p['client_workbook']['template']=str(run_folder/'client-template.xlsx')
    for key, paths in run.get("reference_materials", {}).items():
        p[key] = [str(run_folder/value) for value in paths]
    # The finite plan already contains the interpreted journey; avoid stale original video paths.
    p["materials"] = []
    p["device"]["serial"] = "auto"
    p["device"].pop("endpoint", None)
    p["device"].pop("adb", None)
    p.setdefault("codex", {}).pop("executable", None)
    p["cases"] = [c for c in p["cases"] if c["id"] in selected]
    p["review_context"] = selected
    p["recheck_of"] = {"started_at": run["started_at"], "project_hash": run["project_hash"], "workbook_sha256": digest(Path(workbook).read_bytes())}
    p["case_source"] = "Ricontrollo dei casi selezionati nel report Excel; obiettivi originali preservati."
    output.mkdir(parents=True, exist_ok=True)
    if (output/"project.json").exists():
        raise PilotError("La cartella del ricontrollo contiene già un progetto")
    write_json(output/"taxonomy.json", p.pop("taxonomy_snapshot"))
    p["taxonomy"] = "taxonomy.json"
    write_json(output/"project.json", p)
    return output/"project.json"
