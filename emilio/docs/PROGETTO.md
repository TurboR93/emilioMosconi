# Progetto Emilio — Documentazione completa

> Documento di riferimento per proseguire il lavoro in autonomia (sul Mac e poi
> sul robottino). Raccoglie visione, requisiti, architettura, scelte hardware,
> voce, sistema di censura e roadmap.

---

## 1. Visione

Ridare vita a **Emilio** dentro un **robottino degli anni '90**: deve **parlare**
e **muoversi** (anche in modo manuale), **simulando una persona reale** con un
carattere ben definito e comportamenti coerenti.

Riferimento di personaggio: il registro "alla **Germano Mosconi**" — italiano
verace, schietto, brontolone, spontaneo nel fuorionda — ma **ripulito** da un
sistema di supervisione che censura **parolacce e bestemmie in italiano**.

Due "cervelli" lavorano in cascata:

1. **Base LLM** — genera le risposte spontanee e in carattere.
2. **Supervisore** — controlla a valle ciò che l'LLM ha prodotto e interviene
   su volgarità e bestemmie. È un componente separato e indipendente.

---

## 2. Requisiti raccolti (dalle conversazioni)

| # | Requisito | Stato | Dove |
|---|-----------|-------|------|
| R1 | Emilio parla e (in prospettiva) si muove | ✅ base pronta | `agent.py`, `actuators.py` |
| R2 | Movimento anche **manuale** | ✅ | `cli.py` `/muovi`, `actuators.py` |
| R3 | **Simula una persona reale** con carattere | ✅ | `persona.py` |
| R4 | **Supervisore** che censura parolacce + bestemmie IT, costruito *sopra* la base LLM | ✅ | `moderation/` |
| R5 | Hardware **non performante** (Raspberry o simili) | ✅ progettato così | cloud per LLM+voce |
| R6 | Voce: **italiano molto realistico** (ElevenLabs o simili) | ✅ | `speech.py` |
| R7 | Censura **controllabile dall'amministratore**, facilmente **disattivabile** | ✅ | toggle runtime |
| R8 | Censura **conseguente nel flusso del parlato** (passaggio obbligato) | ✅ | `Moderator.process` |
| R9 | Sviluppo finale sul **Mac** dell'utente | ➡️ predisposto (tutto cross-platform) | — |
| R10 | **Repo su GitHub** + documentazione esaustiva | ✅ in corso | questo documento |

---

## 3. Architettura

```
                 ┌───────────────────────────────────────────┐
   input utente  │                 EmilioAgent                │
   (testo/voce)  │                                            │
        ─────────┼─►  brain.py        →  testo grezzo         │
                 │   (base LLM)                               │
                 │        │                                   │
                 │        ▼                                   │
                 │   moderation/      →  analisi + (eventuale)│
                 │   (SUPERVISORE)       riformulazione +     │
                 │        │              sanificazione        │
                 │        ▼                                   │
                 │   speech.py        →  voce (TTS realistico)│
                 │   actuators.py     →  movimento bocca/corpo│
                 └───────────────────────────────────────────┘
```

Principi:

- **Componenti dietro interfacce** con backend intercambiabili.
- Ogni componente ha un **backend "mock"** che gira **offline e senza chiavi**:
  si sviluppa tutto sul Mac, poi si cambia solo la configurazione per il Pi.
- **Difesa a due livelli** contro il turpiloquio:
  1. il *system prompt* della persona istruisce l'LLM a non usare turpiloquio;
  2. il *supervisore* interviene comunque sull'output (rete di sicurezza).

---

## 4. Struttura del codice

```
emilio/
├── __init__.py          API pubblica del pacchetto
├── __main__.py          avvio della console (python -m emilio)
├── config.py            configurazione (tutto da variabili d'ambiente)
├── persona.py           chi è Emilio + system prompt
├── brain.py             base LLM: ClaudeBrain (API) / MockBrain (offline)
├── moderation/
│   ├── __init__.py
│   ├── lexicon.py       elenchi: parolacce, entità divine, qualificatori, ...
│   └── engine.py        motore: normalizzazione, individuazione, sanificazione
├── speech.py            voce: ElevenLabs / pyttsx3 / mock
├── actuators.py         movimento: seriale / mock + vocabolario movimenti
├── agent.py             orchestrazione della pipeline del parlato
├── cli.py               console di controllo manuale
├── tests/
│   └── test_moderation.py
├── docs/
│   └── PROGETTO.md       (questo file)
├── requirements.txt
└── README.md
```

---

## 5. Il supervisore (parolacce + bestemmie)

È il componente su cui c'è più cura. Vive in `moderation/`.

### 5.1 Cosa riconosce

- **Bestemmie combinatorie**: entità divina (`dio`, `madonna`, `cristo`, `gesù`,
  `ostia`, ...) accostata a un qualificatore offensivo (`cane`, `porco`, `boia`,
  `ladro`, ...), **in qualunque ordine**, anche attaccati (`porcodio`) o separati
  da punteggiatura.
- **Bestemmie/espressioni fisse** non coperte dalla combinazione (`dio morto`,
  `cristo morto`, ...).
- **Parolacce** tramite radici flesse (`cazz` → cazzo/cazzi/cazzata/cazzone),
  con livelli di gravità (1 lieve → 3 forte; bestemmia = 5).

### 5.2 Robustezza (anti-evasione)

- lettere ripetute: `diooo cane`
- leetspeak: `p0rc0 di0`
- maiuscole/minuscole e accenti
- spaziature/punteggiatura tra le due parole della bestemmia

### 5.3 Precisione (niente falsi positivi)

Le parole religiose **da sole NON** vengono censurate, così Emilio può parlare
di religione: `credo in Dio`, `madonna che bello`, `una statua di Cristo`,
`addio amici` → tutte lasciate intatte. Anche i moccoli "puliti" come
`porca miseria` non sono trattati come bestemmie.

### 5.4 Cosa fa quando trova qualcosa

1. Se è attiva la censura e c'è una **bestemmia**, prima **chiede all'LLM di
   riformulare** la frase (così resta sensata invece di essere "bippata").
   Numero di tentativi configurabile (`EMILIO_MAX_REGEN`, default 2).
2. Comunque, come passaggio finale, **ripulisce** il testo:
   - **parolacce** → mascherate (`mask`: `c***o`), oppure `[bip]`, oppure `[censura]`;
   - **bestemmie** → sostituite con un'**interiezione innocua** ("santo cielo",
     "mannaggia", ...). (Mascherarne solo una parte lascerebbe leggibile l'offesa.)

### 5.5 Controllo dell'amministratore (R7, R8)

La censura è un **passaggio obbligato** della pipeline ed è **attivabile/
disattivabile a runtime**:

- da codice: `agent.set_moderazione(True|False)`, stato in `agent.moderazione_attiva`;
- da console: `/censura on | off | stato`;
- all'avvio: `EMILIO_MODERATION=0|1`.

Punto unico di passaggio: `Moderator.process(testo) -> (testo, report, applicata)`.
Quando è **disattivata**, il testo passa **invariato** ma il supervisore
**analizza comunque** e popola il `report`: così l'amministratore vede nei log
cosa *sarebbe* stato censurato, senza alcun effetto sull'output.

### 5.6 Ampliare gli elenchi

Si aggiungono termini in `moderation/lexicon.py`:

- `PROFANITY` — `(radice, gravità, flessione)`
- `BLASPHEMY_DIVINE` — entità divine
- `BLASPHEMY_QUALIFIER` — qualificatori offensivi
- `BLASPHEMY_FIXED` — espressioni fisse
- `INTERJECTIONS` — sostituti innocui

Nessuna modifica al motore (`engine.py`).

---

## 6. La persona (carattere di Emilio)

Definita in `persona.py` come dato (modificabile o caricabile da JSON con
`EMILIO_PERSONA=/percorso.json`). Contiene: biografia, tratti, stile di
linguaggio, interessi, regole di comportamento (incluse quelle anti-turpiloquio,
prima linea di difesa). Da qui si costruisce il **system prompt** dell'LLM.

> Per rendere Emilio "alla Mosconi": qui si inseriscono frasi tipiche,
> intercalari, tormentoni e il tono da fuorionda. Se ritrovi materiale del
> vecchio progetto, va incollato in questo file.

---

## 7. La base LLM (cervello)

`brain.py` con due implementazioni dietro la stessa interfaccia:

- **`MockBrain`** — offline, senza chiavi; repertorio di battute in carattere.
  Può anche produrre frasi "sboccate" (`naughty=True`) per **collaudare il
  supervisore**.
- **`ClaudeBrain`** — base LLM reale via API di **Claude (Anthropic)**.
  - modello di default: `claude-opus-4-8`
  - usa *adaptive thinking* + parametro *effort*
  - mantiene la **memoria della conversazione**
  - `revise()` per la riformulazione richiesta dal supervisore (usa un messaggio
    di sistema a metà conversazione, supportato da Opus 4.8)

> Nota latenza: per il dialogo dal vivo su hardware leggero, se la latenza di
> Opus risultasse alta si può passare a un modello più rapido (es.
> `claude-haiku-4-5`) impostando `EMILIO_MODEL`. La qualità del personaggio è
> migliore con Opus; è un compromesso da tarare sul campo.

---

## 8. La voce (TTS) — flessibile, a bassa latenza, misurabile (R6)

`speech.py`. Pensato attorno a tre obiettivi: **flessibilità**, **latenza**,
**misurabilità**.

### 8.1 Profili voce (flessibilità)

Una voce è descritta da un **`VoiceProfile`** (backend, modello, parametri).
Il **`VoiceManager`** tiene un catalogo di profili e permette di **cambiare voce
a runtime**. Profili predefiniti:

| Profilo | Backend | Note |
|---------|---------|------|
| `mock` | mock | stampa soltanto (sviluppo/test) |
| `offline` | pyttsx3 | TTS offline, senza rete |
| `veloce` | ElevenLabs | **Flash v2.5**, streaming, bassa latenza → dialogo dal vivo |
| `realistico` | ElevenLabs | **Multilingual v2**, massimo realismo |
| `espressivo` | ElevenLabs | Multilingual v2, stabilità bassa, più teatrale |

Selezione: `EMILIO_VOICE=veloce`, oppure a runtime `agent.set_voce("veloce")` /
`/voce veloce`. Puoi aggiungerne altri con `VoiceManager.aggiungi(...)`.
Per elencare le voci del tuo account ElevenLabs: `speech.list_elevenlabs_voices(api_key)`.

### 8.2 Bassa latenza

- **Streaming**: l'`ElevenLabsSpeaker` apre il flusso `/stream` e invia l'audio
  al player **man mano che arriva** (parte prima che la frase sia completata).
  Richiede `mpg123` o `ffplay` (riproduzione da stdin).
- **Modello Flash v2.5** (`eleven_flash_v2_5`): sintesi ~sub-500ms.
- `optimize_streaming_latency` (0..4) regolabile per profilo.

### 8.3 Misurabilità

Ogni `say()` restituisce **`SpeechMetrics`** (TTFB + tempo totale). La pipeline
riporta anche la **latenza dell'LLM** (`RisultatoParlato.latenza_llm`). Da
console: `/voce test` per una prova cronometrata.

> Player audio: streaming via `mpg123`/`ffplay`; file via `afplay` (macOS) o
> `mpg123`/`aplay` (Linux/Raspberry). Su macOS installa `mpg123`
> (`brew install mpg123`) per lo streaming a bassa latenza.

---

## 9. Il movimento (R1, R2)

`actuators.py`:

- **`MockMover`** — stampa i comandi (sviluppo/test).
- **`SerialMover`** — invia comandi via **seriale** a un microcontrollore
  (es. Arduino) che pilota motori/servo/LED. Protocollo testuale, una riga per
  comando: `MOVE <azione> <valore>\n`. Se `pyserial` non c'è, ripiega su stampa.

Vocabolario movimenti (`MOVES`): `avanti`, `indietro`, `sinistra`, `destra`,
`testa_su/giu/sx/dx`, `braccio_su/giu`, `bocca`, `occhi_on/off`, `stop`.

Controllo **manuale** da console: `/muovi avanti 2`, `/azioni` per l'elenco.

---

## 10. Scelte hardware (R5, R9)

**Strategia: il carico pesante sta nel cloud.** L'LLM (Claude) e la voce
(ElevenLabs) girano via API: il Raspberry fa solo da **orchestratore** (manda
testo, riceve audio, lo riproduce, pilota i motori). Quindi:

- **Raspberry Pi 3/4/5** sono più che sufficienti.
- Serve **connessione internet** per LLM e voce realistica. (Senza rete: cervello
  `MockBrain` + voce `pyttsx3`, qualità ridotta.)
- **Audio**: uscita jack/USB/HAT audio + un player MP3 (`mpg123`).
- **Movimento**: scheda motori/servo collegata via USB-seriale, con firmware
  che interpreta `MOVE <azione> <valore>`.

**Sul Mac (sviluppo)**: tutto già cross-platform. `afplay` è preinstallato per
l'audio; per la seriale si usa il backend `mock` finché non c'è hardware.

---

## 11. Configurazione (variabili d'ambiente)

| Variabile | Default | Significato |
|-----------|---------|-------------|
| `EMILIO_USE_LLM` | `0` | `1` per usare Claude invece del mock |
| `EMILIO_MODEL` | `claude-opus-4-8` | modello LLM |
| `EMILIO_MAX_TOKENS` | `800` | lunghezza massima risposta |
| `EMILIO_EFFORT` | `medium` | `low`/`medium`/`high` |
| `EMILIO_MODERATION` | `1` | supervisione attiva all'avvio |
| `EMILIO_CENSOR_STYLE` | `mask` | `mask`/`bleep`/`euphemism` |
| `EMILIO_MODERATE_INPUT` | `1` | analizza anche l'input utente (log) |
| `EMILIO_MAX_REGEN` | `2` | tentativi di riformulazione su bestemmia |
| `EMILIO_VOICE` | (da `EMILIO_TTS`) | profilo voce: `mock`/`offline`/`veloce`/`realistico`/`espressivo` |
| `EMILIO_TTS` | `mock` | ripiego se `EMILIO_VOICE` non impostato |
| `EMILIO_TTS_LANG` | `it` | lingua TTS |
| `ELEVENLABS_API_KEY` | — | chiave ElevenLabs |
| `ELEVENLABS_VOICE_ID` | — | id della voce italiana scelta |
| `ELEVENLABS_MODEL` | `eleven_multilingual_v2` | modello voce |
| `EMILIO_AUDIO_OUT` | `emilio_voce.mp3` | file audio generato |
| `EMILIO_ACTUATORS` | `mock` | `serial`/`mock` |
| `EMILIO_SERIAL_PORT` | `/dev/ttyUSB0` | porta seriale motori |
| `EMILIO_SERIAL_BAUD` | `9600` | baud rate seriale |
| `EMILIO_PERSONA` | — | file JSON con persona custom |

---

## 12. Avvio rapido

### Sul Mac, subito (offline, senza chiavi)

```bash
git clone <URL-REPO>
cd <repo>
python3 -m emilio
```

```
tu> Come va Emilio?
🔊 [Emilio] Eh, ai miei tempi sì che si stava bene...
tu> /muovi avanti 2
🤖 [Emilio muove] vai avanti (x2)
tu> /censura off
tu> /mod porco dio       # debug del supervisore
```

### Emilio "completo" (LLM reale + voce ElevenLabs)

```bash
pip install anthropic requests
export ANTHROPIC_API_KEY=...
export ELEVENLABS_API_KEY=...
export ELEVENLABS_VOICE_ID=...        # voce italiana scelta nel tuo account
export EMILIO_USE_LLM=1
export EMILIO_TTS=elevenlabs
python3 -m emilio
```

### Da codice

```python
from emilio import EmilioAgent
emilio = EmilioAgent()
ris = emilio.parla("Raccontami una cosa dei tuoi tempi")
print(ris.testo_detto, ris.report.summary())
```

---

## 13. Comandi della console

| Comando | Azione |
|---------|--------|
| `<testo>` | parla con Emilio (LLM → supervisore → voce) |
| `/di <testo>` | fai dire una frase esatta (passa dal supervisore) |
| `/voci` | elenca i profili voce |
| `/voce <nome>` | cambia la voce attiva a runtime |
| `/voce test [testo]` | prova la voce e misura la latenza |
| `/muovi <azione> [valore]` | movimento manuale |
| `/azioni` | elenco movimenti |
| `/censura on\|off\|stato` | controllo amministratore della supervisione |
| `/mod <testo>` | analizza un testo col supervisore (debug) |
| `/reset` | azzera la memoria conversazione |
| `/aiuto` | aiuto |
| `/esci` | esci |

---

## 14. Test

```bash
python3 -m unittest emilio.tests.test_moderation -v
```

Coprono: bestemmie combinatorie, forme attaccate/leet, falsi positivi
religiosi, eufemismi, parolacce con flessioni, sanificazione, e il toggle
amministratore.

---

## 15. Roadmap / prossimi passi (sul Mac)

1. **Carattere** — arricchire `persona.py` con frasi e tono "alla Mosconi"
   (e materiale del vecchio progetto, se recuperato).
2. **Voce** — scegliere/clonare una voce italiana su ElevenLabs, salvare il
   `voice_id`, tarare i parametri e fare una prova audio end-to-end.
3. **Cervello** — collegare Claude, tarare prompt/lunghezza/latenza per il
   dialogo dal vivo.
4. **Hardware** — definire motori/servo del robottino e scrivere il firmware
   seriale (`MOVE <azione> <valore>`).
5. **Ingresso vocale (futuro)** — aggiungere STT (riconoscimento vocale) per
   parlare a Emilio a voce: oggi l'input è testuale.

---

## 16. Decisioni ancora aperte

- **Stile di censura di default**: sostituzione con moccolo innocuo (effetto
  "fuorionda ripulito") oppure `[bip]` stile TV? → impostabile con
  `EMILIO_CENSOR_STYLE`.
- **Modello LLM**: Opus (qualità) vs Haiku (latenza/costo) per il tempo reale.
- **Voce**: quale voce ElevenLabs italiana (o eventuale clonazione).
- **Ingresso**: solo testo per ora; valutare comando vocale (STT).

---

## 17. Tecnologie per massimizzare il potenziale dell'LLM (ricerca)

Sintesi di una ricerca su come "spremere" al massimo l'LLM che governa Emilio.

### 18.1 Far AGIRE l'LLM: tool use / function calling

Oggi l'LLM solo *parla*; il movimento è separato. Con il **tool use** (function
calling) di Claude possiamo esporre all'LLM il vocabolario dei movimenti come
"strumenti": Claude, mentre risponde, decide di emettere `muovi("avanti")` o
`muovi("braccio_su")` e il nostro codice lo esegue. Risultato: **Emilio
gesticola e si muove in modo coerente con ciò che dice**, non a caso.
- È il salto di qualità più grande per il personaggio.
- Si definiscono i tool come schema JSON; Claude segnala la chiamata, noi la
  eseguiamo via `actuators.py`.

### 18.2 Agent Skills (Claude)

Le **Skills** sono cartelle (`SKILL.md` + eventuali script/risorse) che Claude
carica **automaticamente quando servono**, senza appesantire sempre il contesto.
Per Emilio possiamo creare skill dedicate, es.:
- *persona-emilio* — tono, frasi tipiche, tormentoni "alla Mosconi";
- *moccoli-puliti* — repertorio di esclamazioni innocue da usare al posto del
  turpiloquio;
- *aneddoti* — storie/contesto da cui attingere.
Regola pratica: descrizioni specifiche = la skill si attiva in modo affidabile;
poche skill ben fatte > tante (ognuna "costa" contesto).

### 18.3 Voce: scelta del modello ElevenLabs

Tre opzioni, da scegliere in base al compromesso realismo/latenza:
- **Multilingual v2** — il più stabile e lifelike: ottimo per qualità, un filo
  più lento. (È il default attuale del progetto.)
- **Flash v2.5** — **bassissima latenza (~sub-500ms)**, 32 lingue incl. italiano:
  ideale per **conversazione in tempo reale** su un robot.
- **Eleven v3** — il più **espressivo** (70+ lingue): per recitazione/emozione.

Inoltre esiste la **ElevenLabs Agents Platform** (STT + LLM + TTS in un unico
agente vocale a bassa latenza): comoda, ma metterebbe l'LLM "dentro" ElevenLabs
e renderebbe più difficile inserire **il nostro supervisore** nel flusso. Per
mantenere il controllo della censura conviene tenere la **nostra pipeline**
(LLM → supervisore → TTS) e usare ElevenLabs **solo** come voce.

### 18.4 Ingresso vocale (STT, futuro)

Per parlare a Emilio a voce (non solo testo) serve uno **Speech-To-Text**.
Opzioni: Whisper (anche locale/`whisper.cpp` sul Pi), o lo STT di ElevenLabs.
Da aggiungere come nuovo componente a monte della pipeline.

### 18.5 Parametri del modello Claude

- *adaptive thinking* + *effort* (`low/medium/high`) per bilanciare qualità e
  latenza/costo.
- Modello: `claude-opus-4-8` per qualità del personaggio; valutare un modello
  più rapido se la latenza dal vivo è critica.

---

## 18. Note operative

- Il nucleo (persona + supervisore + pipeline) gira con la **sola libreria
  standard** di Python: le dipendenze (`anthropic`, `requests`, `pyttsx3`,
  `pyserial`) servono solo per i componenti reali e sono **opzionali**.
- Tutta la configurazione passa da **variabili d'ambiente**: nessun segreto nel
  codice.
- Il progetto è isolato nella cartella `emilio/` e non dipende dagli altri file
  presenti nel repository.
