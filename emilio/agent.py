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
    rigenerazioni: int       # quante volte si è chiesto all'LLM di riformulare
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
        """Esegue tutta la pipeline ma SENZA pronunciare (utile per test/log)."""
        t0 = time.perf_counter()
        testo_grezzo = self.brain.reply(input_utente)
        latenza_llm = time.perf_counter() - t0

        rigenerazioni = 0
        testo = testo_grezzo
        report = self.moderator.review(testo)

        # Se è attiva la censura e c'è una bestemmia, prova a far riformulare
        # all'LLM (così la frase resta sensata invece di essere "bippata").
        while (
            self.moderator.enabled
            and report.has_blasphemy
            and rigenerazioni < self.config.max_regen
        ):
            testo = self.brain.revise(motivo=report.summary())
            report = self.moderator.review(testo)
            rigenerazioni += 1

        # Passaggio finale e obbligato dal supervisore.
        testo_detto, report, censura = self.moderator.process(testo)

        return RisultatoParlato(
            input_utente=input_utente,
            testo_grezzo=testo_grezzo,
            testo_detto=testo_detto,
            report=report,
            rigenerazioni=rigenerazioni,
            censura_applicata=censura,
            latenza_llm=latenza_llm,
        )

    def parla(self, input_utente: str) -> RisultatoParlato:
        """Pipeline completa: genera, supervisiona e fa parlare Emilio."""
        ris = self.genera(input_utente)
        ris.voce = self.di(ris.testo_detto)
        return ris

    def di(self, testo: str) -> SpeechMetrics:
        """Pronuncia un testo arbitrario (passando comunque dal supervisore).

        Restituisce le metriche di latenza della voce.
        """
        testo_detto, _report, _censura = self.moderator.process(testo)
        try:
            self.mover.move("bocca")          # muove la bocca mentre parla
        except Exception:
            pass
        return self.voci.say(testo_detto)

    # -- movimento manuale -------------------------------------------------

    def muovi(self, azione: str, valore: float = 1.0) -> None:
        self.mover.move(azione, valore)

    def reset(self) -> None:
        self.brain.reset()
