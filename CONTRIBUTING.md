# Sviluppare LQA Pilot

Questo repository contiene il bot Windows, la web app statica e i test software della versione 0.6.0. Il funzionamento per gli operatori è descritto in [README.md](README.md); i risultati e i limiti delle verifiche sono in [VALIDAZIONE.md](VALIDAZIONE.md).

## Ambiente locale

Servono Windows, Git e Python 3.11 o successivo. Node.js serve soltanto per verificare o compilare la web app. Dalla cartella clonata:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe 'LQA Pilot.pyw'
```

Per usare realmente il bot occorrono MuMu, un gioco installato e Codex CLI con il proprio login ChatGPT. Questi non servono ai test unitari. Gli account, le quote e gli accessi restano personali: il repository non contiene credenziali né sessioni.

## Verifiche senza consumo GPT

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
node --check lqa_pilot/web/app.js
node webapp/build.mjs
```

I test usano dispositivi e risposte modello simulati; non dimostrano la qualità linguistica di GPT su nuovi giochi o nuovi Excel. Non eseguire `run` o `doctor --probe-models` per verificare una modifica al software: richiedono un collaudo operativo separato e possono consumare quota. `tests/verify_excel_integration.py` è uno script aggiuntivo che richiede una run esportata locale.

## Dove intervenire

| Cartella o file | Responsabilità |
| --- | --- |
| `lqa_pilot/web/` | Sorgenti canonici dell'interfaccia web |
| `lqa_pilot/desktop.py`, `web_bridge.py` | Componente Windows, pairing e gestione dei lavori |
| `lqa_pilot/workbook_project.py`, `workbook_understanding.py` | Lettura e interpretazione dell'Excel prima della navigazione |
| `lqa_pilot/client_excel.py`, `report_preflight.py` | Conservazione del formato cliente e controllo dell'export |
| `lqa_pilot/` | Navigazione, analisi, registrazione, diagnostica e report |
| `tests/` | Verifiche locali con fixture |
| `examples/` | Configurazioni dimostrative; non sono test case forniti dai clienti |
| `tools/` | Preparazione dei pacchetti e verifiche di supporto |
| `webapp/` | Configurazione e build statica Vercel |

## Pacchetto Windows e distribuzione

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --onefile --windowed --name 'LQA Pilot' --distpath '../outputs/lqa-pilot/windows' --workpath '.packaging/gui-work' --specpath '.packaging' --collect-data lqa_pilot --collect-all imageio_ffmpeg 'LQA Pilot.pyw'
.\.venv\Scripts\python.exe tools/prepare_web_release.py 'https://lqa-pilot-web.vercel.app'
node webapp/build.mjs
```

Il percorso `../outputs/lqa-pilot/windows` è quello atteso dal preparatore di release. Per una web app diversa passare il proprio URL HTTPS. `webapp/public`, `webapp/downloads` e `webapp/site` sono generati e non si modificano a mano. Il pacchetto Windows non è incluso in Git; deve essere compilato prima del deploy per rendere disponibile il download.

Il deploy Vercel usa `webapp` come directory radice e richiede accesso al proprio account/progetto Vercel. Il preparatore copia anche i sorgenti web in `webapp/site`, così il deploy dalla sola cartella `webapp` è autosufficiente. Non pubblicare una build senza ZIP sopra al sito di produzione: il collegamento al componente Windows non funzionerebbe. Non sono configurati deploy automatici da questo repository.

Per uno ZIP dei sorgenti:

```powershell
.\.venv\Scripts\python.exe tools/package_release.py '../outputs/LQA-Pilot-source.zip'
```

## Dati da tenere fuori da Git

Non aggiungere file LQA dei clienti, run, screenshot, video, report reali, log, token, `.env`, cartelle `.codex` o `.vercel`, ambienti Python o binari compilati. Usare fixture sintetiche nei test. Non inserire credenziali nel codice: ogni collega effettua il proprio accesso a Codex e, se necessario, a Vercel.
