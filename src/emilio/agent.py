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

import re
import time

from .actuators import Mover, build_mover
from .ascolto import Ascoltatore, build_ascoltatore
from .brain import Brain, build_brain
from .config import EmilioConfig
from .moderation import Moderator, Report
from .occhi import ESPRESSIONI, Occhi, build_occhi
from .persona import Persona
from .speech import SpeechMetrics, VoiceManager, VoiceProfile, build_voice_manager

# Tag di stato d'animo a inizio risposta dell'LLM, es. "[arrabbiato] ...".
_TAG_EMOZIONE = re.compile(r"^\s*\[([a-zàèéìòùA-Z]+)\]\s*")
# Emozioni che l'LLM può dichiarare (le altre voci di ESPRESSIONI sono "di stato").
_EMOZIONI_LLM = {"neutro", "felice", "arrabbiato", "sorpreso", "triste", "pensa"}


def _estrai_emozione(testo: str) -> tuple[str | None, str]:
    """Stacca un eventuale tag '[emozione]' iniziale. Ritorna (tag|None, testo)."""
    m = _TAG_EMOZIONE.match(testo)
    if not m:
        return None, testo
    return m.group(1).lower(), testo[m.end():]


@dataclass
class RisultatoParlato:
    input_utente: str
    testo_grezzo: str        # ciò che ha prodotto l'LLM
    testo_detto: str         # ciò che Emilio dice davvero (post-supervisore)
    report: Report           # esito dell'analisi del supervisore
    span_censura: list[tuple[int, int]]  # intervalli (caratteri) coperti dal bip
    censura_applicata: bool
    emozione: str = "neutro"           # stato d'animo (guida gli occhi)
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
        occhi: Occhi | None = None,
        ascolto: Ascoltatore | None = None,
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
        self.occhi = occhi or build_occhi(self.config)
        self.ascolto = ascolto or build_ascoltatore(self.config)

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

    # -- controllo occhi ---------------------------------------------------

    def set_occhi(self, espressione: str):
        """Cambia l'espressione degli occhi a runtime."""
        return self.occhi.imposta(espressione)

    def guarda(self, direzione: str) -> None:
        self.occhi.guarda(direzione)

    # -- parlato -----------------------------------------------------------

    def genera(self, input_utente: str) -> RisultatoParlato:
        """Esegue tutta la pipeline ma SENZA pronunciare (utile per test/log).

        Il cervello NON riformula: si analizza il testo grezzo e si calcolano
        gli span da coprire col BIP sull'audio (vedi `di`/`parla`).
        """
        try:
            self.occhi.imposta("pensa")       # occhi "pensierosi" mentre genera
        except Exception:
            pass
        t0 = time.perf_counter()
        grezzo_raw = self.brain.reply(input_utente)
        latenza_llm = time.perf_counter() - t0

        # Stacca il tag di stato d'animo dichiarato dall'LLM (non va pronunciato).
        tag, testo_grezzo = _estrai_emozione(grezzo_raw)

        report = self.moderator.review(testo_grezzo)
        span = self.moderator.span_censura(report)        # vuoto se censura OFF
        censura = bool(span)
        testo_detto = self.moderator.testo_con_bip(testo_grezzo, report)
        emozione = self._emozione(input_utente, report, tag)

        return RisultatoParlato(
            input_utente=input_utente,
            testo_grezzo=testo_grezzo,
            testo_detto=testo_detto,
            report=report,
            span_censura=span,
            censura_applicata=censura,
            emozione=emozione,
            latenza_llm=latenza_llm,
        )

    def _emozione(self, input_utente: str, report: Report, tag: str | None) -> str:
        """Determina lo stato d'animo: arrabbiato se è stato provocato (insulto
        nell'input) o se la sua risposta contiene turpiloquio, o se l'LLM lo
        dichiara; altrimenti il tag dichiarato (se valido), o 'neutro'."""
        provocato = False
        if self.config.moderate_input:
            r_in = self.moderator.review(input_utente)
            provocato = r_in.has_profanity or r_in.has_blasphemy
        if (provocato or report.has_profanity or report.has_blasphemy
                or tag == "arrabbiato"):
            return "arrabbiato"
        if tag in _EMOZIONI_LLM and tag in ESPRESSIONI:
            return tag
        return "neutro"

    def parla(self, input_utente: str) -> RisultatoParlato:
        """Pipeline completa: genera e fa parlare Emilio (col bip dove serve)."""
        ris = self.genera(input_utente)
        # Si pronuncia il testo GREZZO: la voce sintetizza la frase naturale e
        # copre con un bip solo gli intervalli sporchi (span_censura).
        ris.voce = self._pronuncia(ris.testo_grezzo, ris.span_censura, ris.emozione)
        return ris

    def di(self, testo: str) -> SpeechMetrics:
        """Pronuncia un testo arbitrario, bippando le parti sporche sull'audio.

        Restituisce le metriche di latenza della voce.
        """
        report = self.moderator.review(testo)
        span = self.moderator.span_censura(report)   # vuoto se censura OFF
        emozione = "arrabbiato" if (report.has_profanity or report.has_blasphemy) else "neutro"
        return self._pronuncia(testo, span, emozione)

    def _pronuncia(self, testo: str, span: list[tuple[int, int]],
                   emozione: str = "neutro") -> SpeechMetrics:
        arrabbiato = emozione == "arrabbiato"
        try:
            self.mover.move("bocca")          # muove la bocca mentre parla
        except Exception:
            pass
        try:
            # arrabbiato -> occhi a forche del diavolo; altrimenti occhi "parla"
            # (così la bocca si anima mentre parla).
            self.occhi.imposta("arrabbiato" if arrabbiato else "parla")
        except Exception:
            pass
        metriche = self.voci.say(testo, bleep_spans=span)
        try:
            self.occhi.imposta("arrabbiato" if arrabbiato else "neutro")
        except Exception:
            pass
        return metriche

    # -- ascolto (voce -> testo) -------------------------------------------

    def ascolta(self, secondi: float | None = None) -> str:
        """Ascolta dal microfono e ritorna ciò che ha capito (STT)."""
        try:
            self.occhi.imposta("ascolta")     # occhi "attenti" mentre ascolta
        except Exception:
            pass
        testo = self.ascolto.ascolta(secondi if secondi is not None else self.config.stt_secondi)
        try:
            self.occhi.imposta("neutro")
        except Exception:
            pass
        return testo

    # -- movimento manuale -------------------------------------------------

    def muovi(self, azione: str, valore: float = 1.0) -> None:
        self.mover.move(azione, valore)

    def reset(self) -> None:
        self.brain.reset()
