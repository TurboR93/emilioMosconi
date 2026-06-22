# Emilio 🤖

Ridare vita a **Emilio** dentro un **robottino degli anni '90**: un cervello
**LLM** che lo fa parlare come una **persona vera** (stile "Germano Mosconi",
verace e brontolone, ma ripulito), una **voce italiana realistica**, un
**supervisore** che censura parolacce e bestemmie — **disattivabile
dall'amministratore** — e il **controllo del movimento** del robottino.

L'LLM dà spontaneità; il supervisore tiene la bocca pulita.

---

## Architettura: la mente e il corpo

Emilio vive su **due macchine** collegate in **Wi-Fi**:

```
   ┌─────────────────────────── MAC (la "mente") ───────────────────────────┐
   │  LLM LOCALE  ─►  Supervisore  ─►  Voce (TTS)                            │
   │  (cervello)      (censura)        (ElevenLabs / offline)                │
   └───────────────┬──────────────────────────────────────┬─────────────────┘
                   │  comandi movimento + audio  (Wi-Fi)   │  audio microfono
                   ▼                                       ▲
   ┌─────────────────────────── RASPBERRY PI (il "corpo") ──────────────────┐
   │  cingoli (motori)   ·   altoparlante   ·   microfono   ·   (LED/occhi)  │
   └────────────────────────────────────────────────────────────────────────┘
```

- **Mac** = la mente. Gira l'orchestratore di Emilio, il **LLM locale**, il
  supervisore e la sintesi vocale. Il Mac è la macchina di sviluppo.
- **Raspberry Pi** = il corpo. **Microfono e altoparlante sono a bordo**: Emilio
  sente e parla dal suo corpo. Pilota i **cingoli** (le braccia arriveranno in
  futuro) e riceve i comandi via Wi-Fi.

> **Stato attuale.** Il codice di oggi è il cuore software (cervello +
> supervisore + voce + movimento) e gira **tutto sul Mac**, in mock o con i
> servizi reali. Il "corpo" Raspberry, il **LLM locale** e il **trasporto
> Wi-Fi** sono i prossimi passi (vedi [Roadmap](#roadmap)); l'architettura è
> già predisposta per accoglierli senza riscritture.

### Pipeline del parlato

```
input  ─►  [Cervello LLM]  ─►  [Supervisore]  ─►  [Voce TTS]  +  [Movimento]
              genera           individua            pronuncia      muove
              in carattere     parti sporche        col BIP
                               DISATTIVABILE        sull'audio
```

Il cervello dice la sua battuta naturale (**niente riformulazione dell'LLM**); il
**supervisore** individua parolacce e bestemmie e la **voce le copre con un BIP
sull'audio**. La censura è **disattivabile dall'amministratore**. Orchestrazione
in [`agent.py`](src/emilio/agent.py).

Ogni componente è dietro un'**interfaccia astratta** con una **factory
`build_*`** e ha un backend **mock** che gira **offline e senza chiavi**: si
sviluppa tutto sul Mac e si cambia solo la configurazione per il robot.

---

## Componenti

| File | Ruolo |
|------|-------|
| [`persona.py`](src/emilio/persona.py) | Chi è Emilio; system prompt (1ª difesa anti-turpiloquio) |
| [`brain.py`](src/emilio/brain.py) | Cervello: `MockBrain` (offline) · `LocalBrain` (LLM locale, Ollama) · `ClaudeBrain` (cloud) |
| [`moderation/`](src/emilio/moderation/) | **Supervisore**: lessico + motore di censura (2ª difesa) |
| [`speech.py`](src/emilio/speech.py) | Voce: `ElevenLabsSpeaker` / `Pyttsx3Speaker` / `MockSpeaker` |
| [`occhi.py`](src/emilio/occhi.py) | Occhi LED: `OcchiMock` / `OcchiPreview` (anteprima nel browser) |
| [`ascolto.py`](src/emilio/ascolto.py) | Riconoscimento vocale (STT): `WhisperAscoltatore` / `MockAscoltatore` |
| [`actuators.py`](src/emilio/actuators.py) | Movimento: `SerialMover` / `MockMover`. *In arrivo: trasporto di rete (Wi-Fi)* |
| [`agent.py`](src/emilio/agent.py) | Pipeline completa |
| [`cli.py`](src/emilio/cli.py) | Console di controllo manuale |

---

## Requisiti

- **Python ≥ 3.11** (minimo). Consigliato **3.13** sul Raspberry (Pi OS Trixie).
  Python 3.9/3.10 **non** sono supportati (3.9 è in EOL da ottobre 2025).
- Il **nucleo** non ha dipendenze: gira con la sola libreria standard.
- Le parti reali sono **extra opzionali** (LLM, voce, hardware).

---

## Avvio rapido (offline, senza chiavi)

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e .
emilio                     # oppure: python -m emilio
```

```
tu> Come va Emilio?
🔊 [Emilio/mock] Eh, ai miei tempi sì che si stava bene...
tu> /muovi avanti 2
🤖 [Emilio muove] vai avanti (x2)
tu> /di ma che cazzo dici, porco dio
🔊 [Emilio/mock] ma che [BIP] dici, [BIP]   # censura ON: bip sull'audio
tu> /censura off
tu> /di ma che cazzo dici, porco dio
🔊 [Emilio/mock] ma che cazzo dici, porco dio   # admin OFF: audio grezzo
```

## Emilio "reale" (cervello + voce)

```bash
pip install -e ".[llm,voice]"      # Claude + ElevenLabs
export ANTHROPIC_API_KEY=...        # cervello (cloud, per ora)
export ELEVENLABS_API_KEY=...       # voce
export ELEVENLABS_VOICE_ID=...      # voce italiana scelta sul tuo account
export EMILIO_USE_LLM=1
export EMILIO_VOICE=veloce          # bassa latenza (Flash v2.5, streaming)
emilio
```

## Cervello locale (Ollama, sul Mac)

Per iterare offline e senza costi, Emilio può usare un **LLM locale** servito da
Ollama (API compatibile OpenAI). Ottimo per lo sviluppo sul Mac:

```bash
ollama pull gemma4:12b              # scarica il modello (es. Gemma 4 12B)
pip install -e ".[voice]"           # 'requests' serve anche per l'LLM locale
export EMILIO_LLM=local
export EMILIO_LOCAL_MODEL=gemma4:12b   # opzionale (default)
emilio
```

> In produzione sul Raspberry si passerà alle **API cloud** (`EMILIO_LLM=claude`,
> voce ElevenLabs): il Pi non regge l'inferenza locale. È solo un cambio di
> variabili d'ambiente — il codice non cambia.

## Occhi: anteprima nel browser

```bash
export EMILIO_OCCHI=preview          # apre una pagina con la faccia di Emiglio
emilio                               # poi: /occhi felice  ·  /occhi guarda destra
```

## Reattività: se lo provochi, si infuria

Se lo **insulti** o lo **contraddici**, Emilio si infuria: gli **occhi diventano
forche del diavolo** e risponde **acido**, con parolacce e bestemmie — che il
supervisore **copre col BIP** (lo stesso interruttore admin le può disattivare).
Lo stato d'animo guida gli occhi: l'LLM lo dichiara con un tag iniziale
(`[arrabbiato]`, `[felice]`, `[pensa]`, ...) che non viene mai pronunciato.

## Parlare a voce (microfono + STT)

Per parlargli davvero, come farà il prodotto finale:

```bash
pip install -e ".[listen]"           # faster-whisper (STT offline, italiano)
export EMILIO_ASCOLTO=whisper
export EMILIO_STT_MODEL=small        # tiny|base|small|medium (qualità vs velocità)
EMILIO_LLM=local EMILIO_VOICE=offline EMILIO_OCCHI=preview emilio
# poi nel prompt:  /ascolta 5   → registra 5s dal microfono e Emilio risponde
```

> Il microfono su macOS chiede il **permesso** la prima volta (al Terminale/app
> che lancia Emilio). Lo STT, come l'LLM locale, gira sul **Mac**.

## Da codice

```python
from emilio import EmilioAgent

emilio = EmilioAgent()
ris = emilio.parla("Raccontami una cosa dei tuoi tempi")
print(ris.testo_detto)        # ciò che ha detto (post-supervisore)
print(ris.report.summary())   # esito dell'analisi del supervisore
```

---

## Il supervisore (parolacce + bestemmie)

È il pezzo centrale. Caratteristiche:

- **Bestemmie combinatorie**: entità divina + qualificatore offensivo in
  qualunque ordine (`porco dio`, `dio cane`, `porca madonna`...), anche
  attaccati (`porcodio`) o con punteggiatura in mezzo.
- **Resistente alle evasioni**: lettere ripetute (`diooo`), leetspeak
  (`p0rc0 di0`), maiuscole, accenti.
- **Preciso**: le parole religiose da sole NON vengono censurate (`credo in Dio`,
  `madonna che bello` passano lisce).
- **Parolacce con flessioni**: una radice intercetta le varianti
  (`cazz` → cazzo, cazzi, cazzata, cazzone).

**Come agisce la censura: un BIP sull'audio.** Il cervello dice la frase per
intero (**niente riformulazione dell'LLM**); la voce ricava dai timestamp di
ElevenLabs *dove* cadono le parti sporche e ci sovrappone un **file BIP** (da
[`src/emilio/assets/beeps/`](src/emilio/assets/beeps/), lista estendibile — per
ora il classico bip) tramite `ffmpeg`. In console/log le parti coperte appaiono
come `[BIP]` (`EMILIO_BIP_MARKER`); sulle voci offline/mock il bip è approssimato.

### Controllo dell'amministratore

La censura è **attivabile/disattivabile a runtime** dall'amministratore. Con la
supervisione **spenta** non si calcola alcuno span da bippare: Emilio dice
l'audio **grezzo**. Anche da spenta, però, il supervisore continua ad
**analizzare** il testo per i log (così sai cosa *sarebbe* stato bippato).

```python
agent.set_moderazione(False)   # disattiva
agent.set_moderazione(True)    # riattiva
agent.moderazione_attiva       # stato
```

Da console: `/censura on|off|stato`. Per ampliare il lessico aggiungi termini in
[`moderation/lexicon.py`](src/emilio/moderation/lexicon.py): nessuna modifica al motore.

---

## Configurazione (variabili d'ambiente)

| Variabile | Default | Note |
|-----------|---------|------|
| `EMILIO_LLM` | (vuoto) | backend cervello: `mock`/`claude`/`local` |
| `EMILIO_LOCAL_MODEL` | `gemma4:12b` | modello dell'LLM locale (Ollama) |
| `EMILIO_LOCAL_URL` | `http://localhost:11434/v1` | endpoint LLM locale (compatibile OpenAI) |
| `EMILIO_USE_LLM` | `0` | retrocompat: `1` = `claude` se `EMILIO_LLM` non impostato |
| `EMILIO_MODEL` | `claude-opus-4-8` | modello Claude (cloud) |
| `EMILIO_MODERATION` | `1` | supervisione (BIP) on/off all'avvio — disattivabile da admin |
| `EMILIO_BIP_MARKER` | `[BIP]` | come appare il bip in console/log |
| `EMILIO_BIP_DIR` | (pacchettizzati) | cartella con i file BIP (lista) |
| `EMILIO_CENSOR_STYLE` | `mask` | resa testuale legacy (`mask`/`bleep`/`euphemism`) |
| `EMILIO_VOICE` | (deriva da `EMILIO_TTS`) | profilo voce: `mock`/`offline`/`veloce`/`realistico`/`espressivo` |
| `EMILIO_TTS` | `mock` | ripiego se `EMILIO_VOICE` non impostato |
| `ELEVENLABS_API_KEY` / `ELEVENLABS_VOICE_ID` | — | voce realistica IT |
| `EMILIO_ACTUATORS` | `mock` | `serial`/`mock` (in arrivo: `network`) |
| `EMILIO_OCCHI` | `mock` | occhi: `mock`/`preview` (anteprima nel browser) |
| `EMILIO_ASCOLTO` | `mock` | STT: `mock`/`whisper` (microfono + faster-whisper) |
| `EMILIO_STT_MODEL` | `small` | modello whisper: `tiny`/`base`/`small`/`medium` |
| `EMILIO_MIC_DEVICE` | (auto) | indice microfono avfoundation (macOS) |
| `EMILIO_SERIAL_PORT` | `/dev/ttyUSB0` | porta seriale motori |
| `EMILIO_PERSONA` | — | file JSON con una persona custom |

---

## Test

```bash
pip install -e ".[dev]"
python -m pytest                       # oppure: python -m unittest discover -s tests
```

19 test su supervisore e voce. Con il **src-layout** i test girano contro il
pacchetto **installato** (`pip install -e .`), non contro i sorgenti: esegui
sempre l'install editable prima dei test.

---

## Struttura del progetto

```
emilioMosconi/
├── pyproject.toml          # metadata, extra opzionali, comando `emilio`
├── README.md               # questo file
├── CLAUDE.md               # guida per le sessioni di sviluppo con Claude Code
├── docs/                   # documentazione (fuori dal pacchetto)
│   ├── PROGETTO.md         # architettura esaustiva, voce, supervisore, roadmap
│   └── HARDWARE.md         # componenti da comprare (Pi, mic, casse, motori)
├── src/
│   └── emilio/             # il pacchetto (src-layout)
│       ├── agent.py · cli.py · config.py · persona.py
│       ├── brain.py · speech.py · actuators.py · occhi.py · audio_bip.py
│       ├── assets/beeps/   # file BIP di censura (bip_classico.wav)
│       └── moderation/     # supervisore (engine + lexicon)
└── tests/                  # test (fuori dal pacchetto)
```

## Roadmap

- ✅ **Cervello locale** — `LocalBrain` (Ollama, API compatibile OpenAI) accanto
  a `ClaudeBrain`/`MockBrain`.
- ✅ **Occhi** — faccia di Emiglio + anteprima nel browser (`OcchiPreview`);
  forche del diavolo + bocca animata.
- ✅ **Reattività** — si infuria se insultato/contraddetto (occhi + risposta
  acida bippata), via tag di stato d'animo dell'LLM.
- ✅ **Ascolto (STT)** — parla a voce: microfono + faster-whisper (`/ascolta`).
  *In arrivo: wake-word + VAD per il dialogo continuo.*
- **Carattere** — arricchire la persona "alla Mosconi".
- **Voce reale** — scegliere/clonare una voce italiana su ElevenLabs, tararla e
  validare il BIP coi timestamp reali.
- **Corpo Wi-Fi** — `NetworkMover`: il protocollo `MOVE <azione> <valore>` passa
  dalla seriale alla **rete** verso il Raspberry; audio (riproduzione e microfono)
  tra mente e corpo. Occhi LED sul Pi (`OcchiLed`).
- **Movimento** — **cingoli** ora; **braccia** in futuro (già nel vocabolario, non
  ancora cablate).

> **Deploy onboard sul Raspberry:** il Pi non regge l'inferenza locale, quindi in
> produzione si useranno le **API cloud** (cervello `claude`, voce ElevenLabs) —
> solo un cambio di variabili d'ambiente. L'LLM locale resta per sviluppo/test.

Dettagli e decisioni aperte in [`docs/PROGETTO.md`](docs/PROGETTO.md).
