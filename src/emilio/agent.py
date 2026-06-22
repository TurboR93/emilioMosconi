"""Emilio: orchestrazione di cervello + supervisore + voce + movimento.

Pipeline del parlato (il supervisore è un passaggio OBBLIGATO):

    input utente
        │
        ▼
    [Cervello LLM]  ──► testo grezzo
        │
        ▼
    [Supervisore]   ──► (se bestemmia) chiede riformulazione all'LLM,
        │                poi comunque ripulisce il testo
        ▼
    [Voce TTS]      ──► Emilio parla (+ muove la bocca)

La censura è controllabile dall'amministratore: `agent.set_moderazione(False)`
la disattiva al volo, senza alterare il resto del flusso.
"""

from __future__ import annotations

from dataclasses import dataclass

import time

from .actuators import Mover, build_mover
from .brain import Brain, build_brain
from .config import EmilioConfig
from .moderation import Moderator, Report
from .persona import Persona
from .speech import SpeechMetrics, VoiceManager, VoiceProfile, build_voice_manager


@dataclass
class RisultatoParlato:
    input_utente: str
    testo_grezzo: str        # ciò che ha prodotto l'LLM
    testo_detto: str         # ciò che Emilio dice davvero (post-supervisore)
    report: Report           # esito dell'analisi del supervisore
    span_censura: list[tuple[int, int]]  # intervalli (caratteri) coperti dal bip
    censura_applicata: bool
    latenza_llm: float = 0.0           # secondi per generare la risposta
    voce: SpeechMetrics | None = None  # metriche di latenza della voce


class EmilioAgent:
    def __init__(
        self,
        config: EmilioConfig | None = None,
        *,
        persona: Persona | None = None,
        brain: Brain | None = None,
        moderator: Moderator | None = None,
        voci: VoiceManager | None = None,
        mover: Mover | None = None,
    ):
        self.config = config or EmilioConfig()
        self.persona = persona or Persona.load(self.config.persona_path)
        self.brain = brain or build_brain(self.config, self.persona)
        self.moderator = moderator or Moderator(
            censor_style=self.config.censor_style,
            enabled=self.config.moderation_enabled,
            bip_marker=self.config.bip_marker,
        )
        self.voci = voci or build_voice_manager(self.config)
        self.mover = mover or build_mover(self.config)

    # -- controllo amministratore sulla censura ---------------------------

    def set_moderazione(self, attiva: bool) -> None:
        """Attiva/disattiva la censura a runtime (controllo amministratore)."""
        self.moderator.enabled = attiva

    @property
    def moderazione_attiva(self) -> bool:
        return self.moderator.enabled

    # -- controllo voci ----------------------------------------------------

    def lista_voci(self) -> list[VoiceProfile]:
        return self.voci.lista()

    def set_voce(self, nome: str) -> VoiceProfile:
        """Cambia la voce attiva a runtime."""
        return self.voci.imposta(nome)

    @property
    def voce_attiva(self) -> str:
        return self.voci.attiva

    # -- parlato -----------------------------------------------------------

    def genera(self, input_utente: str) -> RisultatoParlato:
        """Esegue tutta la pipeline ma SENZA pronunciare (utile per test/log).

        Il cervello NON riformula: si analizza il testo grezzo e si calcolano
        gli span da coprire col BIP sull'audio (vedi `di`/`parla`).
        """
        t0 = time.perf_counter()
        testo_grezzo = self.brain.reply(input_utente)
        latenza_llm = time.perf_counter() - t0

        report = self.moderator.review(testo_grezzo)
        span = self.moderator.span_censura(report)        # vuoto se censura OFF
        censura = bool(span)
        testo_detto = self.moderator.testo_con_bip(testo_grezzo, report)

        return RisultatoParlato(
            input_utente=input_utente,
            testo_grezzo=testo_grezzo,
            testo_detto=testo_detto,
            report=report,
            span_censura=span,
            censura_applicata=censura,
            latenza_llm=latenza_llm,
        )

    def parla(self, input_utente: str) -> RisultatoParlato:
        """Pipeline completa: genera e fa parlare Emilio (col bip dove serve)."""
        ris = self.genera(input_utente)
        # Si pronuncia il testo GREZZO: la voce sintetizza la frase naturale e
        # copre con un bip solo gli intervalli sporchi (span_censura).
        ris.voce = self._pronuncia(ris.testo_grezzo, ris.span_censura)
        return ris

    def di(self, testo: str) -> SpeechMetrics:
        """Pronuncia un testo arbitrario, bippando le parti sporche sull'audio.

        Restituisce le metriche di latenza della voce.
        """
        report = self.moderator.review(testo)
        span = self.moderator.span_censura(report)   # vuoto se censura OFF
        return self._pronuncia(testo, span)

    def _pronuncia(self, testo: str, span: list[tuple[int, int]]) -> SpeechMetrics:
        try:
            self.mover.move("bocca")          # muove la bocca mentre parla
        except Exception:
            pass
        return self.voci.say(testo, bleep_spans=span)

    # -- movimento manuale -------------------------------------------------

    def muovi(self, azione: str, valore: float = 1.0) -> None:
        self.mover.move(azione, valore)

    def reset(self) -> None:
        self.brain.reset()
