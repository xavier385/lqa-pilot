# Collaudo del 18 settembre 2026

## Aggiornamento 0.6.0 — progetti generici e avvio del gioco (20 settembre)

95 test software locali superati. Verificati upload HTTP a blocchi di 31 MB, lettura di 42 fogli con una cella alla riga 50.000/colonna 250, obiettivi senza bug list, report semplice con sole chiavi presenti, fallback per report non utilizzabile e registrazione attiva prima dell'apertura del gioco. Nessun limite fisso sul peso dell'XLSX; RAM e disco restano risorse finite. Le parti non modificate dell'export vengono copiate in streaming.

Prova reale espressamente richiesta: creato un Excel a un solo foglio/una colonna con tre obiettivi dimostrativi (tutorial, impostazioni, menu informativo). Due chiamate GPT hanno riconosciuto i tre obiettivi senza glossario, chiavi o bug list. Il launcher ha trovato Last Asylum dal nome e aperto il package `com.phs.global`. Corretto il riconoscimento quando MuMu esegue l'app in un profilo Android diverso da quello predefinito; corretto anche il rilevamento della porta nel campo `port_forward.adb.host_port`.

Il gioco mostrava il consenso iniziale. Il bot ha selezionato Deutsch, poi si è fermato prima di accettare le condizioni. La revisione automatica ha richiesto autorizzazione esplicita per i termini obbligatori. Tutorial e menu restano INCOMPLETE: questa prova non ne certifica la copertura. Il report semplice è stato generato con gli esiti incompleti. L'opzione `allow_required_terms` è disattivata per default, può essere abilitata soltanto dall'operatore e non abilita pubblicità personalizzata o altri consensi facoltativi.

Consumo fino alla sospensione: 2 chiamate di importazione e 4 di testing, 95.242 token complessivi comunicati da Codex (cache 0). Nessuna seconda lettura dell'Excel durante la correzione del riconoscimento MuMu. La correttezza su ogni possibile workbook o launcher Android non è garantita da questi test.

## Aggiornamento 0.5.0 — importazione adattiva (20 settembre)

87 test software locali superati, senza GPT reale né azioni Android. Fixture con foglio misto in nome non latino, intestazione report alla riga 70, guide/glossario/dev key/log key, assenza di formato cliente con fallback, note e collegamenti, gerarchie unite, schede verticali ripetute, espansione prima del footer e più tabelle sullo stesso foglio. Verificati blocco prima della creazione del driver in caso di importazione incompleta e Pass senza screenshot/commenti. L'export viene provato prima della navigazione con evidenze sintetiche private, mai incluse nei risultati del gioco.

Le fixture verificano flusso, provenienza, mapping e integrità del report; non dimostrano che GPT interpreterà correttamente ogni workbook futuro. La qualità semantica della nuova fase di lettura/riconciliazione non è stata collaudata con chiamate GPT reali, rispettando il limite di consumo chiesto dall'utente. File ambigui, riferimenti indispensabili inaccessibili e strutture che il generatore non può conservare vengono segnalati prima del testing, senza inventare scope o risultati.

## Aggiornamento 0.4.1 — diagnostica e token

Verifiche con dispositivi e modelli simulati: rilevamento vuoto, offline/non autorizzato, porta manuale anche con altro dispositivo già collegato, configurazioni VM malformate, protezione del log con pairing/origine, oscuramento segreti, rotazione log, totale token senza doppio conteggio cache, metriche mancanti e conservazione del consumo di importazioni fallite. Nessun nuovo test nel gioco o richiesta GPT. Il problema specifico del PC del collega richiede il nuovo log per determinarne la causa.

## Aggiornamento 0.3.0: formato semplice e tre modalità

Questa revisione è stata verificata solo sul software locale: **60 test unitari superati**, fixture sintetiche con modelli finti, nessuna nuova chiamata GPT o azione MuMu. Le prove reali documentate sotto appartengono alle versioni precedenti.

- Excel con un solo foglio, le 18 intestazioni del template WeCom, immagini native nella colonna Screenshot, commenti inglesi in una frase e Pass senza immagini/commenti.
- Importazione di Recheck e conservazione del Run ID interno dopo un normale salvataggio Excel verificate su un file esportato; compatibilità con i vecchi report conservata.
- Modalità veloce: filtri su spazi/trattini/stile, glossario obbligatorio per inconsistenze, effort low, mantenimento degli esiti incompleti per dubbi su errori ammessi.
- Modalità video: pipeline separata dall'analisi LQA nello stesso motore, un percorso video per case, controlli sulla chiusura del recorder e sulla registrazione parziale. I test sostituiscono Android/encoder con fixture: **la nuova registrazione MP4 non è stata collaudata dal vivo**, come richiesto dall'utente.
- Il report tedesco semplificato riutilizza le tre segnalazioni della run precedente e cambia soltanto presentazione/commenti. Non rappresenta un nuovo collaudo né una run fast; spaziatura, trattino e formulazione comprensibile ma poco naturale sono esclusi dalla nuova modalità veloce.

Questa è una prima versione funzionante, collaudata su MuMu e su fixture controllate. Non è una certificazione dell'intero Last Asylum né una validazione sulla futura APK del cliente, che non è stata fornita.

## Ambiente verificato

- Windows, MuMu Player, unica VM esistente.
- ADB locale `127.0.0.1:16384`, Android 12, modello emulato SM-S938U.
- Last Asylum: Plague ufficiale, package `com.phs.global`, versione Android 1.0.103, versionCode 103.
- Screenshot nativi del gioco: 2160 × 3840; launcher iniziale 3840 × 2160.
- Codex CLI autenticato tramite ChatGPT. Nessuna API key utilizzata dal bot.

## Scelta del modello

Confronto controllato di Terra e Astra con gli stessi prompt e immagini: due schermate reali (consenso iniziale, timeout) e due schermate sintetiche (testo corretto, refuso noto).

| Misura | GPT-5.6 Terra | GPT-6 Astra |
|---|---:|---:|
| Reasoning navigazione | low | low |
| Tempo mediano per decisione sui due screenshot | 12,55 s | 13,66 s |
| Reasoning analisi | medium | medium |
| Tempo mediano per analisi dei due fixture | 7,36 s | 10,15 s |
| Fixture classificati correttamente | 1/2 | 2/2 |

**Osservazioni verificate visivamente:** sul dialogo di timeout il pulsante OK si trova circa a `(0,50; 0,537)`. Astra ha proposto `(0,50; 0,536)`; Terra `(0,50; 0,715)`, fuori dal pulsante. Nel fixture con `Notifictions`, Terra ha trascritto `Notifications` e dichiarato clear, mentre Astra ha letto il refuso e proposto la correzione giusta. Entrambi non hanno segnalato bug nel fixture corretto.

Il campione è piccolo e diagnostico, non sufficiente a stimare precisione/recall generale o consumo dell'abbonamento. Le latenze includono avvio del processo Codex, ma non il ciclo completo ADB/attese. I benchmark sintetici non equivalgono a test su una build del cliente. Non sono stati effettuati centinaia di retry per selezionare una risposta favorevole.

**Decisione:** Astra low per navigare, medium per piano/analisi/audit, high solo per verifica dei candidati. Dati riproducibili in `runs/model-benchmark/benchmark.json` e `summary.json`. I modelli effettivi e i tempi sono registrati in ogni file `model/*.meta.json`.

## Navigazione reale

La prima run Astra ha gestito la riconnessione, dialoghi introduttivi, attese, il braciere del tutorial e un tentativo di movimento. Ha anche aperto la conferma di uscita tramite Indietro e l'ha richiusa con Cancel: questo è un percorso improduttivo osservato, non un successo da conteggiare.

- 25 richieste di navigazione; mediana 10,92 s, intervallo 9,52–14,97 s.
- 24 azioni tentate, di cui 23 eseguite e una fermata dal controllo di schermata cambiata. Il conteggio include attese e non misura automaticamente il successo semantico di ogni gesto.
- 427,33 s complessivi.
- I case «impostazioni» e «profilo» non sono stati completati: il tutorial obbligatorio impediva l'accesso. Nessun PASS è stato emesso per quei case.

La policy iniziale trattava anche la costruzione del tutorial con 10 gettoni base come spesa bloccata. È stata corretta distinguendo risorse ordinarie di avanzamento, ammesse solo con `allow_game_progress`, da acquisti/valuta premium. La run originale è conservata come incompleta; non è stata riscritta retroattivamente come successo.

Nel primo tentativo con Terra è stato premuto **Agree to all** nel consenso iniziale, comprendente annunci personalizzati facoltativi. Questa scelta non era necessaria per il test. Il bot ora blocca quel pulsante e richiede la gestione minima dei consensi. L'impostazione facoltativa non è stata verificata o ripristinata dai menu del gioco, ancora non raggiunti nel collaudo. Nessun acquisto, invio chat o modifica manuale di account è stato eseguito.

## Analisi reale completata

Run `runs/last-asylum-reading`, scope definito prima dell'esecuzione:

| Case | Scope | Esito |
|---|---|---|
| LA-TEXT-01 | Tutti i testi e contatori visibili della schermata Build Ward | PASS |
| LA-TEXT-02 | Raggiungere il nuovo pannello successivo a Build Ward e leggerlo integralmente | PASS |

La seconda schermata è stata raggiunta con due gesti di movimento; sono stati letti titolo `Plague Doctor`, l'intera frase del dialogo, `Tap to Continue` e l'etichetta `Lv.1`. Il comando Tap to Continue appare solo nel secondo frame: l'analisi l'ha trattato come una comparsa temporale, senza inventare un bug di testo mancante. Gli screenshot originali e l'audit sono consultabili nel report.

- 146,98 s, 8 chiamate GPT, 2 gesti, nessun input scartato dal controllo di schermata.
- 4 decisioni: mediana 12,39 s.
- 2 analisi: mediana 20,20 s.
- 2 audit: mediana 15,32 s.
- Nessun bug confermato e nessun candidato incerto nei due scope.
- Contatori restituiti da Codex: 141.175 token input, dei quali 30.720 cached; 2.028 output. Non equivalgono a un importo API né a una percentuale deducibile della quota ChatGPT.

Questi PASS non coprono profilo, impostazioni, altre lingue, audio, menu futuri o l'intero tutorial.

## Verifica del percorso di un bug

Oltre al confronto iniziale, è stata eseguita una run completa con **GPT reale** su una schermata sintetica con il refuso `Notifictions`:

- rilevamento con Astra medium;
- verifica del frame originale, ritaglio e secondo frame con Astra high;
- audit di copertura con Astra medium;
- risultato BUG con copertura complete, correzione `Notifications`, sottotipo del cliente `client-r19`, priorità T2;
- 4 chiamate, 54,47 s;
- riga TSV con 18 colonne e prove generate dal programma.

Report in `runs/verified-synthetic-bug`. È una prova software esplicitamente etichettata: il refuso non è stato trovato in Last Asylum.

## Altre verifiche

- Suite `unittest`: **48 test superati**; controlli contro falsi PASS, prove mancanti, budget/ripresa, JSON e coordinate non validi, spese vietate, app cambiata, screenshot cambiato, input Unicode non supportato, esportazione TSV, dispositivo scollegato, pipeline offline con tre esiti, portabilità e ricontrollo Excel.
- Video sintetico di 4 secondi: estrazione automatica dei frame a 0 e 2 secondi, senza timestamp forniti; piano generato da GPT e caricato come progetto valido.
- Importazione dal template reale: 42 sottotipi, categorie, priorità e assegnatari.
- Report provato nel browser: copia riga → 18 celle negli appunti; copia screenshot → `image/png`; apertura delle prove; impaginazione verificata visivamente.
- Pacchetto wheel costruito senza scaricare dipendenze durante la build.

## Aggiornamento 0.2.0: Excel e portabilità

- `Setup.cmd` collaudato dopo estrazione dello ZIP in una cartella distinta: ambiente virtuale nuovo, installazione delle dipendenze pubbliche e avvio tramite `Start.ps1`.
- Dalla copia installata è stata eseguita la demo offline con tre esiti attesi: Pass, Bug e Incomplete. Il report `.xlsx` incorpora lo screenshot a risoluzione originale.
- Backend artifact-tool verificato in questa postazione; backend openpyxl esercitato nei test sotto un profilo temporaneo senza runtime documenti Codex.
- Importazione verificata su un Excel realmente esportato, modificando una sola selezione `Ricontrollare`: il nuovo progetto contiene soltanto il caso selezionato. Run ID errato, ID sconosciuti e bug simulati vengono rifiutati.
- Verifica dei pixel: il riquadro rosso viene disegnato fuori dall'area del testo; tutti i pixel interni sono identici all'originale, anche quando il testo è vicino al bordo della schermata.
- I Pass hanno solo identità della sezione e label Pass: campi commento/revisione vuoti e nessuna immagine.
- Layout renderizzato e controllato; la libreria di anteprima non mostra le immagini incorporate, che sono state verificate separatamente nel contenitore Excel, nella posizione corretta e alla risoluzione originale.
- Rilevamento locale di Codex/MuMu e verifica di accesso ad Astra low, medium e high riusciti. Nessun login/account è incluso nel pacchetto; le variabili API vengono escluse dal processo GPT.

La prova in un'altra cartella è stata fatta sullo stesso PC e con lo stesso account reale. Il rispetto del profilo dell'operatore è verificato da test isolati; non è stata eseguita una prova con credenziali di un collega né su un secondo PC fisico. Modelli e quote dipendono dall'account che esegue il bot.

## Bug reale e ricontrollo dall'Excel

Il popup di aggiornamento inglese, acquisito autonomamente in due schermate durante la preparazione, contiene «New version available. Tap Confirm to update.» ma il pulsante si chiama «OK». La verifica GPT ha confermato l'incoerenza e proposto la frase completa «New version available. Tap OK to update.». È un difetto reale del popup, non un refuso aggiunto alla schermata. Lo sfondo del tutorial è escluso dallo scope.

- Run `runs/update-popup-reviewed`: un bug, copertura completa del solo popup, 5 chiamate GPT incluse due verifiche, 72,08 secondi di elaborazione registrati, nessun input al gioco durante l'analisi delle prove.
- Commento finale di due frasi in italiano; tassonomia `client-r23`, Translation/Wording Inconsistency, priorità T1 derivata dal template.
- Excel con screenshot completo 2160 × 3840 incorporato, rettangolo rosso esterno alla frase; originali, ritaglio e screenshot annotato conservati.
- Su una copia del report è stata selezionata automaticamente una sola riga `Ricontrollare` per provare l'importazione; non si tratta di una scelta fatta da un revisore umano.
- Run `runs/update-popup-recheck/run`: 3 chiamate GPT, 42,34 secondi, zero azioni Android. Analisi, verifica e audit sulle prove originali hanno riconfermato il bug e mantenuto le date di acquisizione originali.

Questa prova verifica il ricontrollo di un risultato e non equivale a ritestare una build successiva; per quello serve `recheck --live`. Non è una prova in tedesco o russo.

## Correzione del controllo delle animazioni

Durante il setup, la mano animata del tutorial copriva a intermittenza il pulsante di assegnazione al Lumberyard. Il controllo di freschezza respingeva il clic. Ora ripete fino a tre acquisizioni prima di rinunciare, mantenendo la stessa soglia di corrispondenza e ricontrollando package e orientamento a ogni tentativo. Se il bersaglio resta diverso, nessun input viene inviato. I test verificano sia il ritorno del bersaglio originale sia il cambio di app durante il retry. Nella prova reale il primo e il secondo pulsante prima bloccati sono stati raggiunti rispettivamente al primo e al secondo retry.

Restano da collaudare su una build di testing: navigazione estesa e ricerca di moduli profondi, scroll lunghi, login/sessioni scadute, cheat reali forniti dal cliente, più lingue e un campione ampio di bug UI e linguistici. La copertura di sezioni mai raggiunte rimane incompleta. Non sono implementati LQA audio o gioco in tempo reale ad alta frequenza.

## Preparazione della lingua tedesca completata

La preparazione ha raggiunto il profilo e le impostazioni, selezionato Deutsch e confermato il riavvio. Una nuova acquisizione mostra Arzt-Info, Konto ed Einstellungen: audit di setup completato, distinto da un esito LQA. Le fasi precedenti conservano i rispettivi arresti e non sono state trasformate in successi retroattivi.

Il movimento con joystick ha richiesto molte azioni ed è rimasto lento: nelle prime fasi low le mediane per decisione erano 12,31 e 12,59 secondi; nella fase high 16,67 secondi. Dopo il passaggio alla città e ai pulsanti, la fase conclusiva ha richiesto 88 chiamate e 84 tentativi di azione, in 27,40 minuti di esecuzione attiva. Questi numeri non sono un confronto a parità di scenario. I costi delle fasi precedenti si aggiungono e non devono essere omessi quando si valuta la preparazione complessiva.

Il controllo di interruzione durante una verifica è stato inoltre provato: alla ripresa un candidato senza verdetto può essere verificato dopo essere stato osservato nuovamente su una nuova coppia di frame, senza duplicare la segnalazione.

## Chiusura su richiesta dell’utente

Il collaudo dei sei menu tedeschi è stato interrotto per limitare il consumo. La run ha riservato 40 chiamate GPT (l’ultima interrotta), tentato 20 azioni e registrato 728,83 secondi attivi. Impostazioni/lingue sono state lette; notifiche push solo in parte; gli altri quattro case non sono stati eseguiti. Nessun Pass è stato attribuito alle sezioni non completate.

Il report contiene tre segnalazioni confermate dal modello: spazio dopo Version:, costruzione Offizielle Ernennung Banner e composizione Allianzmitglieder Versammlungshinweis. I candidati ON/OFF sono stati conservativamente declassati dall’assistente a incerti, senza ulteriori chiamate GPT, perché manca una regola del cliente sulle sigle UI. I verdetti precedenti rimangono nella cronologia; queste sigle sono escluse dalla tabella dei bug certi. Il nuovo filtro nel prompt non è stato ricol­laudato dal vivo dopo la richiesta di arresto.

Durante il collaudo è stato corretto anche l’audit: conserva tutte le prove dei controlli e allega i punti del percorso necessari, in anteprima ridotta. Il successivo audit reale ha riconosciuto il percorso delle impostazioni. Il ricontrollo da Excel copia e rimappa anche queste prove quando la run viene trasferita.
# Web app 0.4 — 19 settembre 2026

Pubblicata su https://lqa-pilot-web.vercel.app. Pagina e download pubblico verificati (HTTP 200). Preflight CORS e collegamento HTTP autenticato con origine Vercel verificati senza avviare lavori. Nel browser integrato Codex la richiesta verso loopback resta in sospeso: il collegamento HTTPS→PC in quel browser non è stato convalidato. La UI termina l'attesa con istruzioni per usare Chrome/Edge e autorizzare la rete locale. Il flusso completo con un Excel reale e GPT resta da collaudare, come richiesto dall'utente.

- 68 test software locali superati; modelli e dispositivi sono sostituiti da fixture. Nessuna nuova navigazione nel gioco e nessuna chiamata GPT di collaudo.
- Importazione verificata su 75 obiettivi in più gruppi di righe; una riga omessa interrompe l'importazione. La qualità della nuova classificazione GPT degli Excel non è stata collaudata con chiamate reali, rispettando la richiesta di contenere il consumo.
- Export verificato con due bug list distinte, stili originali identici, intestazioni e larghezze preservate, screenshot a risoluzione originale, Pass senza prove/commenti, testo protetto dall'interpretazione come formula e prefissi XML di compatibilità conservati.
- Interfaccia locale verificata nel browser per collegamento PC e selezione delle tre modalità. Nessun avvio di lavori reali dalla UI durante questa verifica.
- Componente Windows compilato con Python, librerie grafiche, dipendenze e FFmpeg incorporati; controllo di avvio senza MuMu/GPT superato. Restano necessari MuMu e Codex sul PC dell'operatore.
