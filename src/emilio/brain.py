"""Cervello di Emilio: genera le risposte (la "base LLM").

Due implementazioni dietro la stessa interfaccia:
  * MockBrain  -> funziona offline, senza chiavi: utile per provare la pipeline
                  e i test (può anche restituire frasi "sporche" per verificare
                  il supervisore).
  * ClaudeBrain -> usa l'API di Claude (Anthropic). È la base LLM vera.

Il supervisore di censura NON sta qui: il cervello genera, il supervisore
controlla a valle (vedi agent.py). Così la base LLM e la supervisione restano
componenti separati e sostituibili.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod

from .persona import Persona


class Brain(ABC):
    @abstractmethod
    def reply(self, user_text: str) -> str:
        """Genera la risposta di Emilio a un input dell'utente."""

    @abstractmethod
    def revise(self, motivo: str = "") -> str:
        """Richiede di riformulare l'ultima risposta (es. perché conteneva
        turpiloquio). Usato dal supervisore per la rigenerazione."""

    def reset(self) -> None:
        """Azzera la memoria di conversazione."""


class MockBrain(Brain):
    """Cervello finto, deterministico, senza rete.

    Pesca da un repertorio di battute "in carattere". Se `naughty=True` può
    restituire frasi con turpiloquio: serve per collaudare il supervisore.
    """

    CLEAN = [
        "Eh, ai miei tempi sì che si stava bene, mica come adesso.",
        "Ma guarda te se uno deve sentire certe cose... vabbè, dimmi pure.",
        "Insomma, io la penso così e non mi smuove nessuno.",
        "Senti, lascia perdere, te lo dico io come funziona.",
        "Ma certo, figurati, c'ho passato una vita su queste cose.",
    ]
    NAUGHTY = [
        "Porco dio che giornata, non se ne può più!",
        "Ma vaffanculo va', che roba è questa.",
        "Sei proprio uno stronzo, te lo dico in faccia.",
    ]

    def __init__(self, persona: Persona | None = None, naughty: bool = False, seed: int | None = None):
        self.persona = persona or Persona()
        self.naughty = naughty
        self._rng = random.Random(seed)
        self._last_user = ""

    def reply(self, user_text: str) -> str:
        self._last_user = user_text
        pool = self.NAUGHTY if self.naughty else self.CLEAN
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

    def reply(self, user_text: str) -> str:
        self._messages.append({"role": "user", "content": user_text})
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


def build_brain(config, persona: Persona) -> Brain:
    """Factory: sceglie il cervello in base alla configurazione."""
    if config.use_real_llm:
        return ClaudeBrain(
            persona=persona,
            model=config.model,
            max_tokens=config.max_tokens,
            effort=config.effort,
        )
    return MockBrain(persona=persona)
