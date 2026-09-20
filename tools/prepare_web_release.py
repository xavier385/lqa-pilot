"""Create the public static deployment from an allowlist. Never include accounts or runs."""
import json
import shutil
import sys
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED

root=Path(__file__).resolve().parents[1]
exe=root.parent/'outputs/lqa-pilot/windows/LQA Pilot.exe'
if not exe.is_file(): raise RuntimeError('Build the Windows companion first')
web=root/'webapp'
(web/'site').mkdir(exist_ok=True)
for name in ('index.html','app.js','style.css'): shutil.copy2(root/'lqa_pilot/web'/name,web/'site'/name)
(web/'downloads').mkdir(exist_ok=True)
origin=sys.argv[1] if len(sys.argv)>1 else ''
archive=web/'downloads/LQA-Pilot-Windows.zip'
with ZipFile(archive,'w',ZIP_DEFLATED) as z:
    z.write(exe,'LQA Pilot.exe')
    z.writestr('web-origin.json',json.dumps({'origin':origin}))
    z.writestr('LEGGIMI.txt','LQA Pilot\n\nEstrai tutta la cartella e apri LQA Pilot.exe.\nServono MuMu con il gioco installato e Codex con il tuo account ChatGPT.\nIl pulsante di accesso apre il login nel browser.\nSe l\'indirizzo della web app non è già impostato, incollalo nella finestra.\nLascia aperti MuMu e LQA Pilot durante il lavoro. Non servono Python o comandi.\n')
print(archive,archive.stat().st_size,'bytes')
