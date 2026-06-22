# CLAUDE.md

Guida per le sessioni di sviluppo con Claude Code su **Emilio**. Leggi anche
[`README.md`](README.md) (uso) e [`docs/PROGETTO.md`](docs/PROGETTO.md)
(architettura esaustiva).

## Cos'è

Emilio è un **robottino anni '90** riportato in vita: un cervello **LLM** lo fa
parlare come una persona vera (carattere "Germano Mosconi", brontolone ma
bonario), una **voce italiana realistica** lo pronuncia, un **supervisore**
censura parolacce/bestemmie ed è **disattivabile dall'amministratore**.

## Architettura "mente + corpo"

- **Mac = la mente**: orchestratore + **LLM locale** + supervisore + voce.
  È anche la macchina di sviluppo.
- **Raspberry Pi = il corpo**: **microfono e altoparlante a bordo**, motori dei
  **cingoli**, collegato alla mente in **Wi-Fi**.
- **Movimento**: i **cingoli** sono l'unica motorizzazione attiva; le **braccia**
  sono in `actuators.MOVES` ma **rinviate al futuro** (non cablate).

Pipeline (in [`src/emilio/agent.py`](src/emilio/agent.py)):
`input → brain(LLM) → moderator → voce(TTS) + actuators(movimento)`.

**Censura via BIP** (modello deciso col committente): il cervello **NON
riformula**; il supervisore individua parolacce/bestemmie come span di carattere
(`Moderator.span_censura`) e la **voce li copre con un BIP sull'audio**
(`ElevenLabsSpeaker._say_censura` usa l'endpoint *with-timestamps* di ElevenLabs
per mappare i caratteri sul tempo, poi `ffmpeg` sovrappone il bip; logica pura in
[`audio_bip.py`](src/emilio/audio_bip.py); file bip in `assets/beeps/`, lista
estendibile). **Disattivabile dall'admin** con lo stesso interruttore della
supervisione (`set_moderazione(False)` / `/censura off`): spenta → nessuno span →
audio **grezzo**, ma il supervisore analizza comunque per i log. Se il bip audio
fallisce, ripiego sicuro: si risintetizza il testo con "bip" parlato (la
parolaccia non viene mai udita). Le voci `mock`/`offline` approssimano il bip.

## Convenzioni del codice (rispettarle)

- **Lingua: italiano.** Nomi di funzioni/variabili, commenti, docstring, output
  utente sono in italiano. Continua così.
- **Core solo stdlib.** Il nucleo non ha dipendenze. Le librerie esterne
  (`anthropic`, `requests`, `pyttsx3`, `pyserial`) sono **opzionali** e vanno
  importate **pigramente** dentro il backend che le usa, mai a livello di modulo.
- **Pattern a backend intercambiabili.** Ogni capacità ha un'**ABC** + una
  **factory `build_*`** + un backend **mock** (offline, senza chiavi) e uno
  reale: `Brain`/`build_brain`, `Speaker`+`VoiceManager`/`build_voice_manager`,
  `Mover`/`build_mover`. **Aggiungere nuove capacità così** (vedi sotto).
- **Mock-first.** Tutto deve girare offline e senza chiavi (`python -m emilio`).
  I 19 test non devono mai richiedere rete o segreti.
- **Config via env.** Ogni opzione sta in [`config.py`](src/emilio/config.py)
  (`EmilioConfig`, sovrascrivibile da variabili `EMILIO_*`). Non hardcodare.

## Python

- **Minimo: 3.11** (`requires-python = ">=3.11"` in `pyproject.toml`). È il
  Python di Raspberry Pi OS Bookworm. **Consigliato 3.13** sul Pi (Pi OS Trixie).
- **3.9/3.10 vietati** (3.9 è EOL da ottobre 2025; il codice usa la sintassi
  `X | None`). Sviluppo locale sul venv 3.11 in `.venv`.

## Comandi

```bash
source .venv/bin/activate              # venv Python 3.11
pip install -e ".[dev]"                # editable + pytest (necessario col src-layout)
python -m pytest                       # 19 test (o: python -m unittest discover -s tests)
emilio                                 # avvio (o: python -m emilio)
```

Con **src-layout** il pacchetto vive in `src/emilio/`: i test e `python -m emilio`
funzionano **solo dopo `pip install -e .`** (non basta stare nella cartella).

## Come estendere (la libertà di sviluppo futuro è già predisposta)

- **LLM locale** → nuovo `LocalBrain(Brain)` in `brain.py` (poi `brain/`), che
  parla con un server locale sul Mac (es. Ollama, API compatibile OpenAI) via
  `requests`; selezionalo in `build_brain` con un nuovo valore di config. Non
  toccare la pipeline.
- **Corpo in Wi-Fi** → nuovo `NetworkMover(Mover)` in `actuators.py` (poi
  `hardware/`) che invia lo stesso protocollo testuale `MOVE <azione> <valore>`
  su rete invece che su seriale; aggiungi `network` a `EMILIO_ACTUATORS`.
- **Voce sul corpo** → uno `Speaker` che, invece di riprodurre in locale, manda
  l'audio al Pi; il `VoiceManager` già gestisce profili intercambiabili.
- **Ascolto (STT/wake-word)** → nuovo componente **a monte** della pipeline
  (futuro modulo `listen/`), non dentro brain/voce.
- **Concorrenza**: oggi tutto è sincrono e va bene per l'uso a turni. Per
  "muovere mentre parla" o per il barge-in servirà mettere player TTS e attuatori
  dietro thread/coda; per l'ASR pesante un processo separato. Non anticiparlo
  finché non serve.

## Deploy sul Raspberry (quando si arriverà al corpo)

- Pi OS **64-bit** (per i wheel ARM, es. `pydantic-core` di `anthropic`).
- **venv obbligatorio** (Bookworm/Trixie impongono PEP 668: niente `pip` di
  sistema, mai `--break-system-packages`).
- Audio: **`ffmpeg` è richiesto** per il BIP di censura; `mpg123`/`ffplay` per la
  riproduzione; su headless usa **ALSA puro**. `afplay` è **solo macOS**.
  Seriale: utente nel gruppo `dialout`; valuta una regola udev.
- Servizio `systemd` con `EnvironmentFile` per le chiavi.

## Git

- Origin: `https://github.com/TurboR93/emilioMosconi`, branch `master`.
- Sposta i file con `git mv` per preservare la storia. Committa/pusha solo se
  richiesto. Chiudi i messaggi di commit con il trailer
  `Co-Authored-By: Claude ...`.
