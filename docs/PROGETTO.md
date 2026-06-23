# Progetto Emilio — Documentazione completa

> Documento di riferimento per proseguire il lavoro in autonomia (sul Mac e poi
> sul robottino). Raccoglie visione, requisiti, architettura, scelte hardware,
> voce, occhi, ascolto, sistema di censura, reattività e roadmap.

---

## 1. Visione

Ridare vita a **Emilio** dentro un **robottino degli anni '90** (il giocattolo
**Emiglio** di Giochi Preziosi): deve **parlare**, **muoversi** (anche in modo
manuale), **reagire** ed essere espressivo, **simulando una persona reale** con
un carattere ben definito.

Riferimento di personaggio: il registro "alla **Germano Mosconi**" — italiano
verace, schietto, brontolone, **veneto**. Quando lo si provoca esplode con
parolacce e bestemmie, che un **supervisore** copre con un **BIP** sull'audio.

Architettura **mente + corpo**:

- **Mac = la mente**: orchestratore + **LLM** (locale via Ollama, oppure cloud
  Claude) + supervisore + voce + **ascolto (STT)** + anteprima occhi. È anche la
  macchina di sviluppo.
- **Raspberry Pi = il corpo**: motori dei **cingoli**, **microfono e altoparlante
  a bordo**, collegato alla mente in **Wi-Fi**. Onboard, non reggendo l'inferenza
  locale, userà le **API cloud** (Claude + ElevenLabs).

Due "cervelli" lavorano in cascata: la **base LLM** genera le risposte in
carattere; il **supervisore** controlla a valle e copre il turpiloquio col BIP.

---

## 2. Requisiti raccolti

| # | Requisito | Stato | Dove |
|---|-----------|-------|------|
| R1 | Emilio parla e si muove | ✅ | `agent.py`, `actuators.py` |
| R2 | Movimento anche **manuale** | ✅ | `cli.py` `/muovi`, `actuators.py` |
| R3 | **Simula una persona reale** con carattere | ✅ | `persona.py` |
| R4 | **Supervisore** che censura parolacce + bestemmie IT, sopra la base LLM | ✅ | `moderation/` |
| R5 | Hardware del corpo **non performante** (Raspberry) | ✅ | mente sul Mac, cloud onboard |
| R6 | Voce: **italiano realistico** (ElevenLabs) | ✅ | `speech.py` |
| R7 | Censura **disattivabile dall'amministratore** | ✅ | toggle runtime |
| R8 | Censura **conseguente nel flusso** (passaggio obbligato) | ✅ | `review`+`span_censura` |
| R9 | Sviluppo sul **Mac** dell'utente (la mente) | ✅ | LLM/STT locali sul Mac |
| R10 | **Reattività**: si infuria se provocato | ✅ | `agent`, `lexicon.PROVOCAZIONI` |
| R11 | **Occhi** espressivi (anteprima + LED futuri) | ✅ | `occhi.py` |
| R12 | **Ascolto** vocale (STT) | ✅ | `ascolto.py` |
| R13 | **Repo su GitHub** + documentazione esaustiva | ✅ | questo documento |

---

## 3. Architettura

```
            (voce → STT)          ┌──────────────── EmilioAgent (Mac) ───────────────┐
   utente ───────────────────────┼─► ascolto.py  →  testo                            │
   (testo o microfono)           │   brain.py     →  testo grezzo (+ tag [emozione])  │
                                 │       │  (LLM: local/Ollama, claude, o mock)       │
                                 │       ▼                                            │
                                 │   moderation/  →  span "sporchi" RIDOTTI (centro)  │
                                 │       │                                            │
                                 │       ▼                                            │
                                 │   speech.py    →  voce + BIP sul centro            │
                                 │   occhi.py     →  espressione (forche se arrabbiato)│
                                 │   actuators.py →  movimento cingoli (→ Wi-Fi → Pi) │
                                 └────────────────────────────────────────────────────┘
```

Principi:

- **Componenti dietro interfacce** (ABC) con backend intercambiabili e factory
  `build_*`; ogni capacità ha un **backend "mock"** che gira **offline e senza
  chiavi**. Si sviluppa tutto sul Mac, poi si cambia solo la configurazione.
- **Difesa a due livelli** contro il turpiloquio incontrollato: il *system prompt*
  guida l'LLM; il *supervisore* interviene comunque sull'audio (rete di sicurezza).
  Ma quando Emilio è provocato DEVE sboccare: lì il BIP è il punto, non un errore.
- **Pipeline in streaming, togglabile** (`EMILIO_STREAMING`, default ON;
  `/streaming on|off`): `agent.rispondi` → `parla_streaming` consuma `brain.reply_stream`
  e pronuncia **ogni frase appena pronta** (moderata singolarmente) mentre l'LLM
  genera il resto → latenza percepita molto più bassa. `EMILIO_STREAMING=0` torna
  alla `parla` "a blocco unico". Dettagli in §7 e §8.

---

## 4. Struttura del codice (src-layout)

```
emilioMosconi/
├── pyproject.toml       PEP 621: core stdlib; extra llm/voice/offline-voice/hardware/listen/listen-mlx/dev/all
├── README.md            uso
├── CLAUDE.md            guida per sessioni Claude Code
├── docs/
│   ├── PROGETTO.md      (questo file)
│   └── HARDWARE.md      componenti del corpo
├── src/emilio/
│   ├── __init__.py      API pubblica
│   ├── __main__.py      avvio (python -m emilio)
│   ├── config.py        configurazione (env EMILIO_*)
│   ├── persona.py       chi è Emilio + system prompt
│   ├── brain.py         LLM: MockBrain / ClaudeBrain / LocalBrain (Ollama)
│   ├── moderation/      __init__.py · lexicon.py · engine.py (supervisore)
│   ├── speech.py        voce: ElevenLabs / pyttsx3 / mock
│   ├── audio_bip.py     logica pura del BIP (span→tempo, ffmpeg)
│   ├── occhi.py         occhi LED: mock / anteprima web (faccia di Emiglio)
│   ├── ascolto.py       STT: mock / faster-whisper (CPU) / mlx (Apple Silicon) + VAD
│   ├── actuators.py     movimento: seriale / mock
│   ├── cli.py           console di controllo
│   └── assets/beeps/    file BIP (bip_classico.wav)
└── tests/               77 test
```

> Con il **src-layout** i test e `python -m emilio` funzionano **solo dopo**
> `pip install -e .` (il pacchetto vive sotto `src/`).

---

## 5. Il supervisore (parolacce + bestemmie)

Vive in `moderation/`. Analizza il testo prodotto dall'LLM e individua le parti
da coprire.

### 5.1 Cosa riconosce

- **Bestemmie combinatorie**: entità divina (`dio`, `madonna`/`madona`, `cristo`,
  `ostia`, ...) + qualificatore offensivo (`cane`/`can`, `porco`, `boia`,
  `ladro`, ...), in qualunque ordine, anche attaccati (`porcodio`) o con
  punteggiatura in mezzo.
- **Espressioni fisse** (`dio morto`, `ostia santa`, ...).
- **Parolacce** tramite radici flesse (`cazz` → cazzo/cazzi/cazzata), gravità 1–5.

### 5.2 Robustezza (anti-evasione)

Lettere ripetute (`diooo`), leetspeak (`p0rc0 di0`), maiuscole/accenti,
spaziature/punteggiatura tra le due parole.

### 5.3 Precisione (niente falsi positivi)

Le parole religiose da sole NON vengono censurate (`credo in Dio`, `madonna che
bello`, `addio`). Anche i moccoli puliti (`porca miseria`) passano.

### 5.4 Cosa fa quando trova qualcosa: il BIP MIRATO

**Niente riformulazione dell'LLM.** Il cervello dice la sua battuta naturale; il
supervisore restituisce gli **span da bippare** (`Moderator.span_censura` via
`Moderator._riduci_match`). La censura è **MIRATA "alla veneta"**: di ogni
parolaccia restano udibili le **prime 2 lettere** e, per parole di **5+ lettere**,
anche l'**ultima**; si bippa solo il **centro**. Così resta riconoscibile:
`cazzo → ca[BIP]o`, `vaffanculo → va[BIP]o`, `porco dio → po[BIP]o di[BIP]`.

La **voce copre quel centro con un BIP sull'audio**:

- **ElevenLabs** (`ElevenLabsSpeaker._say_censura`): endpoint *with-timestamps*
  con `apply_text_normalization="off"` e **verifica che l'allineamento sia 1:1**
  col testo; mappa gli span su tempo (`audio_bip.intervalli_da_allineamento`) e
  `ffmpeg` muta + sovrappone il file BIP (`audio_bip.applica_bip`).
- **Offline** (pyttsx3, `Pyttsx3Speaker._say_con_bip`): **una sola sintesi**
  dell'intera frase, poi bip sul centro con timing **stimato** in proporzione ai
  caratteri (la voce offline non dà i timestamp).
- **mock**: mostra il marcatore `[BIP]` testuale.

In console/log la resa è `Moderator.testo_con_bip` (marcatore `EMILIO_BIP_MARKER`;
file BIP da `assets/beeps/`, `EMILIO_BIP_DIR`). Se il bip audio non riesce,
**ripiego sicuro**: si risintetizza il testo con "bip" parlato (la parolaccia non
viene **mai** udita). Funzioni utili in `audio_bip.py`: `intervalli_da_allineamento`,
`applica_bip`, `concatena_audio`, `scegli_beep`, `testo_sicuro`, `applica_span`.

### 5.5 Controllo dell'amministratore (R7, R8)

La pipeline usa `review()` + `span_censura()` + `testo_con_bip()`. Disattivabile a
runtime: `agent.set_moderazione(True|False)`, `/censura on|off|stato`, all'avvio
`EMILIO_MODERATION=0|1`. Quando è **spenta** non si calcola alcuno span: Emilio
dice l'audio **grezzo**, ma il supervisore **analizza comunque** (per i log).
`Moderator.process()`/`sanitize()` (stile `EMILIO_CENSOR_STYLE`) restano solo come
resa **testuale legacy**, non sulla via del parlato.

### 5.6 Ampliare gli elenchi

In `moderation/lexicon.py`:

- `PROFANITY` — `(radice, gravità, flessione)`
- `BLASPHEMY_DIVINE` — entità divine (incl. grafie venete `madona`/`madone`)
- `BLASPHEMY_QUALIFIER` — qualificatori offensivi
- `BLASPHEMY_FIXED` — espressioni fisse multi-parola
- `PROVOCAZIONI` — insulti/contraddizioni che fanno infuriare Emilio anche senza
  turpiloquio (`scemo`, `inutile`, `ti sbagli`, `rottame`, ...)
- `INTERJECTIONS` — sostituti innocui (uso legacy)

Nessuna modifica al motore (`engine.py`).

---

## 6. La persona (carattere di Emilio)

In `persona.py` come dato (modificabile o caricabile da JSON con `EMILIO_PERSONA`).
Contiene biografia, tratti, stile, interessi, regole. È **tarata per esplodere**
se provocato: da calmo è brontolone bonario e pulito; se insultato/contraddetto
risponde acido e sboccato (la censura è a valle, non nel prompt). Da qui si
costruisce il **system prompt**, che chiede anche un **tag di stato d'animo**
iniziale (vedi §11).

---

## 7. La base LLM (cervello)

`brain.py`, con **tre** implementazioni dietro la stessa interfaccia, scelte da
`EMILIO_LLM=mock|claude|local` (per retrocompatibilità `EMILIO_USE_LLM=1` = `claude`):

- **`MockBrain`** — offline, senza chiavi; repertorio di battute in carattere.
  Reattivo: se l'input contiene un insulto/provocazione risponde sboccato (per
  collaudare censura e reattività).
- **`ClaudeBrain`** — LLM cloud via API di **Claude (Anthropic)**; default
  `claude-opus-4-8`, *adaptive thinking* + *effort*, memoria conversazione.
- **`LocalBrain`** — LLM **locale via Ollama** (sul Mac, offline, senza chiavi
  cloud). Usa l'**API nativa di Ollama** (`POST /api/chat`) con `think:false` per
  disattivare il ragionamento lento dei modelli (es. Gemma 4: col thinking acceso
  la latenza esplode ~30s). Default `gemma4:12b`. Env: `EMILIO_LOCAL_URL` (default
  `http://localhost:11434`), `EMILIO_LOCAL_MODEL`, `EMILIO_LOCAL_THINK`,
  `EMILIO_LOCAL_KEY`, `EMILIO_LOCAL_KEEP_ALIVE` (default `30m`: tiene il modello
  caldo in RAM, niente reload dopo una pausa).

Tutti i cervelli espongono `reply(user_text, umore="")` **e** `reply_stream(...)`
(generatore di pezzi per lo streaming: il default dell'ABC emette un blocco unico,
`LocalBrain`/`ClaudeBrain` fanno streaming vero — Ollama `stream:true`, Anthropic
`messages.stream`). Con `umore="arrabbiato"` (provocazione rilevata, vedi §11) il
testo utente riceve una spinta a rispondere infuriato. **Velocità**: la leva
principale è un modello più piccolo (es. `gemma3:4b`, 2-4× più rapido del 12B) +
risposte brevi (persona "1-2 frasi" + `EMILIO_MAX_TOKENS`, default 220).
`revise()` esiste ancora ma **non è più usato** (la censura è il BIP, niente
riformulazione).

---

## 8. La voce (TTS) — flessibile, a bassa latenza, misurabile (R6)

`speech.py`. Una voce è un **`VoiceProfile`**; il **`VoiceManager`** tiene il
catalogo e permette di cambiare voce a runtime.

| Profilo | Backend | Note |
|---------|---------|------|
| `mock` | mock | stampa soltanto (sviluppo/test) |
| `offline` | pyttsx3 | TTS offline, voce di sistema italiana |
| `veloce` | ElevenLabs | **Flash v2.5**, streaming, bassa latenza |
| `realistico` | ElevenLabs | **Multilingual v2**, massimo realismo |
| `espressivo` | ElevenLabs | Multilingual v2, più teatrale |

Selezione: `EMILIO_VOICE=veloce`, o `agent.set_voce(...)`/`/voce`. La voce
**offline** sceglie una voce di sistema italiana **vera** evitando le voci
"eloquence" (robotiche/incomprensibili); `EMILIO_TTS_VOICE` (default `Luca`,
maschile) sceglie per nome/id, con ripiego su Alice se assente.

- **Bassa latenza**: streaming `/stream` + Flash v2.5; `optimize_streaming_latency`.
  In più la **pipeline streaming** (§3) parla frase per frase mentre l'LLM genera:
  `agent.parla_streaming` spezza il flusso con `_spezza_frasi` (i `...` sono pausa,
  non fine frase) e pronuncia ogni frase appena completa, ciascuna moderata col suo
  BIP. Togglabile (`EMILIO_STREAMING`/`/streaming`).
- **Misurabilità**: ogni `say()` restituisce `SpeechMetrics` (TTFB + totale); in
  streaming `RisultatoParlato.latenza_llm` riporta il **TTFT** (tempo al primo
  token). Da console `/voce test`.
- **Player**: streaming via `mpg123`/`ffplay`; `ffmpeg` **richiesto** per il BIP.

---

## 9. Gli occhi (espressività)

`occhi.py`. `Occhi` ABC + `build_occhi` (`EMILIO_OCCHI=mock|preview`, porta
`EMILIO_OCCHI_PORT` default 8473).

- **`OcchiMock`** — stampa lo stato.
- **`OcchiPreview`** — anteprima nel **browser** (solo stdlib `http.server`) che
  disegna la **faccia del vero Emiglio**: calotta bianca, visiera nera, occhi
  tondi a LED, **bocca animata** mentre parla. Se **arrabbiato** gli occhi
  diventano **forche del diavolo** animate. Scritte di stato pulsanti
  (TI ASCOLTO / STO PENSANDO / PARLO).

Espressioni (`ESPRESSIONI`): `neutro` (verde), `felice`, `arrabbiato` (rosso,
forche), `sorpreso`, `triste`, `pensa` (viola), `parla`, `ascolta`, `spento`.
Direzioni sguardo: centro/sinistra/destra/su/giu. CLI: `/occhi [espressione]`,
`/occhi guarda <dir>`. L'agente li pilota da solo: `pensa` mentre genera, `parla`
o `arrabbiato` mentre parla, `ascolta` mentre ascolta. Sul corpo: futuro backend
`OcchiLed` su LED RGB indirizzabili (NeoPixel).

---

## 10. L'ascolto (STT, microfono)

`ascolto.py` — **a monte** della pipeline. `Ascoltatore` ABC + `build_ascoltatore`
(`EMILIO_ASCOLTO=mock|whisper|mlx`). Base comune `AscoltatoreMic` (registrazione),
le sottoclassi implementano solo `trascrivi`.

- **`MockAscoltatore`** — ritorna una frase fissa (test).
- **`WhisperAscoltatore`** — **faster-whisper** su **CPU** (offline, italiano) con
  `vad_filter` (salta il silenzio → niente allucinazioni tipo "Sottotitoli...").
- **`MlxAscoltatore`** — **mlx-whisper** su **GPU/ANE di Apple Silicon**: sul Mac
  è molto più rapido della CPU. Repo dei pesi MLX risolto da `_risolvi_repo_mlx`
  (`base` → `mlx-community/whisper-base-mlx`).

**Registrazione**: di default **endpointing VAD** (`EMILIO_STT_VAD=1`) — registra
con `sounddevice` finché parli e **smette dopo una pausa** (`_vad_stato`, soglia a
energia auto-calibrata sul rumore di fondo; tetto `EMILIO_STT_MAX`, coda di
silenzio `EMILIO_STT_SILENZIO`). Senza `sounddevice` o con VAD off ripiega su
`ffmpeg` a tempo fisso (`EMILIO_STT_SECONDI`). Il modello viene **pre-caricato**
in sottofondo all'avvio (`agent._prewarm_ascolto`, thread daemon) così la prima
trascrizione non paga il caricamento.

Gira sul **Mac**, non sul Pi. Env: `EMILIO_STT_MODEL` (default `base`),
`EMILIO_STT_LANG` (it), `EMILIO_STT_COMPUTE` (int8, solo CPU), `EMILIO_STT_VAD`,
`EMILIO_STT_MAX`, `EMILIO_STT_SILENZIO`, `EMILIO_STT_SECONDI`, `EMILIO_MIC_DEVICE`
(indice avfoundation per ffmpeg; il VAD usa il microfono di default). Extra:
`.[listen]` (CPU) o `.[listen-mlx]` (Apple Silicon). CLI: `/ascolta [secondi]`
(un turno) e `/conversa [secondi]` (mani libere). Il microfono su macOS richiede
il permesso al terminale.

---

## 11. La reattività (stato d'animo)

Emilio reagisce alle provocazioni. Se l'utente lo **insulta** o lo **contraddice**
— anche **senza** parolacce (`scemo`, `inutile`, `ti sbagli`, `rottame`...) —
`EmilioAgent._provocato_input` lo rileva (`moderation.contiene_provocazione`,
lista `lexicon.PROVOCAZIONI`) **prima** di generare e passa `umore="arrabbiato"`
al cervello, che risponde acido e sboccato (così non si "calma" ai turni dopo).

Lo stato d'animo è **dichiarato dall'LLM** con un tag a inizio risposta, es.
`[arrabbiato] ...`, che `agent._estrai_emozione` **stacca** (non viene pronunciato)
e mette in `RisultatoParlato.emozione`. Il parsing è tollerante (`[molto
arrabbiato]`, `[arrabbiato!]`, virgolette); se fra parentesi non c'è un'emozione
nota lascia il testo intatto. Emozioni: neutro/felice/arrabbiato/sorpreso/triste/
pensa. Lo stato guida gli **occhi** (forche del diavolo se arrabbiato).
Controllabile con `EMILIO_MODERATE_INPUT`.

---

## 12. Il movimento (R1, R2)

`actuators.py`. **`MockMover`** stampa i comandi; **`SerialMover`** invia
`MOVE <azione> <valore>\n` via seriale a un microcontrollore (Arduino) che pilota
i motori. Vocabolario `MOVES`.

Oggi l'**unica motorizzazione attiva** sono i **cingoli** (`avanti`, `indietro`,
`sinistra`, `destra`). `testa_*`, `braccio_*`, `bocca`, `occhi_on/off` sono già in
`MOVES` ma **rinviati al futuro** (non cablati). Controllo manuale: `/muovi avanti
2`, `/azioni`. In arrivo un `NetworkMover` che manda lo stesso protocollo via
**Wi-Fi** al Pi.

---

## 13. Scelte hardware (R5, R9) — mente + corpo

- **Mac = la mente**: orchestratore + LLM (locale Ollama o cloud Claude) +
  supervisore + voce + STT + anteprima occhi. È dove gira il carico pesante in
  sviluppo.
- **Raspberry Pi = il corpo**: motori dei cingoli, **microfono e altoparlante a
  bordo**, link Wi-Fi con la mente. Onboard, non reggendo l'inferenza locale, userà
  le **API cloud** (Claude + ElevenLabs); per questo il Pi può essere modesto.
- Senza rete: cervello `MockBrain` o **LLM locale Ollama** (sul Mac), voce
  `pyttsx3`, STT faster-whisper. **`ffmpeg` richiesto** (BIP + registrazione mic).

Dettaglio componenti del corpo in [`HARDWARE.md`](HARDWARE.md).

---

## 14. Configurazione (variabili d'ambiente)

| Variabile | Default | Significato |
|-----------|---------|-------------|
| `EMILIO_LLM` | (vuoto) | cervello: `mock`/`claude`/`local` (vuoto = `claude` se `EMILIO_USE_LLM=1`, altrimenti `mock`) |
| `EMILIO_USE_LLM` | `0` | retrocompat: `1` = claude |
| `EMILIO_CLAUDE_MODEL` | `claude-opus-4-8` | modello Claude (ex `EMILIO_MODEL`, ancora valido come alias) |
| `EMILIO_MAX_TOKENS` | `220` | tetto risposta: corta = più rapida e meno crediti voce |
| `EMILIO_STREAMING` | `1` | pipeline voce in streaming (parla a frasi); `0` = blocco unico |
| `EMILIO_EFFORT` | `medium` | `low`/`medium`/`high` (Claude) |
| `EMILIO_LOCAL_URL` | `http://localhost:11434` | endpoint Ollama (API nativa) |
| `EMILIO_LOCAL_KEEP_ALIVE` | `30m` | quanto Ollama tiene il modello caldo (`-1` = sempre) |
| `EMILIO_LOCAL_MODEL` | `gemma4:12b` | modello LLM locale |
| `EMILIO_LOCAL_THINK` | `0` | `1` abilita il ragionamento (lento) |
| `EMILIO_LOCAL_KEY` | — | bearer token opzionale per Ollama |
| `EMILIO_MODERATION` | `1` | supervisione (BIP) attiva all'avvio |
| `EMILIO_MODERATE_INPUT` | `1` | rileva insulti/provocazioni nell'input |
| `EMILIO_BIP_MARKER` | `[BIP]` | resa testuale del bip |
| `EMILIO_BIP_DIR` | (pacchettizzati) | cartella dei file BIP |
| `EMILIO_CENSOR_STYLE` | `mask` | resa testuale legacy |
| `EMILIO_VOICE` | (vuoto) | profilo voce; se vuoto deriva da `EMILIO_TTS` |
| `EMILIO_TTS` | `mock` | ripiego se `EMILIO_VOICE` non impostato |
| `EMILIO_TTS_LANG` | `it` | lingua TTS |
| `EMILIO_TTS_VOICE` | `Luca` | voce di sistema pyttsx3 (offline); ripiego Alice |
| `ELEVENLABS_API_KEY` / `ELEVENLABS_VOICE_ID` | — | voce realistica IT |
| `ELEVENLABS_MODEL` | `eleven_multilingual_v2` | modello ElevenLabs (realistico/espressivo) |
| `EMILIO_AUDIO_OUT` | `emilio_voce.mp3` | file audio generato |
| `EMILIO_OCCHI` | `mock` | occhi: `mock`/`preview` |
| `EMILIO_OCCHI_PORT` | `8473` | porta anteprima web occhi |
| `EMILIO_ASCOLTO` | `mock` | STT: `mock`/`whisper` (CPU)/`mlx` (Apple Silicon) |
| `EMILIO_STT_MODEL` | `base` | modello whisper (`tiny`/`base`/`small`/`medium`) |
| `EMILIO_STT_LANG` | `it` | lingua STT |
| `EMILIO_STT_COMPUTE` | `int8` | tipo di calcolo su CPU (`int8`/`float32`) |
| `EMILIO_STT_VAD` | `1` | endpointing: smette quando smetti di parlare; `0` = secondi fissi |
| `EMILIO_STT_MAX` | `12` | (VAD) tetto massimo di registrazione in secondi |
| `EMILIO_STT_SILENZIO` | `0.8` | (VAD) pausa che chiude il turno, in secondi |
| `EMILIO_MIC_DEVICE` | (auto) | indice microfono avfoundation (solo ffmpeg) |
| `EMILIO_STT_SECONDI` | `5` | durata registrazione se il VAD è disattivato |
| `EMILIO_ACTUATORS` | `mock` | `serial`/`mock` |
| `EMILIO_SERIAL_PORT` | `/dev/ttyUSB0` | porta seriale motori |
| `EMILIO_SERIAL_BAUD` | `9600` | baud rate seriale |
| `EMILIO_PERSONA` | — | file JSON con persona custom |

---

## 15. Avvio rapido

### Offline, senza chiavi
```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e .
emilio                 # oppure: python -m emilio
```

### Cervello locale (Ollama) + voce udibile + occhi + ascolto
```bash
pip install -e ".[voice,offline-voice,listen]"
ollama pull gemma4:12b && ollama serve &
EMILIO_LLM=local EMILIO_VOICE=offline EMILIO_OCCHI=preview EMILIO_ASCOLTO=mlx emilio
```

### Emilio "completo" (cloud)
```bash
pip install -e ".[llm,voice]"
export ANTHROPIC_API_KEY=...  ELEVENLABS_API_KEY=...  ELEVENLABS_VOICE_ID=...
export EMILIO_LLM=claude EMILIO_VOICE=realistico   # o veloce
emilio
```

### Da codice
```python
from emilio import EmilioAgent
emilio = EmilioAgent()
ris = emilio.parla("Raccontami una cosa dei tuoi tempi")
print(ris.testo_detto, ris.emozione, ris.report.summary())
```

---

## 16. Comandi della console

| Comando | Azione |
|---------|--------|
| `<testo>` | parla con Emilio (LLM → supervisore → voce) |
| `/di <testo>` | fai dire una frase esatta (passa dal supervisore) |
| `/voci` · `/voce <nome>` · `/voce test [testo]` | voci e prova latenza |
| `/muovi <azione> [valore]` · `/azioni` | movimento manuale + elenco |
| `/occhi [espressione]` · `/occhi guarda <dir>` | espressione/sguardo occhi |
| `/ascolta [secondi]` | parla a voce una volta (microfono → risposta) |
| `/conversa [secondi]` | modalità voce a mani libere |
| `/streaming on\|off\|stato` | pipeline voce: streaming (a frasi) o blocco unico |
| `/censura on\|off\|stato` | controllo amministratore della supervisione |
| `/mod <testo>` | analizza un testo col supervisore (debug) |
| `/reset` · `/aiuto` · `/esci` | memoria, aiuto, uscita |

---

## 17. Test

```bash
pip install -e ".[dev]"
python -m pytest        # 77 test (oppure: python -m unittest discover -s tests)
```

Coprono: supervisore (bestemmie combinatorie, leet, falsi positivi, flessioni,
censura mirata), voce, censura audio, cervello + occhi, reattività + ascolto.
Tutti **offline, senza rete né chiavi**.

---

## 18. Roadmap / prossimi passi

1. **Voce reale** — voce italiana (maschile) su ElevenLabs, `voice_id`, taratura;
   col timing esatto il BIP diventa preciso al millisecondo.
2. **Modello locale non censurato** — per bestemmie garantite a prescindere dal modello.
3. **Carattere** — arricchire `persona.py` (frasi, tormentoni "alla Mosconi").
4. **Corpo Wi-Fi** — `NetworkMover` + Pi; audio (mic/altoparlante) tra mente e corpo.
5. **Wake-word** — togliere del tutto il "parla ora" (il VAD per chiudere il turno
   c'è già: registra finché parli e smette dopo una pausa).
6. **Movimento** — cingoli ora; testa/braccia in futuro.

---

## 19. Tecnologie per massimizzare il potenziale dell'LLM (ricerca)

### 19.1 Far AGIRE l'LLM: tool use / function calling
Esporre il vocabolario dei movimenti come "strumenti" così l'LLM, mentre parla,
decide di emettere `muovi("avanti")` ed Emilio gesticola coerentemente. Salto di
qualità più grande per il personaggio. (Oggi: lo stato d'animo via tag è un primo
passo in questa direzione.)

### 19.2 Agent Skills (Claude)
Cartelle (`SKILL.md` + risorse) caricate solo quando servono: es. *persona-emilio*,
*moccoli-puliti*, *aneddoti*. Descrizioni specifiche = attivazione affidabile.

### 19.3 Voce: modelli ElevenLabs
Multilingual v2 (realismo), Flash v2.5 (latenza, default per `veloce`), Eleven v3
(espressività). Conviene tenere la **nostra pipeline** (LLM → supervisore → TTS) e
usare ElevenLabs **solo** come voce, per mantenere il controllo della censura.

### 19.4 Ingresso vocale (STT) — ✅ fatto
Implementato con **faster-whisper** (vedi §10). Alternative future: Whisper.cpp
sul Pi, o STT cloud.

### 19.5 Parametri Claude
*adaptive thinking* + *effort* per bilanciare qualità/latenza; modello più rapido
(`claude-haiku-4-5`) se la latenza dal vivo è critica.

---

## 20. Note operative

- Il **nucleo** gira con la sola **libreria standard**; le dipendenze
  (`anthropic`, `requests`, `pyttsx3`, `pyserial`, `faster-whisper`) sono
  **opzionali** (extra del `pyproject.toml`) e importate pigramente.
- Tutta la configurazione passa da **variabili d'ambiente**: nessun segreto nel codice.
- **`ffmpeg`** è richiesto per il BIP di censura e per la registrazione del microfono.
