from __future__ import annotations

import csv
import html
import io
import json
import re
from pathlib import Path

from .util import read_json, write_json

BUG_HEADERS = ["Date Created", "Location", "Bug Module", "Screenshot", "LQA Bug",
               "Error Description & Suggestion", "Error Key", "Fixed in Language File", "Translator issue",
               "Responsible person / PM", "Priority", "Bug Category", "Assigned To", "Dev Status",
               "Dev Notes", "LQA Status", "Localizer Notes", "Created By"]
CASE_HEADERS = ["Case ID", "Module", "Result", "Coverage", "Checks analyzed", "Total checks", "Bugs", "Notes"]
CLIENT_HEADERS = read_json(Path(__file__).parent/"data/client_columns.json")


def cell(value):
    """Plain TSV cells; prevent spreadsheet formula execution on untrusted game text."""
    value = str(value).replace("\t", " ").replace("\r", " ").replace("\n", " | ")
    if value.lstrip().startswith(("=", "+", "-", "@")):
        value = "'" + value
    return value


def tsv(headers, rows, with_headers=True):
    return "\n".join("\t".join(cell(v) for v in row) for row in ([headers] if with_headers else []) + rows) + "\n"


def export(folder):
    folder = Path(folder).resolve()
    run = read_json(folder / "run.json")
    if run["project"].get("mode") == "video":
        from .video import export_manifest
        return export_manifest(folder, run)
    if run['project'].get('client_workbook'):
        from .client_excel import export_client
        return export_client(folder,state=run)
    project = run["project"]
    cases, bugs, pending = [], [], []
    bug_rows, case_rows = [], []
    for spec in project["cases"]:
        result = run["cases"].get(spec["id"], {})
        confirmed = [f for f in result.get("findings", []) if f["verification"]["verdict"] == "confirmed"]
        pending.extend({**f, "case_id": spec["id"]} for f in result.get("findings", []) if f["verification"]["verdict"] == "uncertain")
        note = "" if result.get("status") == "PASS" else result.get("blocker", "") or result.get("audit", {}).get("explanation", "")
        ids = [f["id"] for f in confirmed]
        case_rows.append([spec["id"], spec["title"], result.get("status", "INCOMPLETE"), result.get("coverage", "partial"),
                          sum(bool(c.get("evidence_ids")) for c in result.get("checks", {}).values()), len(spec["checks"]), ", ".join(ids), note])
        cases.append({"spec": spec, "result": result, "row": case_rows[-1]})
        for finding in confirmed:
            taxonomy = finding["taxonomy"]
            evidence = run["evidence"][finding["evidence_id"]]
            steps = result.get("steps", [])
            sequence = []
            for s in steps[:finding.get("step_index", len(steps))]:
                if s["evidence_id"] == finding["evidence_id"]:
                    break
                if s.get("execution", {}).get("executed") and s["action"]["kind"] not in {"wait"}:
                    sequence.append(f"{s['action']['kind']}: {s['action']['target']}")
            comment = finding['verification'].get('report_comment', finding['verification']['explanation'])
            description = f"Text: {finding['observed']}\nIssue: {comment}\nFix: {finding['expected']}"
            row = [run["started_at"][:10], spec["title"], spec["id"], f"evidence/{finding['id']}-annotated.png",
                   taxonomy["name_zh"], description, "", "", "", "", taxonomy["priority"], taxonomy["category"],
                   taxonomy["owner"], "", "", "", "Ready for human review", "LQA Pilot / GPT"]
            bug_rows.append(row)
            bugs.append({**finding, "case_id": spec["id"], "evidence": evidence, "steps": sequence, "row": row})
    from .excel_report import export_excel
    workbook = export_excel(folder, run, cases, bugs, BUG_HEADERS, bug_rows)
    for name, headers, rows in (("bugs", BUG_HEADERS, bug_rows), ("test_results", CASE_HEADERS, case_rows)):
        (folder / f"{name}.tsv").write_text(tsv(headers, rows), encoding="utf-8-sig")
        (folder / f"{name}_paste.tsv").write_text(tsv(headers, rows, False), encoding="utf-8-sig")
    write_json(folder / "results.json", {"project": project["name"], "run": run["started_at"], "cases": cases,
                                         "bugs": bugs, "unresolved_candidates": pending, "usage": run["usage"]})
    lines = [f"# {project['name']}", "", f"Run: {run['started_at']} · {run['calls']} chiamate GPT · {run['actions']} azioni tentate", "",
             "PASS = tutti i controlli dello scope dichiarato analizzati e audit completo. BUG = errori verificati, con copertura separata. INCOMPLETE = non certificabile.", "",
             "| Caso | Risultato | Copertura | Note |", "|---|---|---|---|"]
    for row in case_rows:
        lines.append("| " + " | ".join(str(row[i]).replace("|", "/").replace("\n", " ") for i in (0, 2, 3, 7)) + " |")
    for bug in bugs:
        lines.extend(["", f"## {bug['id']} — {bug['taxonomy']['name_en']}", "",
                      f"Osservato: {bug['observed']}", "", f"Atteso: {bug['expected']}", "",
                      f"{bug['verification'].get('report_comment', bug['verification']['explanation'])}", "", f"Prova: [{bug['evidence_id']}]({bug['evidence']['path'].replace(chr(92), '/')})"])
    lines.extend(["", f"Candidati incerti esclusi dalla tabella bug: {len(pending)}.", "",
                  "Il controllo è visivo: nessun accesso a sorgenti/engine. Audio e accuratezza rispetto a sorgenti non fornite restano non verificati.",
                  "TSV contiene i testi; immagini e campi relazione/lookup di WeCom richiedono inserimento/associazione nella sheet."])
    (folder / "report.md").write_text("\n".join(lines), encoding="utf-8")
    h = html.escape
    cards = []
    for case in cases:
        result, spec = case["result"], case["spec"]
        if result.get("status") == "PASS":
            cards.append(f"<article><span class='badge PASS'>Pass</span><h3>{h(spec['id'])} · {h(spec['title'])}</h3></article>")
            continue
        checks_html = ""
        for c in spec["checks"]:
            assessment = result.get("checks", {}).get(c["id"], {})
            proofs = ""
            for ident in assessment.get("evidence_ids", []):
                evidence = run["evidence"].get(ident)
                if evidence:
                    src = h(evidence["path"].replace("\\", "/"))
                    proofs += f'<a href="{src}" target="_blank" title="{h(ident)}"><img class="proof" src="{src}" alt="{h(ident)}"></a>'
            checks_html += f"<li><b>{h(c['scope'])}</b>: {h(c['instruction'])}<br><small>{h(assessment.get('explanation','Non osservato'))}</small><div>{proofs}</div></li>"
        cards.append(f"<article><span class='badge {h(result.get('status','INCOMPLETE'))}'>{h(result.get('status','INCOMPLETE'))}</span> <small>{h(result.get('coverage','partial'))}</small><h3>{h(spec['id'])} · {h(spec['title'])}</h3><p>{h(case['row'][-1])}</p><details><summary>Controlli richiesti e prove</summary><ul>{checks_html}</ul></details></article>")
    bug_cards = []
    for i, b in enumerate(bugs):
        src = h(f"evidence/{b['id']}-annotated.png")
        crop = src
        bug_cards.append(f"""<article class="bug"><div><span class="badge BUG">{h(b['taxonomy']['priority'])}</span>
<h3>{h(b['id'])} · {h(b['taxonomy']['name_en'])}</h3>
<p><b>Osservato:</b> {h(b['observed'])}</p><p><b>Atteso:</b> {h(b['expected'])}</p>
<p>{h(b['verification'].get('report_comment', b['verification']['explanation']))}</p><p><small>{h(' → '.join(b['steps']))}</small></p>
<button onclick="copyRow({i})">Copia riga bug</button> <button onclick="copyImage('{src}')">Copia screenshot</button>
<a href="{src}" target="_blank">Apri originale</a></div><a href="{src}" target="_blank"><img src="{crop}" alt="Prova del bug {h(b['id'])}"></a></article>""")
    data = json.dumps({"bugRows": [[cell(x) for x in r] for r in bug_rows], "caseRows": [[cell(x) for x in r] for r in case_rows]}, ensure_ascii=False).replace("<", "\\u003c")
    page = r"""<!doctype html><html lang="it"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LQA Pilot · Revisione</title><style>
:root{font-family:system-ui,sans-serif;color:#192839;background:#f0f4f8}body{max-width:1180px;margin:auto;padding:34px}h1{font-size:36px;margin:10px 0}h2{margin-top:36px}p{line-height:1.55}small{color:#526278}header{border-bottom:2px solid #d7e1eb;padding-bottom:24px}article{background:white;border:1px solid #dce4ed;border-radius:12px;padding:22px;margin:15px 0;overflow-wrap:anywhere}button,a.download{background:#174969;color:white;border:0;border-radius:7px;padding:10px 14px;cursor:pointer;text-decoration:none;margin:4px 4px 4px 0}.badge{font-size:12px;font-weight:bold;border-radius:5px;padding:5px 9px}.PASS{background:#d8f1e2;color:#165c35}.BUG{background:#ffe1dc;color:#9b2c1c}.INCOMPLETE{background:#fff0c2;color:#775500}.bug{display:grid;grid-template-columns:3fr 2fr;gap:28px}img{max-width:100%;max-height:430px;object-fit:contain}.proof{height:160px;margin:12px 12px 0 0;border-radius:6px}li{margin:12px 0}#toast{position:fixed;bottom:20px;right:20px;background:#192839;color:white;padding:12px;display:none}details{padding:8px 0}footer{margin:35px 0;font-size:13px;color:#526278}@media(max-width:700px){.bug{grid-template-columns:1fr}body{padding:18px}}
</style><header><small>LQA PILOT · RISULTATI DA REVISIONARE</small><h1>__TITLE__</h1><p>__META__</p>
<button onclick="copyAll('bugRows')">Copia tutti i bug</button><button onclick="copyAll('caseRows')">Copia risultati dei case</button>
<a class="download" href="report.xlsx" download>Scarica Excel</a><a class="download" href="bugs.tsv" download>Scarica TSV</a><a class="download" href="results.json" download>JSON completo</a></header>
<h2>Esito dei test case</h2>__CASES__<h2>Bug verificati (__COUNT__)</h2>__BUGS__
<h2>Candidati da approfondire</h2><p>__PENDING__</p>
<footer>PASS riguarda esclusivamente lo scope dichiarato e richiede copertura completa. Non equivale alla certificazione dell'intero gioco.<br>
La copia delle righe usa l'ordine delle 18 colonne del template del cliente. Screenshot da incollare separatamente; relazioni e lookup di WeCom vanno associati nella sheet.<br>
Nessuna pubblicazione automatica. Le decisioni GPT, i tempi e le prove originali sono conservati nella cartella della run.</footer>
<div id="toast" role="status"></div><script>
const data=__DATA__;
function toast(t){const e=document.getElementById('toast');e.textContent=t;e.style.display='block';setTimeout(()=>e.style.display='none',5000)}
async function put(t){try{await navigator.clipboard.writeText(t);toast('Copiato')}catch(e){toast('Copia non disponibile: apri il TSV scaricabile oppure avvia lqa-pilot review.')}}
function copyRow(i){put(data.bugRows[i].join('\t'))}
function copyAll(k){put(data[k].map(r=>r.join('\t')).join('\n'))}
async function copyImage(path){try{const blob=await(await fetch(path)).blob();await navigator.clipboard.write([new ClipboardItem({'image/png':blob})]);toast('Screenshot copiato')}catch(e){toast('Apri originale e copia l’immagine dal browser.')}}
</script></html>"""
    replacements = {"__TITLE__": h(project["name"]), "__META__": h(f"{run['started_at']} · {len(cases)} case · {run['calls']} chiamate GPT · {round(run['active_seconds'])} secondi attivi"),
                    "__CASES__": "".join(cards), "__COUNT__": str(len(bugs)), "__BUGS__": "".join(bug_cards) or "<p>Nessun bug confermato. Verificare gli esiti e la copertura dei case.</p>",
                    "__PENDING__": h("; ".join(f"{b['id']}: {b['verification']['explanation']}" for b in pending) or "Nessuno."), "__DATA__": data}
    page = re.sub("|".join(map(re.escape, replacements)), lambda match: replacements[match.group(0)], page)
    (folder / "review.html").write_text(page, encoding="utf-8")
    return workbook
