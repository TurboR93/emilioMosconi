"""Cervello di Emilio: genera le risposte (la "base LLM").

Due implementazioni dietro la stessa interfaccia:
  * MockBrain  -> funziona offline, senza chiavi: utile per provare la pipeline
                  e i test (può anche restituire frasi "sporche" per verificare
                  il supervisore).
  * ClaudeBrain -> usa l'API di Claude (Anthropic). È la base LLM vera (cloud).
  * LocalBrain  -> LLM locale via server compatibile OpenAI (es. Ollama con
                   Gemma): gira sul Mac, offline e senza chiavi cloud.

Il supervisore di censura NON sta qui: il cervello genera, il supervisore
controlla a valle (vedi agent.py). Così la base LLM e la supervisione restano
componenti separati e sostituibili.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from collections.abc import Iterator

from .persona import Persona

# Spinta una-tantum quando l'utente provoca: l'LLM tende a "calmarsi" nei turni
# successivi, qui lo si ri-infuria per quel turno (vedi agent._provocato_input).
_NUDGE_ARRABBIATO = (
    "\n\n(L'utente ti ha appena offeso o contraddetto: rispondi INFURIATO, "
    "acido e sboccato — parolacce e bestemmie venete a raffica, senza trattenerti.)"
)


def _con_umore(user_text: str, umore: str) -> str:
    """Aggiunge una spinta al testo utente in base all'umore rilevato."""
    if umore == "arrabbiato":
        return user_text + _NUDGE_ARRABBIATO
    return user_text


def _claude_extra_kwargs(think: str, effort: str) -> dict:
    """Parametri opzionali della richiesta Claude in base alla modalità 'think'.

    - "adaptive" -> ragionamento adattivo + effort (più qualità su Opus/Sonnet,
      ma latenza maggiore);
    - "" / "off" (default) -> nessun parametro extra: richiesta minima, TTFT più
      basso, e indispensabile con Haiku (dove 'effort' darebbe 400).
    Funzione pura (niente SDK): testabile offline.
    """
    if (think or "").lower() == "adaptive":
        return {"thinking": {"type": "adaptive"},
                "output_config": {"effort": effort}}
    return {}


class Brain(ABC):
    @abstractmethod
    def reply(self, user_text: str, umore: str = "") -> str:
        """Genera la risposta di Emilio. `umore` è un suggerimento sullo stato
        d'animo rilevato dall'utente (es. 'arrabbiato' se ti ha provocato)."""

    def reply_stream(self, user_text: str, umore: str = "") -> Iterator[str]:
        """Genera la risposta a PEZZI (per parlare frase per frase mentre l'LLM
        scrive). Default: un blocco unico (i backend che sanno fare streaming
        ridefiniscono questo metodo)."""
        yield self.reply(user_text, umore)

    @abstractmethod
    def revise(self, motivo: str = "") -> str:
        """Richiede di riformulare l'ultima risposta (es. perché conteneva
        turpiloquio). Usato dal supervisore per la rigenerazione."""

    def reset(self) -> None:
        """Azzera la memoria di conversazione."""


class MockBrain(Brain):
    """Cervello finto, deterministico, senza rete.

    Pesca da un repertorio di battute "in carattere". Se viene PROVOCATO
    (insulti o contraddizioni nell'input) — oppure con `naughty=True` — risponde
    in modo acido e sboccato: serve per collaudare la reattività e il bip.
    Prefigge un tag di stato d'animo come farebbe l'LLM vero ([arrabbiato], ...).
    """

    CLEAN = [
        "[neutro] Eh, ai miei tempi sì che si stava bene, mica come adesso.",
        "[neutro] Ma guarda te se uno deve sentire certe cose... vabbè, dimmi pure.",
        "[felice] Insomma, io la penso così e non mi smuove nessuno.",
        "[pensa] Senti, lascia perdere, te lo dico io come funziona.",
        "[neutro] Ma certo, figurati, c'ho passato una vita su queste cose.",
    ]
    ARRABBIATO = [
        "[arrabbiato] Ma chi, porco dio, te credi de essere, dio can, par vegnir qua a rompere?!",
        "[arrabbiato] Senti, madonna ladra, mi sa che, dio boia, te vol proprio andar in mona!",
        "[arrabbiato] Ma cossa, ostia, te se messo in testa, dio porco, brutto coglione che no te xe altro?!",
        "[arrabbiato] Adesso, porca madonna, basta, dio can, che te spacco i bulloni, va' in mona!",
        "[arrabbiato] Sta' attento, dio can, che te dae tante sberle con tutte due le mani finché diventano dispari!",
    ]

    # Marcatori (sottostringa) che indicano insulto o contraddizione nell'input.
    _PROVOCAZIONI = (
        "vaffan", "stronz", "cazz", "merd", "scem", "cretin", "idiot", "imbecill",
        "deficien", "stupid", "coglion", "fai schifo", "ti odio", "sei brutto",
        "ti sbagli", "hai torto", "non è vero", "non e vero", "non sono d'accordo",
        "ma stai zitto", "sei un", "non capisci", "non vali",
    )

    def __init__(self, persona: Persona | None = None, naughty: bool = False, seed: int | None = None):
        self.persona = persona or Persona()
        self.naughty = naughty
        self._rng = random.Random(seed)
        self._last_user = ""

    def _provocato(self, testo: str) -> bool:
        t = testo.lower()
        return any(m in t for m in self._PROVOCAZIONI)

    def reply(self, user_text: str, umore: str = "") -> str:
        self._last_user = user_text
        arrabbiato = self.naughty or umore == "arrabbiato" or self._provocato(user_text)
        pool = self.ARRABBIATO if arrabbiato else self.CLEAN
        return self._rng.choice(pool)

    def revise(self, motivo: str = "") -> str:
        # alla riformulazione torna sempre pulito
        return self._rng.choice(self.CLEAN)

    def reset(self) -> None:
        self._last_user = ""


class ClaudeBrain(Brain):
    """Base LLM reale tramite l'API di Claude (Anthropic).

    Richiede il pacchetto `anthropic` e la variabile ANTHROPIC_API_KEY.
    """

    def __init__(
        self,
        persona: Persona | None = None,
        model: str = "claude-opus-4-8",
        max_tokens: int = 800,
        effort: str = "medium",
        think: str = "",
    ):
        try:
            import anthropic  # import pigro: serve solo se usi l'LLM vero
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "Pacchetto 'anthropic' non installato. Esegui: pip install anthropic"
            ) from e

        self.persona = persona or Persona()
        self.model = model
        self.max_tokens = max_tokens
        self.effort = effort
        # think: "" / "off" -> niente ragionamento (TTFT più basso, e indispensabile
        # con Haiku dove 'effort' darebbe 400); "adaptive" -> ragionamento + effort
        # (più qualità su Opus/Sonnet, ma latenza maggiore). Per la voce: off.
        self.think = (think or "").lower()
        self._client = anthropic.Anthropic()
        self._system = self.persona.system_prompt()
        self._messages: list[dict] = []

    def _extra_kwargs(self) -> dict:
        return _claude_extra_kwargs(self.think, self.effort)

    def _generate(self) -> str:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self._system,
            messages=self._messages,
            **self._extra_kwargs(),
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        self._messages.append({"role": "assistant", "content": text})
        return text

    def reply(self, user_text: str, umore: str = "") -> str:
        self._messages.append({"role": "user", "content": _con_umore(user_text, umore)})
        return self._generate()

    def reply_stream(self, user_text: str, umore: str = "") -> Iterator[str]:
        self._messages.append({"role": "user", "content": _con_umore(user_text, umore)})
        with self._client.messages.stream(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self._system,
            messages=self._messages,
            **self._extra_kwargs(),
        ) as stream:
            pezzi: list[str] = []
            for delta in stream.text_stream:
                if delta:
                    pezzi.append(delta)
                    yield delta
        self._messages.append({"role": "assistant", "content": "".join(pezzi)})

    def revise(self, motivo: str = "") -> str:
        # Toglie l'ultima risposta "sporca" e chiede di riformulare.
        # Usa un messaggio di sistema a metà conversazione (supportato da
        # Claude Opus 4.8): istruzione operativa che non rompe la cache.
        if self._messages and self._messages[-1]["role"] == "assistant":
            self._messages.pop()
        istruzione = (
            "Riformula la tua ultima risposta mantenendo senso e carattere, ma "
            "SENZA parolacce, volgarità o bestemmie. Se eri irritato, usa moccoli "
            "innocui come 'santo cielo' o 'mannaggia'."
        )
        if motivo:
            istruzione += f" (Problema rilevato: {motivo}.)"
        self._messages.append({"role": "system", "content": istruzione})
        return self._generate()

    def reset(self) -> None:
        self._messages = []


class LocalBrain(Brain):
    """LLM locale via Ollama (gira sul Mac, offline, senza chiavi cloud).

    Usa l'API nativa di Ollama (`/api/chat`) perché permette di DISATTIVARE il
    "thinking" dei modelli (es. Gemma 4): col thinking acceso la latenza esplode
    (centinaia di token di ragionamento prima della risposta — ~30s). Con
    `think=False` le risposte restano brevi e rapide, adatte al dialogo dal vivo.
    Stessa interfaccia degli altri cervelli: si seleziona da config.
    """

    def __init__(
        self,
        persona: Persona | None = None,
        base_url: str = "http://localhost:11434",
        model: str = "gemma4:12b",
        max_tokens: int = 800,
        think: bool = False,
        api_key: str = "",
        keep_alive: str = "30m",
        temperature: float = 0.85,
        repeat_penalty: float = 1.3,
    ):
        self.persona = persona or Persona()
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.think = think
        self.api_key = api_key
        self.keep_alive = keep_alive
        self.temperature = temperature
        self.repeat_penalty = repeat_penalty
        self._system = self.persona.system_prompt()
        self._messages: list[dict] = []

    def _options(self) -> dict:
        # repeat_penalty + repeat_last_n: scoraggiano i modelli piccoli dal
        # ripetere lo stesso moccolo; temperature alza la varietà.
        return {
            "num_predict": self.max_tokens,
            "temperature": self.temperature,
            "repeat_penalty": self.repeat_penalty,
            "repeat_last_n": 256,
        }

    def _errore_connessione(self) -> str:
        return (f"Ollama non risponde su {self.base_url}. "
                f"Avvialo con:  ollama serve")

    def _errore_modello(self) -> str:
        return (f"Modello locale '{self.model}' non disponibile su Ollama. "
                f"Scaricalo con:  ollama pull {self.model}")

    def _chat(self) -> str:
        import requests  # import pigro: serve solo col cervello locale

        msgs = [{"role": "system", "content": self._system}] + self._messages
        payload = {
            "model": self.model,
            "messages": msgs,
            "stream": False,
            "think": self.think,                         # False = niente ragionamento lento
            "keep_alive": self.keep_alive,               # tiene il modello caldo in RAM
            "options": self._options(),
        }
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        try:
            resp = requests.post(self.base_url + "/api/chat",
                                 headers=headers, json=payload, timeout=120)
        except requests.exceptions.ConnectionError:
            raise RuntimeError(self._errore_connessione()) from None
        if resp.status_code == 404:
            raise RuntimeError(self._errore_modello())
        resp.raise_for_status()
        text = resp.json()["message"]["content"].strip()
        self._messages.append({"role": "assistant", "content": text})
        return text

    def reply(self, user_text: str, umore: str = "") -> str:
        self._messages.append({"role": "user", "content": _con_umore(user_text, umore)})
        return self._chat()

    def reply_stream(self, user_text: str, umore: str = "") -> Iterator[str]:
        import json
        import requests  # import pigro: serve solo col cervello locale

        self._messages.append({"role": "user", "content": _con_umore(user_text, umore)})
        msgs = [{"role": "system", "content": self._system}] + self._messages
        payload = {
            "model": self.model,
            "messages": msgs,
            "stream": True,
            "think": self.think,
            "keep_alive": self.keep_alive,
            "options": self._options(),
        }
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        pezzi: list[str] = []
        try:
            resp = requests.post(self.base_url + "/api/chat", headers=headers,
                                 json=payload, stream=True, timeout=120)
        except requests.exceptions.ConnectionError:
            raise RuntimeError(self._errore_connessione()) from None
        with resp:
            if resp.status_code == 404:
                raise RuntimeError(self._errore_modello())
            resp.raise_for_status()
            for riga in resp.iter_lines():
                if not riga:
                    continue
                obj = json.loads(riga)
                pezzo = (obj.get("message") or {}).get("content", "")
                if pezzo:
                    pezzi.append(pezzo)
                    yield pezzo
                if obj.get("done"):
                    break
        self._messages.append({"role": "assistant", "content": "".join(pezzi)})

    def revise(self, motivo: str = "") -> str:
        # Non più usato dalla pipeline (la censura ora è il BIP sull'audio), ma
        # l'interfaccia resta coerente con gli altri cervelli.
        if self._messages and self._messages[-1]["role"] == "assistant":
            self._messages.pop()
        istruzione = "Riformula la tua ultima risposta senza parolacce né bestemmie."
        if motivo:
            istruzione += f" (Problema: {motivo}.)"
        self._messages.append({"role": "user", "content": istruzione})
        return self._chat()

    def reset(self) -> None:
        self._messages = []


class CloudBrain(Brain):
    """LLM cloud generico via API **OpenAI-compatibile** (`/v1/chat/completions`).

    Copre i provider che parlano il protocollo OpenAI: **Groq** (latenza minima
    con modelli open), OpenRouter, OpenAI, vLLM... La leva principale per la
    latenza è il provider + un modello piccolo/rapido (es. `llama-3.1-8b-instant`
    su Groq). Stessa interfaccia degli altri cervelli (mock/claude/local), con
    streaming vero (SSE `data:`), così la voce parte frase per frase.
    """

    def __init__(
        self,
        persona: Persona | None = None,
        base_url: str = "https://api.groq.com/openai/v1",
        model: str = "llama-3.3-70b-versatile",
        max_tokens: int = 800,
        api_key: str = "",
        temperature: float = 0.85,
    ):
        self.persona = persona or Persona()
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.api_key = api_key
        self.temperature = temperature
        self._system = self.persona.system_prompt()
        self._messages: list[dict] = []

    def _payload(self, stream: bool) -> dict:
        return {
            "model": self.model,
            "messages": [{"role": "system", "content": self._system}] + self._messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": stream,
        }

    def _headers(self) -> dict:
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        return headers

    def _errore_connessione(self) -> str:
        return (f"Provider cloud non raggiungibile su {self.base_url}. "
                f"Controlla EMILIO_CLOUD_URL e la rete.")

    def _controlla(self, resp) -> None:
        import requests  # import pigro: serve solo col cervello cloud
        if resp.status_code in (401, 403):
            raise RuntimeError("Chiave API cloud mancante o non valida "
                               "(imposta EMILIO_CLOUD_KEY).")
        if resp.status_code == 404:
            raise RuntimeError(f"Modello cloud '{self.model}' non trovato sul provider.")
        try:
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise RuntimeError(f"Errore dal provider cloud: {e}") from None

    def reply(self, user_text: str, umore: str = "") -> str:
        import requests  # import pigro: serve solo col cervello cloud

        self._messages.append({"role": "user", "content": _con_umore(user_text, umore)})
        try:
            resp = requests.post(self.base_url + "/chat/completions",
                                 headers=self._headers(),
                                 json=self._payload(stream=False), timeout=120)
        except requests.exceptions.ConnectionError:
            raise RuntimeError(self._errore_connessione()) from None
        self._controlla(resp)
        text = resp.json()["choices"][0]["message"]["content"].strip()
        self._messages.append({"role": "assistant", "content": text})
        return text

    def reply_stream(self, user_text: str, umore: str = "") -> Iterator[str]:
        import json
        import requests  # import pigro: serve solo col cervello cloud

        self._messages.append({"role": "user", "content": _con_umore(user_text, umore)})
        try:
            resp = requests.post(self.base_url + "/chat/completions",
                                 headers=self._headers(),
                                 json=self._payload(stream=True), stream=True, timeout=120)
        except requests.exceptions.ConnectionError:
            raise RuntimeError(self._errore_connessione()) from None
        pezzi: list[str] = []
        with resp:
            self._controlla(resp)
            for riga in resp.iter_lines():
                if not riga:
                    continue
                linea = riga.decode("utf-8") if isinstance(riga, bytes) else riga
                if not linea.startswith("data:"):
                    continue
                dato = linea[len("data:"):].strip()
                if dato == "[DONE]":
                    break
                try:
                    obj = json.loads(dato)
                except json.JSONDecodeError:
                    continue
                delta = (obj.get("choices") or [{}])[0].get("delta") or {}
                pezzo = delta.get("content") or ""
                if pezzo:
                    pezzi.append(pezzo)
                    yield pezzo
        self._messages.append({"role": "assistant", "content": "".join(pezzi)})

    def revise(self, motivo: str = "") -> str:
        if self._messages and self._messages[-1]["role"] == "assistant":
            self._messages.pop()
        istruzione = "Riformula la tua ultima risposta senza parolacce né bestemmie."
        if motivo:
            istruzione += f" (Problema: {motivo}.)"
        self._messages.append({"role": "user", "content": istruzione})
        return self.reply(istruzione)

    def reset(self) -> None:
        self._messages = []


def build_brain(config, persona: Persona) -> Brain:
    """Factory: sceglie il cervello in base alla configurazione.

    `EMILIO_LLM` = mock | claude | local | cloud. Per retrocompatibilità, se non
    impostato, `EMILIO_USE_LLM=1` equivale a `claude`, altrimenti `mock`.
    """
    backend = (getattr(config, "llm_backend", "") or
               ("claude" if config.use_real_llm else "mock")).lower()
    if backend == "local":
        return LocalBrain(
            persona=persona,
            base_url=config.local_llm_url,
            model=config.local_llm_model,
            max_tokens=config.max_tokens,
            think=config.local_llm_think,
            api_key=config.local_llm_key,
            keep_alive=getattr(config, "local_llm_keep_alive", "30m"),
            temperature=getattr(config, "local_llm_temp", 0.85),
            repeat_penalty=getattr(config, "local_llm_repeat_penalty", 1.3),
        )
    if backend == "cloud":
        return CloudBrain(
            persona=persona,
            base_url=getattr(config, "cloud_llm_url", "https://api.groq.com/openai/v1"),
            model=getattr(config, "cloud_llm_model", "llama-3.3-70b-versatile"),
            max_tokens=config.max_tokens,
            api_key=getattr(config, "cloud_llm_key", ""),
            temperature=getattr(config, "cloud_llm_temp", 0.85),
        )
    if backend == "claude":
        return ClaudeBrain(
            persona=persona,
            model=config.claude_model,
            max_tokens=config.max_tokens,
            effort=config.effort,
            think=getattr(config, "claude_think", ""),
        )
    return MockBrain(persona=persona)
