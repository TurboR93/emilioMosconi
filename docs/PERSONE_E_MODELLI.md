# Persone e modelli: selezione auto-aggiornante

> Per i futuri sviluppatori di **Emilio**.
> Come funziona la console interattiva che fa scegliere CERVELLO, MODELLO e PERSONA
> con menu numerati, e perché nella maggior parte dei casi **non devi toccare codice**
> quando esce un modello nuovo o aggiungi una persona.

File di riferimento: [`src/emilio/cli.py`](../src/emilio/cli.py) (menu e fetcher),
[`src/emilio/agent.py`](../src/emilio/agent.py) (preset provider, attivazione, nomi
brevi), [`src/emilio/persona.py`](../src/emilio/persona.py) (dati persona),
[`src/emilio/config.py`](../src/emilio/config.py) (env `EMILIO_*`).

---

## 1. Principio: "zero hardcoding dove possibile"

L'obiettivo è che **i nuovi elementi compaiano da soli** nei menu, senza modificare
il codice:

- una **persona** nuova = un file JSON in più → appare nel menu `/persona`;
- un **modello** nuovo del provider = lo elenca la fonte "viva" (Ollama / API del
  provider) → appare nel menu `/modello-llm`.

Dove un elenco vivo non è disponibile (offline, senza chiave, SDK assente) si
**ripiega** su liste curate a mano (`_MODELLI_CLAUDE` e `_MODELLI_CLOUD` in `cli.py`).
I curati sono **solo una rete di sicurezza**, non la verità: quando la fonte live
risponde, vince sempre lei.

I menu sono costruiti da `_scegli(titolo, opzioni, attivo)` (`cli.py`): numerati, col
valore attivo marcato `← attivo`, e accettano sia il numero sia un nome libero (così
un power user può scrivere un id fuori elenco). Il **modello attualmente in uso** è
sempre inserito in testa anche se non compare nella fonte live: lo fa
`_modelli_disponibili`, con `nomi.insert(0, attuale)` quando l'attuale è fuori elenco.

---

## 2. PERSONE — aggiungerne una senza scrivere codice

### Come si aggiunge

1. Crea un file `tools/persona_<nome>.json` (es. `tools/persona_pirata.json`).
2. Fine. Compare **da solo** nel menu `/persona` come `pirata`, e lo selezioni con
   `/persona pirata` o dal menu numerato.

### Come funziona la scoperta automatica

- `cli._lista_persone()` fa il **glob** di `tools/persona_*.json` **e** di
  `persona_*.json` nella cwd, ricava il nome breve con `agent._nome_persona()`
  (`tools/persona_veterano.json` → `veterano`) e antepone sempre `"default"` (la
  persona di serie, senza file).
- `cli._risolvi_persona(arg)` mappa il nome al file provando, in ordine, questi
  candidati: `tools/persona_<nome>.json`, `persona_<nome>.json`, `<nome>.json`,
  `tools/<nome>.json` (primo che esiste vince). Un percorso che finisce in `.json` è
  preso così com'è. `default`/`base`/`emilio` → `Persona()` di serie. Se nessun
  candidato esiste, solleva `ValueError` con l'elenco dei nomi disponibili.
- Il caricamento vero è `Persona.from_json(path)` (`persona.py`, fa `cls(**data)`);
  l'agente la attiva con `agent.set_persona(persona, origine)`, che **ricostruisce il
  cervello** col nuovo system prompt e **azzera la memoria**.

### Chiavi del JSON

Le chiavi sono **esattamente** i campi del dataclass `Persona` (`persona.py`):
`from_json` fa `cls(**data)`, quindi una chiave non prevista solleva `TypeError`.
Tutti i campi hanno un default: nel JSON metti **solo** quelli che vuoi sovrascrivere.
Esempi: `tools/persona_veterano.json`, `tools/persona_machiavelli.json`.

| Chiave | Tipo | Significato |
|---|---|---|
| `nome` | str | Nome del personaggio (default "Emilio"; resta "Emilio" salvo motivi forti). |
| `eta` | str | Età/inquadramento (default "sulla sessantina"). |
| `biografia` | str | Chi è: il blocco identitario principale del system prompt. |
| `tratti` | list[str] | Tratti caratteriali (permalosità, ironia, ecc.). |
| `stile` | str | Come parla (registro, intercalari, lunghezza frasi). |
| `interessi` | list[str] | Temi su cui si accende. |
| `regole` | list[str] | Vincoli forti (resta nel personaggio, brevità, come/quando si infuria, ecc.). |

> Il tag di stato d'animo iniziale (`[neutro|felice|arrabbiato|sorpreso|pensa|triste]`)
> è **già imposto** dal `system_prompt()` di base, non dal JSON: non serve ripeterlo
> nelle regole.
>
> Promemoria di carattere: la **censura è a valle** (supervisore + BIP), non nel
> prompt. La persona può infilare parolacce/bestemmie *in mezzo* alle frasi quando è
> provocata; ci pensa il moderatore a coprirle. Per la taratura fine di carattere e
> lessico vedi [`docs/MESSA_A_PUNTO.md`](MESSA_A_PUNTO.md).

---

## 3. MODELLI per backend — fonte viva + fallback curato

Tutto passa da **`cli._modelli_disponibili(agent)`**, che sceglie la fonte in base a
`agent.backend_cervello` e ripiega sui curati se la fonte live è vuota. Il backend si
imposta con `agent.set_cervello(...)` (env `EMILIO_LLM`); il modello con
`agent.set_modello(...)`. Lo schema della risposta `GET /models` è
**OpenAI-compatibile** e identico per tutti i provider cloud: la chiave top-level
`data` è un array di oggetti modello e l'id sta in `data[].id`.

### `mock`
Nessun modello → menu vuoto (è il backend offline di default, mock-first).

### `local` (Ollama) — **già auto-aggiornato**
- Fonte viva: `cli._ollama_modelli()` esegue `ollama list` (subprocess, timeout 5 s,
  best-effort) e prende la prima colonna di ogni riga (salta l'header).
- **Nessun fallback curato:** se Ollama non c'è il menu è vuoto (scarichi un modello
  con `ollama pull` e ricompare da solo).
- Env: `EMILIO_LOCAL_MODEL` (default `gemma4:12b`), `EMILIO_LOCAL_URL` (default
  `http://localhost:11434`).

### `cloud` (provider OpenAI-compatibile) — **già auto-aggiornato**
- Fonte viva: `cli._cloud_modelli(url, key)` fa `GET {EMILIO_CLOUD_URL}/models`, header
  `Authorization: Bearer {key}` **solo se la chiave c'è**, ed estrae **`data[].id`**.
  Scarta le voci **non-chat** (TTS/STT/embeddings/immagini/moderation) con il filtro
  `_NON_CHAT`, poi ordina. `requests` importato pigramente; qualsiasi errore
  (rete/chiave/schema) → `[]`.
- **Tetto a 60 voci** nel menu: `nomi = vivi[:60]`. Serve per provider come OpenRouter,
  che ne ha **centinaia** (400+): senza tetto il menu numerato sarebbe ingestibile.
  Gli altri restano raggiungibili scrivendo l'id a mano (`_scegli` accetta nomi liberi).
- Fallback curato (solo se la fonte live è vuota): `_MODELLI_CLOUD[provider]`, dove il
  provider è dedotto dall'URL con `agent._nome_provider()`.
- Env: `EMILIO_CLOUD_URL` (default Groq `https://api.groq.com/openai/v1`),
  `EMILIO_CLOUD_MODEL` (default `llama-3.3-70b-versatile`), `EMILIO_CLOUD_KEY`. Il
  preset si cambia anche a runtime con `/provider groq|openrouter|openai|<url>`.

Dettagli per provider (verificati; `data[].id` vale per tutti):

| Provider | Endpoint `/models` | Auth | Note operative |
|---|---|---|---|
| **Groq** | `https://api.groq.com/openai/v1/models` | `Bearer $EMILIO_CLOUD_KEY` | Non paginato; la lista include whisper/tts/guard, **scartati** dal filtro `_NON_CHAT`. Più rapidi: `llama-3.1-8b-instant` (~560 tok/s), `openai/gpt-oss-20b` (~1000 tok/s). I `preview` possono essere ritirati senza preavviso: non per la produzione. id case-sensitive, col prefisso owner (`openai/`, `meta-llama/`). |
| **OpenRouter** | `https://openrouter.ai/api/v1/models` | **Nessuna** (endpoint pubblico). | 400+ modelli, **non paginato** (un solo array). Il **tetto a 60** del menu è essenziale. Query opzionali lato server: `order=latency-low-to-high`, `category`, `supported_parameters`. Gli id possono cambiare (alias che redirigono al `canonical_slug`): usa **`id`** come chiave. |
| **OpenAI** | `https://api.openai.com/v1/models` | `Bearer $EMILIO_CLOUD_KEY` | Non paginato; include embedding/tts/whisper/dall-e/moderation/fine-tuned, **scartati** dal filtro `_NON_CHAT` (restano comunque eventuali snapshot datati). `owned_by` può essere l'org per i fine-tuned. |

> **Caching consigliato (TODO, non ancora implementato):** oggi `_modelli_disponibili`
> chiama l'API **a ogni apertura del menu** `/modello-llm`. Tutti i provider raccomandano
> una cache con TTL (es. 1 h per Groq, 1–24 h per OpenAI/OpenRouter) o un fetch a
> startup, non una chiamata per apertura. Quando servirà, aggiungere una cache
> in-memory con timestamp dentro `cli.py` (resta stdlib, nessuna nuova dipendenza).

### `claude` (Anthropic) — **già auto-aggiornato**
- Fonte viva: `cli._claude_modelli()` usa `client.models.list()` (`import anthropic`
  pigro) e tiene gli id che iniziano per `claude`. L'endpoint elenca i modelli **dal
  più recente al più vecchio**, quindi i nuovi compaiono in testa da soli.
- **Attenzione paginazione:** l'implementazione itera **direttamente** il risultato di
  `models.list()` (`for m in client.models.list()`), e gli SDK auto-paginano così.
  **NON** usare `.data`, che restituisce solo la prima pagina (default `limit=20`).
- Preferisci gli **alias dateless/pinned** (es. `claude-opus-4-8`, `claude-sonnet-4-6`,
  `claude-haiku-4-5`) agli id datati (es. `claude-haiku-4-5-20251001`): l'API
  restituisce entrambi.
- Auth via SDK: basta `ANTHROPIC_API_KEY` nell'ambiente (header REST equivalenti:
  `x-api-key` + `anthropic-version: 2023-06-01`; endpoint GA, nessun header beta).
- Fallback curato: `_MODELLI_CLAUDE = ["claude-haiku-4-5", "claude-sonnet-4-6",
  "claude-opus-4-8"]` (usato quando manca SDK o chiave).
- Env: `EMILIO_CLAUDE_MODEL` (default `claude-opus-4-8`; `EMILIO_MODEL` resta come alias deprecato).
- **Caveat:** la Models API **non** è disponibile su Amazon Bedrock né Google Vertex
  (lì la lista modelli va presa dalla console/API del provider). Per bassa latenza il
  candidato è `claude-haiku-4-5` (il più veloce, 200K context); `claude-sonnet-4-6` è il
  compromesso; `claude-opus-4-8` solo se serve più capacità.

---

## 4. Come ESTENDERE

### Aggiungere un nuovo provider cloud (preset URL + fallback)
1. **URL preset** → aggiungi una voce a `_PROVIDER_URLS` in `agent.py` (oggi: `groq`,
   `openrouter`, `openai`). Così l'utente scrive `groq`/`openrouter`/… invece dell'URL
   completo, e `_nome_provider()` mostra il nome breve in console (e fa il mapping
   inverso URL → nome).
2. **Fallback curato** → aggiungi `"<provider>": [...]` a `_MODELLI_CLOUD` in `cli.py`.
   **La chiave deve coincidere col nome breve restituito da `_nome_provider`** (cioè la
   stessa chiave usata in `_PROVIDER_URLS`), altrimenti il fallback non viene mai trovato.
3. **Nient'altro:** se l'endpoint è OpenAI-compatibile (`GET /models` con `data[].id`),
   `_cloud_modelli` lo gestisce già. A runtime basta `/provider <nome>` (o
   `EMILIO_CLOUD_URL`) e la chiave (`EMILIO_CLOUD_KEY`).

### Aggiornare i fallback curati
- Claude: `_MODELLI_CLAUDE` in `cli.py`.
- Cloud: `_MODELLI_CLOUD[provider]` in `cli.py`. Valori attuali: `groq` →
  `llama-3.1-8b-instant`, `llama-3.3-70b-versatile`; `openai` → `gpt-4o-mini`, `gpt-4o`;
  `openrouter` → `meta-llama/llama-3.3-70b-instruct`, `google/gemini-2.0-flash-001`.
- Tienili **corti** (2–4 voci, i più veloci/economici): servono solo offline.

### Dove mettere le cose nel codice
- Logica di scelta della fonte → **`cli._modelli_disponibili(agent)`** (punto unico).
- Fetcher per backend → `cli._ollama_modelli` / `_cloud_modelli` / `_claude_modelli`
  (+ filtro `_NON_CHAT`).
- Menu numerato → `cli._scegli`. Modello attivo → `cli._modello_attuale` (legge
  `local_llm_model` / `claude_model` / `cloud_llm_model` dalla config).
- Scoperta persone → `cli._lista_persone` / `_risolvi_persona`.
- Attivazione → `agent.set_cervello` / `set_modello` / `set_persona` (tutte e tre
  **ricostruiscono il cervello e azzerano la memoria**, con rollback se la build fallisce).
- Convenzioni: **italiano**; **core solo stdlib**; librerie esterne (`requests`,
  `anthropic`) **importate pigramente** dentro il fetcher; ogni nuova opzione via **env
  `EMILIO_*`** in `config.py`; tutto deve girare anche in **mock** offline.

---

## 5. Checklist "è uscito un modello / una persona nuova"

### Modello nuovo del provider (local / cloud / claude)
- **Cosa NON devi fare:** niente. Compare da solo dalla fonte viva (`ollama list`,
  `GET /models`, `models.list()`). Nessun commit.
- **Cosa puoi toccare (opzionale):** il fallback curato (`_MODELLI_CLAUDE` /
  `_MODELLI_CLOUD`), se vuoi che compaia **anche offline / senza chiave**. È l'unica
  modifica di codice mai necessaria, ed è facoltativa.

### Persona nuova
- **Cosa NON devi fare:** niente codice. Nessuna lista da aggiornare in `cli.py`.
- **Cosa devi fare:** creare `tools/persona_<nome>.json` con le chiavi della §2.
  Compare da solo in `/persona`.

### Nuovo provider cloud
- **Devi toccare:** `_PROVIDER_URLS` (`agent.py`) per il preset URL, e `_MODELLI_CLOUD`
  (`cli.py`) per il fallback (stessa chiave del nome breve). I modelli live arrivano da
  soli se l'API è OpenAI-compatibile.

### Manutenzione periodica (raccomandata, non obbligatoria)
- Potare i fallback curati dai modelli ritirati (su Groq i `preview` spariscono senza
  preavviso).
- Quando le chiamate live diventeranno frequenti/lente, introdurre il **caching con
  TTL** in `_modelli_disponibili` (vedi TODO §3).

---

*Basata sullo stato attuale di `src/emilio/cli.py`, `agent.py`, `persona.py`,
`config.py`. Dati provider (endpoint/auth/`data[].id`) verificati per Groq, OpenRouter,
OpenAI, Anthropic.*
