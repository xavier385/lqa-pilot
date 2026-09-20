# LQA Pilot

Per lavorare sul codice: [guida per lo sviluppo](CONTRIBUTING.md). Lo stato dei collaudi e i limiti conosciuti sono in [VALIDAZIONE.md](VALIDAZIONE.md).

Bot visuale per giochi Android in MuMu. Acquisisce autonomamente gli screenshot, naviga tramite ADB, analizza le schermate con GPT e produce risultati da revisionare. Non legge sorgenti o engine del gioco e non richiede screenshot preparati dal tester.

**GPT viene usato tramite `codex exec` con login ChatGPT**, senza chiavi API, SDK OpenAI o automazione dell'interfaccia di ChatGPT. Richiede connessione Internet e una sessione Codex abilitata; consuma la quota Codex dell'abbonamento. Non è un modello offline né un servizio a consumo illimitato. Riferimenti ufficiali: [autenticazione](https://developers.openai.com/codex/auth), [esecuzione non interattiva e JSON strutturato](https://developers.openai.com/codex/noninteractive).

## Web app — avvio senza comandi (versione 0.5)

**Aggiornamento 0.5.0: lettura dei progetti senza template fisso.** Ogni foglio viene letto per intero nei limiti dichiarati, comprese sezioni miste, commenti, collegamenti, immagini e contesto delle celle unite. Il bot distingue obiettivi/test, guide, glossari, dev key, log key, tassonomie e formati dei difetti. I nomi dei fogli, l'ordine delle colonne e le etichette di priorità non sono prefissati. Le chiavi mantengono valore, significato, utilizzo dichiarato e righe di provenienza; non danno accesso al codice/engine e non vengono interpretate automaticamente come comandi.

Dopo la lettura viene verificato il contesto di ogni test con le istruzioni dell'intero file e viene eseguita una prova privata del generatore Excel, con dati sintetici esclusi dal risultato finale. Solo quando piano e report risultano validi viene creato il driver Android. La UI mostra un riepilogo dell'analisi. Un'ambiguità sostanziale o un riferimento indispensabile non disponibile interrompe l'importazione prima della navigazione. La lettura di collegamenti esterni non viene simulata. Nessuna prova sintetica dell'export diventa un test case del cliente.

Il report può avere colonne diverse, campi combinati, celle unite entro un difetto, blocchi verticali ripetibili e più tabelle, anche sullo stesso foglio. I piè di pagina vengono spostati quando serve spazio. I campi mancanti confluiscono in una cella descrittiva disponibile; le chiavi del difetto vengono compilate soltanto quando la corrispondenza con il testo originale è univoca. Se il cliente non fornisce alcun formato, viene usata la tabella di fallback a 18 colonne già concordata. Non si sostituisce silenziosamente un formato cliente non compreso. Report con regioni sovrapposte o celle unite che attraversano più difetti richiedono chiarimento. Le formule mantenute sono esportate come valori salvati; non viene certificata l'esecuzione di macro o calcoli esterni.

Per questa versione occorre scaricare il nuovo componente Windows: la web app impedisce l'avvio con versioni precedenti alla 0.5.0. Le tre modalità, i log diagnostici e il contatore token restano disponibili. La lettura usa ancora un budget massimo di 60 chiamate; i prompt sono suddivisi anche per quantità di testo e immagini.

**Aggiornamento 0.4.1:** riscaricare il componente Windows, chiudere quello precedente e aprire il nuovo eseguibile. In **Diagnostica e log errori** si possono visualizzare e scaricare i tentativi di collegamento ADB, le porte rilevate e gli errori. Il registro locale ruota automaticamente e non include materiali del progetto, prompt o credenziali. In **Opzioni collegamento MuMu** è possibile indicare la porta ADB locale e, con più dispositivi, il serial. La selezione viene mantenuta nel progetto eseguito; non si modifica più un JSON a mano.

Il **contatore token** comprende lettura Excel e testing, distingue input/output/cache e si aggiorna dopo ogni chiamata in base ai dati restituiti da Codex. La cache è un sottoinsieme dell'input, non viene sommata una seconda volta. Chiamate in corso o fallite senza metriche rendono esplicito che il conteggio è parziale. Non misura la quota residua dell'account e non aggiunge chiamate GPT.

**Sito:** https://lqa-pilot-web.vercel.app — usare Chrome o Edge per il collegamento al PC. Il browser integrato in Codex può lasciare in sospeso la richiesta di accesso alla rete locale.

Aprire la web app pubblicata su Vercel e scaricare il componente Windows dal collegamento **È la prima volta?**. Estrarre tutto lo ZIP, aprire **LQA Pilot.exe**, quindi premere **Collega e apri la web app** e inserire il codice mostrato. Servono MuMu con il gioco installato e Codex con il proprio account ChatGPT. Python, PowerShell e il prompt non servono con questo pacchetto. Ogni operatore usa il proprio account e la propria quota; nessuna credenziale è distribuita.

Nel browser consentire l'accesso alla rete locale quando richiesto. Il componente rimane sul PC perché deve controllare l'emulatore; Vercel ospita l'interfaccia statica. Lasciare aperti il componente e MuMu durante il lavoro. La web app non ospita l'emulatore e non elimina la quota dell'account Codex.

Caricare l'Excel, scegliere lingua e modalità, rilevare il gioco aperto e premere **Analizza Excel e avvia**. L'importazione legge le righe dei fogli, conserva la provenienza dei test case e considera le immagini incorporate. Le istruzioni del documento sono materiali del progetto, non comandi di sistema. Non vengono creati test dimostrativi in sostituzione di obiettivi mancanti.

Con **Check completo** e **Check veloce** il solo download è un Excel con le bug list originali del cliente, anche quando i bug testuali e grafici hanno fogli distinti. Intestazioni, stili e larghezze restano quelli originali. Le righe di esempio nell'area dati vengono sostituite dai risultati. Commenti e fix sono in inglese, con screenshot annotati per i bug; Pass non ha screenshot o commenti. Un controllo non completato resta Incomplete. **Solo video** mantiene un MP4 per journey/obiettivo; i percorsi incompleti vengono indicati nella UI.

Limiti di elaborazione: massimo 30 MB, 40 fogli e 45.000 celle non vuote. I gruppi di lettura sono limitati anche a 12 immagini e alla quantità di testo; nessuna riga viene troncata silenziosamente. Una singola riga eccezionalmente estesa, un formato sovrapposto o informazioni essenziali mancanti producono un errore esplicito. Le formule dei fogli conservati vengono convertite nei valori salvati e le convalide dipendenti da altri fogli vengono rimosse. Le formule essenziali prive di valori salvati richiedono prima il ricalcolo in Excel. Un formato troppo stretto per testo completo e screenshot nella stessa cella richiede spazio dedicato. Video esterni e collegamenti a materiali non incorporati non vengono scaricati automaticamente.

I file operativi restano nella cartella locale `%LOCALAPPDATA%\LQA Pilot\jobs`. Sono necessari al bot, ma non vengono offerti come output aggiuntivi dalla web app. Il materiale necessario all'analisi è inviato a GPT tramite Codex. Le funzionalità CLI descritte sotto rimangono disponibili per chi usa il pacchetto sorgente.

## Installazione del pacchetto sorgente su Windows

Estrarre l'intero ZIP in una cartella scrivibile. Installare MuMu Player e il gioco, Python 3.11+ e Codex (app desktop oppure CLI). Eseguire `Setup.cmd`: crea un ambiente Python locale e installa le dipendenze pubbliche. Non richiede privilegi amministratore se i prerequisiti sono già installati. Connessione Internet necessaria per installazione e GPT.

Ogni operatore esegue **`Start.cmd login` con il proprio account ChatGPT**. Se Codex è già autenticato con l'account corretto, questo passaggio non serve. Il pacchetto non contiene login, token, chiavi o sessioni di chi lo ha creato. L'account deve avere accesso a Codex e ai modelli configurati; quota e disponibilità appartengono a quell'account. `doctor` verifica il login locale, non presume che tutti gli account abbiano gli stessi modelli.

`Start.cmd doctor --project projects/cliente/project.json --probe-models` prova anche l'accesso ai modelli e ai livelli di reasoning configurati con brevi richieste che consumano quota. Se un account non li supporta, indicare nel progetto un modello disponibile; il bot non sostituisce silenziosamente il modello scelto.

I percorsi vengono rilevati dall'utente Windows corrente, dal PATH e dall'installazione MuMu; è possibile specificare `device.adb` e `codex.executable` per installazioni non standard. La porta ADB della VM viene rilevata, senza fissarla a quella del PC originario. Con più dispositivi indicare `device.serial`. L'Excel funziona anche senza il runtime documenti di Codex: usa automaticamente il backend pubblico openpyxl quando artifact-tool non è disponibile.

Non trasferire `.venv`: su un altro PC rieseguire `Setup.cmd`. Trasferire invece i progetti con i loro materiali e i report Excel, che incorporano le immagini.

```powershell
.\Start.ps1 pack-project projects/cliente/project.json --output cliente-portabile.zip
```

Estrarre il progetto sul nuovo PC e avviare una nuova run. `pack-project` include solo i materiali dichiarati, converte i riferimenti in percorsi relativi e rimuove i percorsi degli eseguibili e l'endpoint ADB della vecchia macchina. Le run già avviate conservano il loro ambiente originale per tracciabilità; `resume` richiede lo stesso progetto e scope.

## Avvio

Aprire MuMu, avviare il gioco e aprire un terminale nella cartella di LQA Pilot. Codex e Python vengono individuati nelle installazioni esistenti.

```powershell
.\Start.ps1 doctor --project examples/last-asylum-smoke.json
.\Start.ps1 run examples/last-asylum-smoke.json --output runs/mia-prova
.\Start.ps1 review runs/mia-prova
```

Le modalità `full` e `fast` producono **`report.xlsx`**, con un solo foglio. La modalità `video` produce un MP4 per case/journey e `videos.json`. `review` apre un'anteprima HTML facoltativa dei risultati LQA; il server ascolta solo su `127.0.0.1` e Ctrl+C lo chiude.

## Tre modalità nello stesso bot

Selezionare `mode` nel progetto (`full` di default) oppure `--mode` nel comando. L'opzione del comando prevale. Usare una cartella nuova per ogni modalità; `resume` richiede la stessa modalità dell'avvio.

```powershell
.\Start.ps1 run projects/cliente/project.json --mode full --output runs/completa
.\Start.ps1 run projects/cliente/project.json --mode fast --output runs/veloce
.\Start.ps1 run projects/cliente/project.json --mode video --output runs/video
```

| Modalità | Controlli | Reasoning Astra predefinito | Output |
|---|---|---|---|
| `full` | Analisi LQA completa dello scope, verifica dei candidati e audit | Navigazione low; analisi/audit medium; verifica high | Excel, un foglio |
| `fast` | Difetti UI, typo inequivocabili, errori gravi di significato, terminologia da glossario e rischi reputazionali concreti | Navigazione e analisi/verifica/audit low | Excel, un foglio |
| `video` | Solo navigazione e controllo della copertura del percorso | Navigazione e audit del percorso low; nessuna analisi/verifica LQA | Un MP4 per case/journey |

La navigazione, gli obiettivi, gli scroll e i controlli di freschezza dello schermo restano gli stessi. La modalità veloce riduce l'effort dell'analisi, non le sezioni da visitare. Ignora stile, spazi, trattini, formulazioni poco naturali e grammatica che non compromette il senso. Le inconsistenze sono ammesse solo con una voce corrispondente in un glossario fornito, ad esempio `"glossary": {"army": "Armee"}`. `Pass` in questa modalità riguarda soltanto questi controlli ridotti.

Per tedesco/russo e ambientazioni della Seconda Guerra Mondiale, specificare contesto e requisiti del cliente in `content_policy`. Il bot distingue descrizione storica da approvazione di contenuti lesivi: un nome storico da solo non dimostra un errore. Non inventa divieti legali e non certifica la conformità legale.

La modalità video registra realmente il display Android durante il percorso, senza costruire slideshow. Ogni elemento di `cases` corrisponde a un journey/obiettivo e a `videos/<case-id>.mp4`. Non emette Pass né bug: `videos.json` distingue `RECORDED` da `INCOMPLETE`, conserva il motivo dei blocchi e l'eventuale video parziale. Per un unico video, definire il journey in un unico case. Le aree vanno mostrate e fatte scorrere anche quando non vengono analizzate.

Registrazione senza audio, lato lungo massimo 1920 px, bitrate 8 Mbps. Configurare `"video": {"max_dimension": 0, "bit_rate": 8000000}` per la risoluzione nativa, se supportata dall'encoder Android. I segmenti vengono uniti automaticamente in un MP4; durante il rinnovo della registrazione gli input sono sospesi. Brevi intervalli non registrati sono dichiarati nel manifest: il gioco può continuare ad animarsi. Alla ripresa i nuovi segmenti vengono aggiunti al video precedente. Le registrazioni Android richiedono `screenrecord`; FFmpeg è incluso nella dipendenza pubblica `imageio-ffmpeg`. Non è stato effettuato un nuovo collaudo nel gioco di questa modalità, rispettando la richiesta di arresto dei test.

Per la dimostrazione tedesca di Last Asylum sono inclusi `examples/setup-german.json` e `examples/last-asylum-german-text-menus.json`. Il primo serve solo a raggiungere i menu e cambiare lingua; non genera esiti LQA sul tutorial:

```powershell
.\Start.ps1 setup-game examples/setup-german.json --output runs/preparazione-de
.\Start.ps1 run examples/last-asylum-german-text-menus.json --output runs/menu-de --no-launch
```

Avviare il secondo comando dopo che il setup risulta `setup_complete`. Il setup può essere ripreso con lo stesso comando e `--resume`, conservando il budget consumato. Blocchi e prerequisiti non risolti rimangono espliciti; non viene certificata una lingua mai raggiunta.

Requisiti su altri PC: Python 3.11+, dipendenze installate da `Setup.cmd` (oppure `python -m pip install -e .`), Codex CLI con login ChatGPT e MuMu con ADB accessibile. FFmpeg viene rilevato dal PATH o da imageio-ffmpeg; è anche configurabile con `ffmpeg` per i materiali e `video.ffmpeg` per le registrazioni. Configurare il package del gioco già installato. `doctor` verifica collegamento e autenticazione; con più dispositivi specificare `device.serial`.

## Creare un progetto reale

```powershell
.\Start.ps1 init projects/cliente
```

Compilare `projects/cliente/project.json`: package, lingua, obiettivi, test case, eventuali materiali e cheat. Ogni case contiene un obiettivo e controlli con `id`, `scope`, `instruction`, `modality`. Il completamento deve essere osservabile: «tutte le tab del pannello X, scroll incluso» è verificabile; «tutto il gioco» senza confini non lo è. Si possono avere più controlli per case e più case per progetto. Non vengono accorpati case diversi perché hanno lo stesso nome.

Per far elaborare al bot obiettivi, journey testuali, screenshot o video:

```json
{
  "goals": ["Trovare il menu alleanza e verificarne i testi"],
  "materials": [
    {"path": "journey.md"},
    {"path": "riferimento.png"},
    {"path": "percorso.mp4", "sample_every_seconds": 2},
    {"path": "test-case.xlsx", "sheet": "Test case"}
  ],
  "cheats": [
    {"id": "unlock_menu", "enabled": true, "instructions": "Istruzioni fornite dal cliente per usare il menu cheat in-game"}
  ]
}
```

Sono campi da inserire nel progetto, non un file completo. Se si vogliono generare i case dagli obiettivi, rimuovere i case di esempio prima di `prepare`. I case espliciti già presenti vengono conservati integralmente.

```powershell
.\Start.ps1 prepare projects/cliente/project.json --output projects/cliente/prepared
.\Start.ps1 run projects/cliente/prepared/project.json --output runs/cliente-001
```

I video vengono campionati automaticamente ogni 2 secondi (configurabile). È possibile specificare `timestamps_seconds` per passaggi precisi. I frame vengono elaborati in gruppi, poi viene composto il piano; il manifest conserva timestamp, hash e limiti del campionamento. L'audio dei video non viene trascritto. Passaggi molto brevi potrebbero richiedere un intervallo minore: il piano conserva questa limitazione e non afferma di aver letto ogni fotogramma. Oltre 180 frame per materiale viene richiesto di suddividere il progetto o modificare l'intervallo, senza eliminare la parte finale in silenzio. Screenshot/video di riferimento descrivono il percorso; le prove del risultato provengono sempre dalla run effettiva.

I cheat sono solo quelli esplicitamente abilitati nel progetto. Sono istruzioni per il menu del gioco, eseguite una schermata alla volta e soggette alla stessa policy. Il bot non inventa comandi, non esegue shell descritte nei documenti e non applica hack al processo del gioco. Funzioni nuove possono essere raggiunte esplorando etichette e icone anche senza journey.

## Modello scelto dopo la prova

Default della modalità completa: **GPT-6 Astra**, reasoning **low** per navigare, **medium** per piano/analisi/audit, **high** per la verifica dei candidati. Le altre modalità applicano i livelli indicati nella tabella sopra; `fast` forza low nei ruoli di analisi/verifica/audit. La scelta del navigatore riprende il collaudo precedente, senza nuovi benchmark. Vedere `VALIDAZIONE.md`: i confronti precedenti riguardano un campione piccolo.

Quando l'avanzamento di gioco è autorizzato e si accumulano movimenti senza arrivare a una schermata da analizzare, il navigatore passa temporaneamente a reasoning high. Poi torna al livello configurato. Questo aiuta a pianificare il percorso in presenza di ostacoli; il movimento libero con joystick resta molto più lento della consultazione dei menu. Le escalation sono registrate nel log e nei metadati delle chiamate. `adaptive_navigation: false` disattiva questa scelta automatica.

Ogni ruolo è configurabile senza cambiare codice:

```json
"codex": {
  "timeout_seconds": 180,
  "models": {
    "navigate": {"model": "gpt-6-astra", "reasoning": "low"},
    "analyze": {"model": "gpt-6-astra", "reasoning": "medium"},
    "verify": {"model": "gpt-6-astra", "reasoning": "high"}
  }
}
```

La navigazione usa un'immagine ridotta; l'analisi riceve le immagini originali e la verifica un ritaglio a risoluzione nativa. Il modello vede una memoria sintetica del percorso, non l'intera registrazione a ogni tocco. Le chiamate sono isolate, hanno JSON Schema e un contatore persistente; nei metadati rimangono tempi e token restituiti da Codex. Le chiavi API nell'ambiente non vengono passate al processo e il login deve risultare ChatGPT.

## Quando un test è PASS

Il navigatore può proporre di terminare, **non assegnare PASS**. Prima vengono analizzati i controlli applicabili con prove reali; un secondo passaggio verifica i bug candidati; un audit confronta scope/journey, screenshot e storico. Il programma assegna l'esito:

| Risultato | Significato |
|---|---|
| PASS | Tutti i controlli richiesti hanno prove leggibili, nessun bug o dubbio irrisolto, audit completo e nessun blocco. |
| BUG | Almeno un difetto confermato dalla verifica. La copertura, completa o parziale, è indicata separatamente. |
| INCOMPLETE | Percorso bloccato, contenuti non visti/non leggibili, candidato incerto, budget esaurito o capacità non disponibile. Non è PASS. |

Un PASS riguarda lo scope scritto nel case, non l'intero gioco. L'audit è anch'esso basato su GPT e non fornisce una garanzia matematica di assenza di errori; il risultato resta da revisionare. L'accuratezza della traduzione rispetto alla sorgente non può essere certificata senza sorgenti/glossario. I controlli audio restano incompleti in questa versione. La raccolta delle schermate è automatica; non serve registrare un video continuo per eseguire LQA testuale.

## Risultati e template cliente

`report.xlsx` contiene soltanto **Bug list**, con le 18 intestazioni originali del cliente e nello stesso ordine. Nessuna copertina, foglio riepilogativo o colonna aggiuntiva.

- **Pass**: nome/ID della sezione e label `Pass` in `LQA Status`; nessuna immagine o commento.
- **Bug**: tipo del cliente, testo integrale, commento inglese in una frase (massimo 220 caratteri) e fix completo nella lingua target. La cella `Error Description & Suggestion` usa tre righe: `Text`, `Issue`, `Fix`. Lo screenshot completo è incorporato nella colonna `Screenshot`; il riquadro rosso non copre i pixel del testo. Per overflow: alternativa breve senza perdita d'informazioni, oppure riduzione del font.
- **Incomplete**: sezione non completata; i dettagli restano nei dati della run. `Bug (partial)` segnala bug trovati senza completare l'intero scope. Nessun Pass viene assegnato a sezioni non viste.

Per selezionare risultati da ricontrollare scegliere **`Recheck` in `LQA Status`**, scrivere eventuali note in **`Localizer Notes`**, salvare l'Excel e lanciare:

```powershell
.\Start.ps1 recheck runs/cliente-001/report.xlsx --run runs/cliente-001 --output runs/ricontrollo-001
```

Di default il bot **rianalizza le prove originali**, evitando la navigazione. Le date restano quelle delle acquisizioni originali; origine e modalità del riesame sono conservate nella run. Per raccogliere prove fresche navigando di nuovo nel gioco aggiungere **`--live`**. Più bug dello stesso caso producono un solo ricontrollo dello scope del caso. `--prepare-only` crea il progetto selezionato senza chiamare GPT. Il Run ID nelle proprietà interne dell'Excel verifica la corrispondenza con la run, senza aggiungere celle. Le note sono dati da valutare, non comandi. Rigenerando un report viene conservata una copia del precedente in `review-backups`. È mantenuta l'importazione dei vecchi report a tre fogli.

Per far eseguire il ricontrollo a un collega, trasferire l'Excel modificato **insieme all'intera cartella della run**. Dalla versione 0.2 le immagini dei journey necessarie sono copiate in `references` dentro la run: il ricontrollo le risolve nella nuova posizione e rileva nuovamente Codex/ADB con l'account e la macchina del collega. Le vecchie run senza questa cartella richiedono anche i materiali originali.

**Origine dei case dimostrativi:** i progetti Last Asylum inclusi sono stati definiti da noi per collaudare il workflow. Non sono i test case del cliente. La classificazione degli errori e le 18 colonne provengono invece dal template fornito. Nei progetti reali gli obiettivi devono provenire dal progetto/cliente; eventuali case generati da GPT riportano assunzioni e origine.

- `review.html`: revisione visuale, esiti, controlli, bug, immagini e pulsanti di copia.
- `bugs.tsv`: 18 colonne nell'ordine del Bug list del template allegato.
- `bugs_paste.tsv`: stesse righe senza intestazione, pronte per l'incolla.
- `test_results.tsv` e `test_results_paste.tsv`: riepilogo case con copertura e blocchi.
- `results.json`: dati strutturati, inclusi candidati incerti.
- `run.json`, `events.jsonl`, `evidence/`, `model/`: stato, percorso, prove originali e richieste/risposte/metriche del modello.

La tassonomia predefinita contiene i **42 sottotipi effettivamente letti dal file Excel fornito**. Categoria, priorità T0/T1/T2 e assegnatario derivano da quel sottotipo; GPT non inventa severità. Un progetto può specificare una tassonomia JSON diversa con `taxonomy`. Se manca, viene usata quella fornita e inclusa nel bot. Non viene ricostruita una tassonomia di un altro cliente da supposizioni.

```powershell
.\Start.ps1 taxonomy "C:\percorso\template.xlsx" --output projects/cliente/taxonomy.json
```

Il comando importa il foglio `Bug types` del formato osservato; per layout diversi si usa un JSON con gli stessi campi. Le immagini si incollano separatamente dai testi. Relazioni, checkbox e colonne lookup di WeCom non sono normali celle Excel: il bot produce i valori per la revisione, senza fingere di aver ricreato i tipi nativi della smart table. Le colonne gestite dal cliente restano vuote.

## Arresto, ripresa e limiti operativi

Ctrl+C interrompe il processo; si può anche creare un file chiamato `STOP` nella cartella della run. Il controllo avviene ai confini delle chiamate e prima delle azioni successive. Per riprendere, rimuovere `STOP` e usare:

```powershell
.\Start.ps1 resume projects/cliente/prepared/project.json --output runs/cliente-001 --no-launch
```

Si mantiene il budget già consumato. Il bot osserva nuovamente lo schermo: non ripete un tocco rimasto in stato incerto durante un'interruzione. Modificare scope, tassonomia o configurazione richiede una run nuova. Un lock impedisce due run concorrenti sulla stessa seriale. Un controllo della schermata corrente riduce i tocchi su finestre cambiate durante l'attesa di GPT. Il nome del package viene verificato prima di inviare input.

La policy permette navigazione e, se `allow_game_progress` è true, avanzamento con risorse ordinarie rinnovabili del tutorial. Acquisti, spese premium, messaggi, reset e gestione account non sono previsti. La classificazione del rischio dipende anche dal modello; i controlli di coordinate/package non sono una prova semantica del contenuto di un pulsante. In una build di testing è opportuno usare un account di prova. L'inserimento tramite `adb input text` è limitato all'ASCII: l'Unicode richiede un IME dedicato e viene bloccato esplicitamente invece di dichiarare superato un test errato.

Non sono implementati: combattimento in tempo reale ad alta frequenza, audio LQA, confronto garantito con sorgenti non fornite, pubblicazione WeCom, ripristino automatico di salvataggi o installazione APK. Il workflow iniziale si concentra su navigazione di interfacce e analisi visuale. Blocchi di login, server o tutorial vengono riportati, non mascherati.

## Verifica del software

```powershell
python -m unittest discover -s tests -v
.\Start.ps1 demo --output runs/demo
.\Start.ps1 benchmark runs/last-asylum-terra --output runs/confronto
```

`demo --gpt` verifica invece un refuso sintetico con GPT reale, fino alla riga bug finale.

`demo` è un test deterministico con schermate sintetiche e modelli finti: verifica che PASS/BUG/INCOMPLETE, prove e tabella siano gestiti correttamente, senza consumare quota. `benchmark` usa invece GPT reale e riporta le risposte integrali, i tempi e controlli sintetici con esito noto. Non invia tocchi Android. La prova MuMu è distinta da entrambe.
