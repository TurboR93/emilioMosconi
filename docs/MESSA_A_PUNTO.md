# Messa a punto di Emilio — come funziona e come correggerlo

Guida operativa per **studiare e correggere** il comportamento di Emilio: il
**carattere** (system prompt / persona) e il **dizionario** (lessico di censura).
Per l'architettura completa vedi [`PROGETTO.md`](PROGETTO.md); per l'uso quotidiano
il [`README.md`](../README.md). Qui si entra nel *cosa toccare per ottenere cosa*.

---

## 0. Il flusso in 30 secondi

```
tu (testo o voce)
   │
   ▼
[ascolto.py]  STT: voce → testo            (solo se parli)
   │
   ▼
[brain.py]    LLM + SYSTEM PROMPT → battuta grezza (con tag [emozione])
   │              ▲ persona.py costruisce il system prompt
   │              ▲ se ti ha provocato, riceve una spinta "arrabbiato"
   ▼
[moderation/] SUPERVISORE: trova le bestemmie → posizioni da bippare
   │              ▲ lexicon.py = il dizionario
   ▼
[speech.py]   VOCE (TTS) + BIP sull'audio  +  [occhi.py]  +  [actuators.py]
```

Due cose si correggono spesso:
1. **come parla / cosa dice** → `src/emilio/persona.py` (§2–§3)
2. **cosa viene bippato** → `src/emilio/moderation/lexicon.py` (§4)

Tutto il resto si regola con le **variabili d'ambiente** (§5).

---

## 1. I quattro "cervelli" e i modelli

`EMILIO_LLM` sceglie il backend:

| Backend | Cos'è | Quando |
|---|---|---|
| `mock` | finto, offline, senza chiavi | test, pipeline |
| `local` | Ollama sul Mac (API nativa `/api/chat`) | **sviluppo offline** |
| `claude` | Anthropic (cloud, SDK `anthropic`) | qualità; **bassa latenza con Haiku** |
| `cloud` | provider OpenAI-compatibile (Groq/OpenRouter/OpenAI) | **latenza minima** con modelli open |

In sviluppo si usa **local**. Il modello locale si sceglie con `EMILIO_LOCAL_MODEL`
(default `gemma4:12b`, il più coerente nei test).

Modelli locali provati (tutti scaricati con `ollama pull <nome>`):

| Modello | Note dai test |
|---|---|
| **gemma4:12b** | Il più **coerente** e in tema; brontolone arguto. Default. |
| aya-expanse:8b | Molto colorito e leggero, ma meno costante. |
| mistral-nemo | Dialetto pesante ma a volte sgrammaticato. |
| gemma2:9b | Buono, ogni tanto generico. |
| qwen2.5:7b | Scartato: poco coerente per questo uso. |

Cambiare modello al volo: `EMILIO_LOCAL_MODEL=aya-expanse:8b ./avvia.sh`, oppure
**dalla console** `/cervello <backend>` + `/modello-llm <nome>` (§6). Per confrontare i
locali offline: `python tools/prova_carattere.py <modello>` (§6).

### Cervello online a bassa latenza (TTFT)

Per il dialogo dal vivo conta il tempo al primo token; la console stampa il TTFT a
ogni risposta. Due preset (lo streaming è già attivo):

```bash
# Claude veloce (Haiku, niente thinking — il default)
EMILIO_LLM=claude EMILIO_CLAUDE_MODEL=claude-haiku-4-5 ANTHROPIC_API_KEY=… ./avvia.sh
#   EMILIO_CLAUDE_THINK=adaptive  → ragionamento+effort (più qualità, più lento) su Opus/Sonnet

# Cloud generico (Groq = latenza minima con modelli open)
EMILIO_LLM=cloud EMILIO_CLOUD_MODEL=llama-3.1-8b-instant EMILIO_CLOUD_KEY=… ./avvia.sh
#   altri provider: EMILIO_CLOUD_URL=https://openrouter.ai/api/v1  (o api.openai.com/v1)
```

> Sul Raspberry si userà il **cloud** (`claude` o `cloud`): il Pi non regge
> l'inferenza locale. Il caching del system prompt NON aiuta qui: la persona è
> sotto la soglia minima cacheable, quindi non viene messa in cache.

---

## 2. Il CARATTERE: il system prompt (`persona.py`)

La persona è un **dataclass** di soli dati: biografia, età, tratti, stile,
interessi, regole. Il metodo `system_prompt()` li concatena nel testo che riceve
l'LLM. **Modificare quei campi = cambiare il carattere**, senza toccare codice.

Mappa campo → effetto:

| Campo (`persona.py`) | Controlla |
|---|---|
| `biografia`, `eta` | Chi è Emilio (lo sfondo). |
| `tratti` | Il temperamento (es. "ama divagare" → se divaga troppo, **toglilo**). |
| `stile` | *Come* parla: frasi brevi, intercalari, niente tono da assistente. |
| `interessi` | Di cosa parla volentieri (calcio d'epoca, cucina, ...). |
| `regole` | Le **istruzioni operative** numerate: brevità, reazione, turpiloquio, perifrasi. È qui che si lavora di fino. |

### Il system prompt RESO (quello che l'LLM legge davvero)

Per vederlo in qualunque momento:
```bash
python -c "from emilio.persona import Persona; print(Persona().system_prompt())"
```
Stato attuale (sintesi delle regole che contano per il tuo uso):

- **R3 — brevità**: una o due frasi, asciutte (è una voce, non un saggio). Se
  vuoi sfoghi più lunghi alza `EMILIO_MAX_TOKENS`; se vuoi più stringato, abbassalo.
- **R5 — arguzia prima**: la battuta deve avere CONTENUTO pertinente; la bestemmia
  è il *condimento*, non il piatto.
- **R6 — reazione**: se insultato/contraddetto esplode acido, infila UNA
  parolaccia/bestemmia *in mezzo* alla frase, **varia sempre** (mai lo stesso
  moccolo ripetuto), più arrabbiato = più tagliente (non più ripetitivo).
- **R7 — perifrasi argute**: predilige minacce surreali con spessore lessicale
  (es. *"te dae tante sberle finché diventano dispari"*), non solo moccoli.
- **Tag d'animo**: ogni risposta inizia con `[neutro|felice|arrabbiato|sorpreso|
  pensa|triste]`, che l'agente **stacca** prima di pronunciare (vedi §3).

### Persona personalizzata da file — e cambio al volo

Puoi caricare una persona alternativa senza toccare il codice, **all'avvio**:
```bash
EMILIO_PERSONA=tools/persona_germano.json ./avvia.sh
```
…oppure **dalla console, a runtime**, con `/persona <nome|file>`:
```text
tu> /persona germano       # carica tools/persona_germano.json
tu> /persona default       # torna alla persona di serie
tu> /persona               # elenca quelle disponibili
```
Un nome semplice (`germano`) viene cercato come `tools/persona_germano.json`
(o `persona_germano.json` / `germano.json`). Il JSON ha le stesse chiavi del
dataclass (`biografia`, `tratti`, `regole`, ...). Cambiare persona **azzera la
memoria** (vedi §6). Ne tieni quante ne vuoi: una per ogni carattere da provare.

### Leve di correzione tipiche

| Vuoi che... | Tocca |
|---|---|
| bestemmi **di meno** | R5/R6: rafforza "condimento, non piatto"; togli enfasi |
| bestemmi **di più** | R6: alza il tono ("a raffica") — ma rischi ripetizione |
| **divaghi meno** / resti sulla domanda | togli il tratto "ama divagare", rafforza R5 "rispondi davvero a quello che ti dicono" |
| **frasi più corte** | R3 + abbassa `EMILIO_MAX_TOKENS` |
| **non ripeta** lo stesso moccolo | R6 (già lo dice) + alza `EMILIO_LOCAL_REPEAT_PENALTY` |

---

## 3. La REATTIVITÀ (quando si arrabbia)

Tre pezzi, tutti in `agent.py` + `moderation/`:

1. **Rilevazione provocazione** — `EmilioAgent._provocato_input` chiama
   `moderation.contiene_provocazione`, che è vera se il testo dell'utente contiene
   un insulto/contraddizione (lista `lexicon.PROVOCAZIONI`: `scemo`, `inutile`,
   `ti sbagli`, `rottame`...) **oppure** una parolaccia. Interruttore:
   `EMILIO_MODERATE_INPUT`.
2. **Spinta all'LLM** — se provocato, al messaggio utente viene aggiunta una nota
   (`brain._NUDGE_ARRABBIATO`) che impone una risposta infuriata: serve perché i
   modelli tendono a "calmarsi" ai turni successivi.
3. **Tag d'animo** — l'LLM apre con `[arrabbiato]` ecc.; `agent._estrai_emozione`
   lo stacca (non si pronuncia) e lo usa per gli **occhi** (forche del diavolo se
   arrabbiato). Il parsing è robusto: stacca anche i tag d'animo **inventati** dal
   modello (`[scettico]`, `[brontolo bonario]`) per non farli finire pronunciati,
   ma preserva i contenuti veri fra parentesi (`[Bologna]`, `[3-1]`).

Per **ampliare ciò che lo fa infuriare** aggiungi termini a `lexicon.PROVOCAZIONI`.

---

## 4. Il DIZIONARIO e la censura (`moderation/`) — maneggiare con cura

Il supervisore **non** riformula: trova le parti "sporche" e la voce le copre con
un BIP. Le liste stanno in [`lexicon.py`](../src/emilio/moderation/lexicon.py); il
motore (match) in `engine.py` — **non serve toccare il motore**, solo le liste.

### ⚠️ REGOLA D'ORO: sono RADICI, non parole intere

In `PROFANITY` ogni voce è `(radice, severità, inflect)`. Con `inflect=True` il
motore **aggiunge da solo le desinenze**:

```
("cazz", 3, True)   →  becca  cazzo, cazzi, cazzata, cazzone, cazzata...
("cazzo", 3, True)  →  becca SOLO "cazzo"   ←  "cazzata" SFUGGE!
```

**Non "completare" le radici.** Sembrano troncate ma è voluto. Per aggiungere una
parolaccia nuova, metti la **radice** (es. `("sega", 1, True)`), non la parola intera.

### Le liste

| Lista | A cosa serve |
|---|---|
| `PROFANITY` | Parolacce: `(radice, severità 1-5, inflect)`. |
| `BLASPHEMY_DIVINE` | Entità divine (`dio`, `madonna`, `cristo`, `ostia`...). **Da sole NON si censurano** (così "credo in Dio" passa). |
| `BLASPHEMY_QUALIFIER` | Qualificatori (`cane`, `porco`, `mostro`, `serpente`...). Il motore combina **ogni** divina con **ogni** qualificatore, in **qualsiasi ordine**, anche attaccati. |
| `BLASPHEMY_FIXED` | Bestemmie intere non generabili dalla combinazione (`madonnaccia`, `dea madonna`). |
| `PROVOCAZIONI` | Insulti che fanno infuriare Emilio (anche senza parolacce). |
| `INTERJECTIONS` | *Legacy*: NON usate nel parlato attuale (la censura è un BIP, non una sostituzione). |

### Come si fa a beccare una bestemmia nuova del gruppo

Quasi sempre basta aggiungere il **qualificatore** a `BLASPHEMY_QUALIFIER`: da
solo copre tutte le combo. Es. aggiungendo `"verme"` ottieni *gratis* `dio verme`,
`madonna verme`, `vermedio`... Robustezza già inclusa nel motore: lettere ripetute
(`diooo`), leetspeak (`p0rc0`), `k` veneta (`diokan`, `porko`), accenti, maiuscole.

### Cosa viene bippato e come

- **Solo le bestemmie** (`EMILIO_BIP_SOLO_BESTEMMIE=1`, default). Le parolacce si
  sentono in chiaro ma restano *rilevate* (per i log e per farlo arrabbiare).
- Censura **"alla veneta"**: di ogni parola restano udibili le **prime 2 lettere**
  (e l'ultima per parole di 5+), si bippa solo il **centro** → `po[BIP]o di[BIP]`.
- Disattivabile dall'admin: `/censura off` (runtime) o `EMILIO_MODERATION=0` (avvio).

### Come TESTARE le modifiche al dizionario

```bash
# dentro la console:
/mod dio verme        → ti dice cosa rileva (senza far parlare Emilio)

# da terminale, la suite del lessico:
python -m pytest tests/test_moderation.py tests/test_lessico_gruppo.py -q
```

---

## 5. Le manopole (variabili d'ambiente)

Tutte in [`config.py`](../src/emilio/config.py). Le più utili per la messa a punto:

| Variabile | Default | Effetto |
|---|---|---|
| `EMILIO_LLM` | `mock` | backend cervello: `mock`/`local`/`claude`/`cloud` |
| `EMILIO_LOCAL_MODEL` | `gemma4:12b` | modello Ollama |
| `EMILIO_CLAUDE_MODEL` | `claude-haiku-4-5` | modello Claude (ex `EMILIO_MODEL`, ancora valido); default Haiku = TTFT basso; più capacità → `claude-sonnet-4-6`/`claude-opus-4-8` |
| `EMILIO_CLAUDE_THINK` | (off) | `adaptive` = ragionamento+effort (qualità, più lento); off = TTFT basso, ok con Haiku |
| `EMILIO_CLOUD_URL` | `…groq.com/openai/v1` | endpoint OpenAI-compat. (Groq/OpenRouter/OpenAI) |
| `EMILIO_CLOUD_MODEL` | `llama-3.3-70b-versatile` | modello cloud (`llama-3.1-8b-instant` = più rapido) |
| `EMILIO_CLOUD_KEY` | (vuoto) | chiave API del provider cloud |
| `EMILIO_MAX_TOKENS` | `220` | lunghezza max risposta (corta = più rapida, più asciutta) |
| `EMILIO_LOCAL_TEMP` | `0.85` | varietà/creatività (più alto = più vario) |
| `EMILIO_LOCAL_REPEAT_PENALTY` | `1.3` | penalità ripetizione (alza a `1.4` se ripete) |
| `EMILIO_LOCAL_KEEP_ALIVE` | `30m` | tiene il modello caldo in RAM |
| `EMILIO_STREAMING` | `1` | parla frase per frase (TTFT basso); `0` = a blocco |
| `EMILIO_VERBOSO` | `1` | monitor: mostra in tempo reale (💬) il testo che sta per dire; `0` = off |
| `EMILIO_MODERATION` | `1` | censura on/off all'avvio |
| `EMILIO_BIP_SOLO_BESTEMMIE` | `1` | bippa solo bestemmie; `0` = anche parolacce |
| `EMILIO_MODERATE_INPUT` | `1` | rileva le provocazioni nell'input |
| `EMILIO_VOICE` | `offline` (in `.env.local`) | `offline` (robotica, gratis) / `veloce`/`realistico`/`espressivo` (ElevenLabs). `mock` (stampa, nessun audio) resta valido via env ma è **nascosto dal menu** `/voce` |
| `EMILIO_VOCE_EMOZIONE` | `1` | voce ElevenLabs col **tono modulato** dallo stato d'animo (arrabbiato instabile/enfatico, triste posato…); `0` = tono fisso da profilo. La voce `offline` resta piatta |
| `EMILIO_ASCOLTO` | `mock` | STT: `mock`/`whisper`/`mlx` |

> Le chiavi e le scelte personali (voce, modello) stanno in `.env.local`
> (ignorato da git), caricato da `avvia.sh`. Esempio: `EMILIO_VOICE=veloce ./avvia.sh`
> forza la voce ElevenLabs per quella sessione.

---

## 6. Come testare e iterare

**Console** (`./avvia.sh`):

All'avvio la console stampa un **banner** con lo stato (cervello, persona, voce…)
e le **azioni principali**. Cambi le cose base **al volo, senza riavviare**:

| Comando | Uso |
|---|---|
| `<testo>` | parla con Emilio (a testo) |
| `/conversa [secondi]` | conversazione a **voce** a mani libere |
| `/cervello [..]` | cambia il **cervello** (mock/local/claude/cloud); **senza arg = menu numerato** |
| `/modello-llm [nome]` | cambia il **modello dell'LLM/cervello**; **senza arg = menu numerato** (Ollama dal vivo, o preset Claude/cloud); o nome diretto. Alias: `/modello` |
| `/persona [nome\|file]` | cambia **personalità**; **senza arg = menu numerato** delle persona disponibili; o nome/file diretto |
| `/voce [nome]` | cambia **voce**; **senza arg = menu numerato** (voci reali: offline/ElevenLabs; `mock` solo per nome); `/voce test` per provarla |
| `/think off\|adaptive` | **latenza Claude**: `off` = veloce (Haiku) · `adaptive` = più qualità (Opus/Sonnet) |
| `/lunghezza <n>` | lunghezza max risposta (`max_tokens`): corta = più rapida |
| `/provider groq\|openrouter\|openai\|<url>` | endpoint del cervello **cloud** |
| `/temp <n>` | varietà/creatività del campionamento (local/cloud; es. `0.6`) |
| `/verboso on\|off` | **monitor**: mostra in tempo reale (💬) il testo che sta per dire, frase per frase |
| `/stato` | mostra la configurazione attiva + le manopole di latenza |
| `/di <frase>` | fagli dire una frase esatta (per provare voce/bip) |
| `/mod <frase>` | cosa rileva il supervisore (debug dizionario) |
| `/voce test [testo]` | prova la voce e misura la latenza |
| `/censura on\|off` · `/streaming on\|off` | interruttori a runtime |
| `/reset` | azzera la memoria (utile se "si incarta") |
| `/occhi [espressione]` | prova gli occhi |

> `/cervello`, `/modello-llm` e `/persona` **ricostruiscono il cervello** e quindi
> **azzerano la memoria** della conversazione (comportamento voluto: nuova mente,
> nuovo personaggio).

**Batteria del carattere** (offline, niente voce/crediti):
```bash
python tools/prova_carattere.py              # modello di default
python tools/prova_carattere.py aya-expanse:8b
```
Manda una conversazione multi-turno e mostra, per ogni battuta, tag emozione +
risposta + cosa verrebbe bippato + l'elenco dei moccoli usati (per vedere se
ripete). È lo strumento giusto per giudicare una modifica a persona/lessico.

**Vocabolario dal gruppo WhatsApp**: `tools/estrai_lessico.py` (vedi
[`tools/README.md`](../tools/README.md)).

**Suite completa**: `python -m pytest` (84 test). Gira contro il pacchetto
installato: serve `pip install -e ".[dev]"` (src-layout).

---

## 7. Mappa dei file (dove correggere cosa)

| Voglio cambiare... | File |
|---|---|
| carattere, regole, stile, system prompt | `src/emilio/persona.py` |
| dizionario (parolacce/bestemmie/provocazioni) | `src/emilio/moderation/lexicon.py` |
| logica di match/censura (raramente) | `src/emilio/moderation/engine.py` |
| reattività, tag emozione, pipeline, streaming | `src/emilio/agent.py` |
| cervello locale/cloud, campionamento | `src/emilio/brain.py` |
| voce, profili, BIP audio | `src/emilio/speech.py`, `src/emilio/audio_bip.py` |
| occhi | `src/emilio/occhi.py` |
| ascolto (STT) | `src/emilio/ascolto.py` |
| default delle opzioni | `src/emilio/config.py` |
| chiavi/scelte locali (NON nel repo) | `.env.local` |

---

## 8. Note dai test (stato attuale, gemma4:12b)

- ✅ Coerente e in tema; brontolone bonario da calmo; minacce argute e perifrasi
  ricche da arrabbiato; racconta aneddoti pertinenti.
- ⚠️ A volte è **più lungo** di "una/due frasi" → se dà fastidio, abbassa
  `EMILIO_MAX_TOKENS` (es. 140) e/o rafforza R3.
- ⚠️ Ripete `vaffanculo` ogni tanto fra turni diversi → alza
  `EMILIO_LOCAL_REPEAT_PENALTY` a `1.4`.
- ⚠️ Inventa combo creative garbate ("madonna zanzaeerafeleata") che NON vengono
  bippate perché non sono nel dizionario: è un limite del modello, non un bug —
  le combo *reali* (dio/madonna/cristo + qualificatore noto) vengono coperte.
