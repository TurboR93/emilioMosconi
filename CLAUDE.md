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

- **Mac = la mente**: orchestratore + **LLM** (locale o cloud) + supervisore +
  voce + **ascolto (STT)**. È anche la macchina di sviluppo.
- **Raspberry Pi = il corpo**: **microfono e altoparlante a bordo**, motori dei
  **cingoli**, collegato alla mente in **Wi-Fi**.
- **Movimento**: i **cingoli** sono l'unica motorizzazione attiva; le **braccia**
  sono in `actuators.MOVES` ma **rinviate al futuro** (non cablate).

Pipeline (in [`src/emilio/agent.py`](src/emilio/agent.py)):
`input → brain(LLM) → moderator → voce(TTS) + actuators(movimento)`.

**Censura via BIP, MIRATA** (modello deciso col committente): il cervello **NON
riformula**; il supervisore individua parolacce/bestemmie e restituisce gli span
da bippare (`Moderator.span_censura` via `_riduci_match`) — censura "alla veneta":
di ogni parolaccia restano udibili le **prime 2 lettere** (e l'ultima per parole
di 5+), si bippa solo il **centro** (es. `st[BIP]o`). La **voce copre quel centro
con un BIP sull'audio**: `ElevenLabsSpeaker._say_censura` usa l'endpoint
*with-timestamps* (`apply_text_normalization=off` + verifica allineamento 1:1) e
`ffmpeg`; la voce **offline** fa **una sola sintesi** e stima il timing in
proporzione ai caratteri; `mock` mostra `[BIP]` testuale (`Moderator.testo_con_bip`,
marcatore `EMILIO_BIP_MARKER`). Logica pura in
[`audio_bip.py`](src/emilio/audio_bip.py); bip in `assets/beeps/` (`EMILIO_BIP_DIR`).
**Disattivabile dall'admin** (`set_moderazione(False)` / `/censura off`): spenta →
nessuno span → audio **grezzo**, ma il supervisore analizza comunque per i log.
Se il bip fallisce, ripiego sicuro: testo con "bip" parlato (la parolaccia non
viene mai udita).

## Convenzioni del codice (rispettarle)

- **Lingua: italiano.** Nomi di funzioni/variabili, commenti, docstring, output
  utente sono in italiano. Continua così.
- **Core solo stdlib.** Il nucleo non ha dipendenze. Le librerie esterne
  (`anthropic`, `requests`, `pyttsx3`, `pyserial`, `faster-whisper`) sono
  **opzionali** e vanno importate **pigramente** dentro il backend che le usa,
  mai a livello di modulo.
- **Pattern a backend intercambiabili.** Ogni capacità ha un'**ABC** + una
  **factory `build_*`** + un backend **mock** (offline, senza chiavi) e uno
  reale: `Brain`/`build_brain`, `Speaker`+`VoiceManager`/`build_voice_manager`,
  `Mover`/`build_mover`, `Occhi`/`build_occhi`, `Ascoltatore`/`build_ascoltatore`.
  **Aggiungere nuove capacità così** (vedi sotto).
- **Mock-first.** Tutto deve girare offline e senza chiavi (`python -m emilio`).
  I 54 test non devono mai richiedere rete o segreti.
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
python -m pytest                       # 54 test (o: python -m unittest discover -s tests)
emilio                                 # avvio (o: python -m emilio)
```

Con **src-layout** il pacchetto vive in `src/emilio/`: i test e `python -m emilio`
funzionano **solo dopo `pip install -e .`** (non basta stare nella cartella).

## Cervello: backend selezionabile

`EMILIO_LLM` = `mock` | `claude` | `local`. Il **`LocalBrain`** ([brain.py](src/emilio/brain.py))
usa l'**API nativa di Ollama** (`localhost:11434/api/chat`, campo `think:false`
per disattivare il ragionamento lento — NON è l'API OpenAI `/v1`), per sviluppo
offline sul Mac. Si passa a Claude (cloud) o al locale **solo via env**, senza
toccare la pipeline. Env del locale: `EMILIO_LOCAL_URL` (default
`http://localhost:11434`), `EMILIO_LOCAL_MODEL` (default `gemma4:12b`),
`EMILIO_LOCAL_THINK`, `EMILIO_LOCAL_KEY`. Tutti i cervelli espongono
`reply(user_text, umore=...)`: con `umore="arrabbiato"` (provocazione rilevata) il
prompt utente riceve una spinta a rispondere infuriato. **Onboard sul Pi si userà
il cloud** (`claude` + ElevenLabs): il Raspberry non regge l'inferenza locale.

## Occhi (importantissimi)

Capacità a sé ([occhi.py](src/emilio/occhi.py)): `Occhi` ABC + `build_occhi`
(`EMILIO_OCCHI=mock|preview`, porta `EMILIO_OCCHI_PORT` default 8473).
`OcchiPreview` apre un'**anteprima nel browser** (solo stdlib `http.server`) che
disegna la **faccia del vero Emiglio** (calotta bianca, visiera nera, occhi tondi
a LED, **bocca animata** mentre parla); se **arrabbiato** gli occhi diventano
**forche del diavolo** animate, con scritte di stato pulsanti (TI ASCOLTO / STO
PENSANDO / PARLO). Espressioni in `ESPRESSIONI`: neutro/felice/arrabbiato/sorpreso/
triste/pensa/parla/ascolta/spento. CLI: `/occhi [espressione]`, `/occhi guarda <dir>`.
L'agente li pilota da solo (pensa mentre genera, parla/arrabbiato mentre parla,
ascolta mentre ascolta). In futuro `OcchiLed` sul Pi (LED RGB indirizzabili).

## Reattività (carattere) e ascolto

- **Stato d'animo**: l'LLM inizia la risposta con un tag `[neutro|felice|
  arrabbiato|sorpreso|pensa|triste]` che `agent._estrai_emozione` stacca (non si
  pronuncia) e usa per guidare gli occhi. `RisultatoParlato.emozione`. Il parsing
  è **tollerante** (virgolette/asterischi/aggettivi: `[molto arrabbiato]`,
  `[arrabbiato!]`); se fra parentesi non c'è un'emozione nota, lascia il testo intatto.
- **Si infuria**: `agent._provocato_input` rileva insulti/contraddizioni anche
  SENZA parolacce (`moderation.contiene_provocazione`, lista `lexicon.PROVOCAZIONI`)
  e gli passa `umore="arrabbiato"`; `_emozione` mette `arrabbiato` anche se la
  risposta contiene turpiloquio o se il tag è `[arrabbiato]`. Allora occhi = forche
  del diavolo + risposta acida bippata. La persona ([persona.py](src/emilio/persona.py))
  è tarata per esplodere (la censura è a valle, non nel prompt). `EMILIO_MODERATE_INPUT`.
- **Ascolto (STT)**: [ascolto.py](src/emilio/ascolto.py) — `Ascoltatore` ABC +
  `build_ascoltatore` (`EMILIO_ASCOLTO=mock|whisper`). `WhisperAscoltatore`
  registra dal microfono (ffmpeg avfoundation) e trascrive con faster-whisper
  (offline, IT) con `vad_filter` (anti-allucinazione sul silenzio). CLI:
  `/ascolta [secondi]` (un turno) e `/conversa [secondi]` (mani libere). Env:
  `EMILIO_STT_MODEL` (default `small`), `EMILIO_STT_LANG`, `EMILIO_STT_COMPUTE`,
  `EMILIO_MIC_DEVICE`, `EMILIO_STT_SECONDI`. Gira sul Mac (non sul Pi).

## Come estendere (la libertà di sviluppo futuro è già predisposta)

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
