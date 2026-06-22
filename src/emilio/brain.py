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


class Brain(ABC):
    @abstractmethod
    def reply(self, user_text: str, umore: str = "") -> str:
        """Genera la risposta di Emilio. `umore` è un suggerimento sullo stato
        d'animo rilevato dall'utente (es. 'arrabbiato' se ti ha provocato)."""

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
        "[arrabbiato] Porco dio, dio can, ma chi te credi de essere?! Vaffanculo va'!",
        "[arrabbiato] Madonna ladra, dio boia, ma va' in mona! Coglione, porca madonna!",
        "[arrabbiato] Dio cane, ostia santa, vaffanculo te e chi t'ha fatto, dio porco!",
        "[arrabbiato] Ma va' in mona, dio can! Stronzo, porco dio, te spacco i bulloni!",
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
        self._client = anthropic.Anthropic()
        self._system = self.persona.system_prompt()
        self._messages: list[dict] = []

    def _generate(self) -> str:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self._system,
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
            messages=self._messages,
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        self._messages.append({"role": "assistant", "content": text})
        return text

    def reply(self, user_text: str, umore: str = "") -> str:
        self._messages.append({"role": "user", "content": _con_umore(user_text, umore)})
        return self._generate()

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
    ):
        self.persona = persona or Persona()
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.think = think
        self.api_key = api_key
        self._system = self.persona.system_prompt()
        self._messages: list[dict] = []

    def _chat(self) -> str:
        import requests  # import pigro: serve solo col cervello locale

        msgs = [{"role": "system", "content": self._system}] + self._messages
        payload = {
            "model": self.model,
            "messages": msgs,
            "stream": False,
            "think": self.think,                         # False = niente ragionamento lento
            "options": {"num_predict": self.max_tokens},
        }
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        resp = requests.post(self.base_url + "/api/chat",
                             headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        text = resp.json()["message"]["content"].strip()
        self._messages.append({"role": "assistant", "content": text})
        return text

    def reply(self, user_text: str, umore: str = "") -> str:
        self._messages.append({"role": "user", "content": _con_umore(user_text, umore)})
        return self._chat()

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


def build_brain(config, persona: Persona) -> Brain:
    """Factory: sceglie il cervello in base alla configurazione.

    `EMILIO_LLM` = mock | claude | local. Per retrocompatibilità, se non
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
        )
    if backend == "claude":
        return ClaudeBrain(
            persona=persona,
            model=config.model,
            max_tokens=config.max_tokens,
            effort=config.effort,
        )
    return MockBrain(persona=persona)
