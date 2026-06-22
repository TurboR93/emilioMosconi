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
from .moderation import Moderator, Report, contiene_provocazione
from .occhi import ESPRESSIONI, Occhi, build_occhi
from .persona import Persona
from .speech import SpeechMetrics, VoiceManager, VoiceProfile, build_voice_manager

# Tag di stato d'animo a inizio risposta dell'LLM, es. "[arrabbiato] ...".
# Tollerante: virgolette/asterischi attorno, spazi interni, punteggiatura.
_TAG_EMOZIONE = re.compile(r"""^\s*["'*]*\[\s*([^\]]{1,30}?)\s*\]["'*]*\s*""")
# Emozioni che l'LLM può dichiarare (le altre voci di ESPRESSIONI sono "di stato").
_EMOZIONI_LLM = {"neutro", "felice", "arrabbiato", "sorpreso", "triste", "pensa"}


_TERMINATORI = ".!?…"
_CHIUSURE = "\"'»)]"


def _spezza_frasi(buf: str) -> tuple[list[str], str]:
    """Estrae le frasi COMPLETE da `buf`, lasciando il resto in sospeso.

    Una frase è completa quando un terminatore (. ! ? …) è seguito da spazio o
    da fine stringa CON ancora testo dopo: finché il terminatore è in coda al
    buffer non si sa se la frase è finita (potrebbe arrivare altro nel prossimo
    pezzo dello stream), quindi resta in sospeso. Ritorna (frasi, resto).
    """
    frasi: list[str] = []
    inizio = 0
    i = 0
    n = len(buf)
    while i < n:
        if buf[i] in _TERMINATORI:
            k = i + 1
            while k < n and buf[k] in _TERMINATORI:    # gruppo di terminatori
                k += 1
            term = buf[i:k]
            # "..." (puntini di sospensione) = pausa, NON fine frase: tira dritto
            if set(term) == {"."} and len(term) >= 2:
                i = k
                continue
            j = k
            while j < n and buf[j] in _CHIUSURE:        # virgolette/parentesi finali
                j += 1
            if j >= n:        # terminatore in coda: aspetta il prossimo pezzo
                break
            if buf[j].isspace():
                frase = buf[inizio:j].strip()
                if frase:
                    frasi.append(frase)
                inizio = j
            i = j
            continue
        i += 1
    return frasi, buf[inizio:]


def _fondi_metriche(ms: list) -> "SpeechMetrics | None":
    """Unisce le metriche delle singole frasi in una sola (per il riepilogo)."""
    ms = [m for m in ms if m]
    if not ms:
        return None
    ttfb = next((m.ttfb for m in ms if m.ttfb is not None), None)
    return SpeechMetrics(ms[0].backend, ms[0].profilo, ttfb,
                         sum(m.totale for m in ms), sum(m.caratteri for m in ms))


def _estrai_emozione(testo: str) -> tuple[str | None, str]:
    """Stacca un tag '[emozione]' iniziale SOLO se è un'emozione nota.

    Tollera '[molto arrabbiato]', '[arrabbiato!]', '"[arrabbiato]"' ecc. Se fra
    le parentesi non c'è un'emozione valida (es. '[Bologna]', '[ndr]'), lascia
    il testo INTATTO: meglio non mangiare contenuto legittimo.
    """
    m = _TAG_EMOZIONE.match(testo)
    if not m:
        return None, testo
    parole = re.findall(r"[a-zàèéìòù]+", m.group(1).lower())
    emo = parole[-1] if parole else ""
    if emo in _EMOZIONI_LLM:
        return emo, testo[m.end():]
    return None, testo


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
            solo_bestemmie=getattr(self.config, "censura_solo_bestemmie", True),
        )
        self.voci = voci or build_voice_manager(self.config)
        self.mover = mover or build_mover(self.config)
        self.occhi = occhi or build_occhi(self.config)
        self.ascolto = ascolto or build_ascoltatore(self.config)
        # Pipeline del parlato: streaming (parla frase per frase) o a blocco
        # unico (vecchia). Scelta all'avvio (EMILIO_STREAMING) e da runtime.
        self.streaming = getattr(self.config, "streaming", True)
        # Scalda lo STT in sottofondo: così la prima trascrizione non paga il
        # caricamento del modello (solo coi backend reali, mai nei test/mock).
        if getattr(self.config, "stt_backend", "mock").lower() in ("whisper", "reale", "mlx"):
            import threading
            threading.Thread(target=self._prewarm_ascolto, daemon=True).start()

    def _prewarm_ascolto(self) -> None:
        try:
            self.ascolto.prewarm()
        except Exception:
            pass

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
        # Rileva la provocazione PRIMA di generare: serve a ri-infuriare l'LLM
        # (che altrimenti si calma ai turni dopo) e a guidare gli occhi.
        provocato = self._provocato_input(input_utente)
        t0 = time.perf_counter()
        grezzo_raw = self.brain.reply(input_utente, umore="arrabbiato" if provocato else "")
        latenza_llm = time.perf_counter() - t0

        # Stacca il tag di stato d'animo dichiarato dall'LLM (non va pronunciato).
        tag, testo_grezzo = _estrai_emozione(grezzo_raw)

        report = self.moderator.review(testo_grezzo)
        span = self.moderator.span_censura(report)        # vuoto se censura OFF
        censura = bool(span)
        testo_detto = self.moderator.testo_con_bip(testo_grezzo, report)
        emozione = self._emozione(report, tag, provocato)

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

    def _provocato_input(self, input_utente: str) -> bool:
        """True se l'utente lo ha insultato/contraddetto (anche senza parolacce)."""
        if not self.config.moderate_input:
            return False
        return contiene_provocazione(input_utente)

    def _emozione(self, report: Report, tag: str | None, provocato: bool) -> str:
        """Stato d'animo: arrabbiato se provocato, o se la risposta contiene
        turpiloquio, o se l'LLM lo dichiara; altrimenti il tag valido o 'neutro'."""
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

    def rispondi(self, input_utente: str) -> RisultatoParlato:
        """Parla scegliendo la pipeline attiva: streaming o a blocco unico."""
        if self.streaming:
            return self.parla_streaming(input_utente)
        return self.parla(input_utente)

    def set_streaming(self, attivo: bool) -> None:
        """Attiva/disattiva la pipeline streaming a runtime (admin)."""
        self.streaming = attivo

    def parla_streaming(self, input_utente: str) -> RisultatoParlato:
        """Come `parla`, ma pronuncia FRASE PER FRASE mentre l'LLM genera: la
        prima battuta parte appena pronta, senza aspettare tutta la risposta.

        Ogni frase passa dal supervisore singolarmente (stessa censura via BIP).
        Il tag di stato d'animo iniziale viene staccato prima di parlare.
        """
        try:
            self.occhi.imposta("pensa")
        except Exception:
            pass
        provocato = self._provocato_input(input_utente)
        umore = "arrabbiato" if provocato else ""

        buffer = ""
        tag: str | None = None
        tag_risolto = False
        arrabbiato = provocato
        frasi_grezze: list[str] = []
        frasi_dette: list[str] = []
        span_tot: list[tuple[int, int]] = []
        metriche: list[SpeechMetrics] = []
        t0 = time.perf_counter()
        ttft: float | None = None

        prima_fatta = False

        def _parla_frase(frase: str) -> None:
            nonlocal arrabbiato
            frase = frase.strip()
            if not frase:
                return
            report = self.moderator.review(frase)
            span = self.moderator.span_censura(report)
            if report.has_profanity or report.has_blasphemy:
                arrabbiato = True
            try:
                self.occhi.imposta("arrabbiato" if arrabbiato else "parla")
            except Exception:
                pass
            try:
                self.mover.move("bocca")
            except Exception:
                pass
            # Passa al TTS ciò che ha GIÀ detto: così la voce continua l'intonazione
            # invece di "ripartire" a ogni frase (niente salti di tono).
            prev = " ".join(frasi_grezze)
            metriche.append(self.voci.say(frase, bleep_spans=span, previous_text=prev))
            frasi_grezze.append(frase)
            frasi_dette.append(self.moderator.testo_con_bip(frase, report))
            span_tot.extend(span)

        for pezzo in self.brain.reply_stream(input_utente, umore=umore):
            if ttft is None:
                ttft = time.perf_counter() - t0
            buffer += pezzo
            if not tag_risolto:
                # stacca il tag [emozione] appena c'è abbastanza testo per deciderlo
                if ("]" in buffer or len(buffer) >= 48
                        or (buffer.strip() and buffer.lstrip()[0] != "[")):
                    tag, buffer = _estrai_emozione(buffer)
                    tag_risolto = True
                    if tag == "arrabbiato":
                        arrabbiato = True
                else:
                    continue
            # Parla SUBITO la prima frase (TTFT basso); il resto si accumula e si
            # dice in un BLOCCO UNICO a fine generazione (meno frammentazione,
            # tono più coerente). Per le risposte di 1 frase coincide col blocco.
            if not prima_fatta:
                frasi, buffer = _spezza_frasi(buffer)
                if frasi:
                    _parla_frase(frasi[0])
                    prima_fatta = True
                    resto = " ".join(frasi[1:])     # eventuali frasi già pronte
                    buffer = (resto + " " + buffer) if resto else buffer

        if not tag_risolto:                       # risposta cortissima senza tag chiuso
            tag, buffer = _estrai_emozione(buffer)
        if buffer.strip():                         # tutto il resto, in un blocco unico
            _parla_frase(buffer)

        testo_grezzo = " ".join(frasi_grezze).strip()
        testo_detto = " ".join(frasi_dette).strip()
        report = self.moderator.review(testo_grezzo)
        emozione = self._emozione(report, tag, provocato)
        riposo = emozione if emozione in ESPRESSIONI and emozione not in (
            "parla", "pensa", "ascolta", "spento") else "neutro"
        try:
            self.occhi.imposta(riposo)
        except Exception:
            pass

        return RisultatoParlato(
            input_utente=input_utente,
            testo_grezzo=testo_grezzo,
            testo_detto=testo_detto,
            report=report,
            span_censura=self.moderator.span_censura(report),
            censura_applicata=bool(span_tot),
            emozione=emozione,
            latenza_llm=ttft or 0.0,        # tempo al PRIMO token (responsività)
            voce=_fondi_metriche(metriche),
        )

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
        # A fine battuta lascia l'espressione dichiarata se è "stabile"
        # (neutro/felice/arrabbiato/sorpreso/triste); pensa/parla/ascolta -> neutro.
        riposo = emozione if emozione in ESPRESSIONI and emozione not in (
            "parla", "pensa", "ascolta", "spento") else "neutro"
        try:
            self.occhi.imposta(riposo)
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
