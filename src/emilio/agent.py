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

import os
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


# Scorciatoie per i provider cloud OpenAI-compatibili (vedi /provider).
_PROVIDER_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
}


def _nome_provider(url: str) -> str:
    """Nome breve di un provider cloud dal suo URL (per la console)."""
    for nome, u in _PROVIDER_URLS.items():
        if (url or "").rstrip("/") == u:
            return nome
    # ripiego: l'host dell'URL (senza schema)
    resto = (url or "").split("://", 1)[-1]
    return resto.split("/", 1)[0] or url


def _nome_persona(path: str | None) -> str:
    """Nome breve di una persona dal percorso del file (None -> 'default').

    Es. 'tools/persona_veterano.json' -> 'veterano'. Serve per mostrare in
    console quale personalità è attiva senza stampare un percorso intero.
    """
    if not path:
        return "default"
    base = os.path.basename(path)
    if base.endswith(".json"):
        base = base[:-5]
    if base.startswith("persona_"):
        base = base[len("persona_"):]
    return base or "default"


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
    """Stacca il tag '[...]' iniziale dello stato d'animo (non si pronuncia).

    - emozione NOTA ('[arrabbiato]', '[molto arrabbiato]', '"[Arrabbiato]"') ->
      la ritorna e la stacca;
    - tag d'animo INVENTATO dal modello, in minuscolo e di 1-3 parole
      ('[scettico]', '[brontolo bonario]') -> lo stacca comunque (emozione neutra),
      così non finisce PRONUNCIATO;
    - contenuto legittimo fra parentesi (maiuscole/cifre/punteggiatura, es.
      '[Bologna]', '[ndr]', '[3-1]') -> lascia il testo INTATTO.
    """
    m = _TAG_EMOZIONE.match(testo)
    if not m:
        return None, testo
    contenuto = m.group(1).strip()
    parole = re.findall(r"[a-zàèéìòùáíóúü]+", contenuto.lower())
    emo = parole[-1] if parole else ""
    if emo in _EMOZIONI_LLM:
        return emo, testo[m.end():]
    # tag d'animo inventato: solo lettere minuscole/spazi, al massimo 3 parole
    if parole and len(parole) <= 3 and re.fullmatch(r"[a-zàèéìòùáíóúü ]+", contenuto):
        return None, testo[m.end():]
    return None, testo          # sembra contenuto vero ([Bologna], [3-1]): non toccare


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
        # Etichetta breve della personalità attiva (per la console): 'default'
        # oppure il nome del file caricato via EMILIO_PERSONA / comando /persona.
        self.persona_origine = (
            "personalizzata" if persona is not None
            else _nome_persona(self.config.persona_path))
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
        # Modalità monitor della console: se True il terminale mostra, in tempo
        # reale, il testo che Emilio sta per dire (vedi CLI /verboso). ON di
        # default (EMILIO_VERBOSO). Flag di presentazione: la usa la console,
        # non il nucleo.
        self.verboso = getattr(self.config, "verboso", True)
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

    # -- controllo cervello (backend e modello) ---------------------------

    @property
    def backend_cervello(self) -> str:
        """Backend LLM attuale: 'mock', 'local' (Ollama), 'claude' o 'cloud'."""
        return (self.config.llm_backend
                or ("claude" if self.config.use_real_llm else "mock")).lower()

    def descrizione_cervello(self) -> str:
        """Etichetta leggibile del cervello attivo, col modello fra parentesi."""
        b = self.backend_cervello
        if b == "local":
            return f"local ({self.config.local_llm_model})"
        if b == "claude":
            return f"claude ({self.config.model})"
        if b == "cloud":
            return f"cloud ({self.config.cloud_llm_model})"
        return b

    def set_cervello(self, backend: str) -> str:
        """Cambia il backend LLM a runtime (mock|local|claude|cloud) e ricostruisce
        il cervello. La memoria della conversazione viene azzerata. Se la
        costruzione fallisce (es. SDK/chiave mancante) lo stato resta invariato."""
        backend = backend.lower().strip()
        if backend not in ("mock", "local", "claude", "cloud"):
            raise ValueError(
                f"Cervello sconosciuto: '{backend}'. Usa: mock, local, claude o cloud.")
        prec = self.config.llm_backend
        self.config.llm_backend = backend
        try:
            self.brain = build_brain(self.config, self.persona)
        except Exception:
            self.config.llm_backend = prec        # rollback: niente stato a metà
            raise
        return self.descrizione_cervello()

    def set_modello(self, nome: str) -> str:
        """Cambia il modello del backend attivo e ricostruisce il cervello
        (local -> modello Ollama, claude -> id Anthropic, cloud -> modello del
        provider OpenAI-compatibile). Memoria azzerata; rollback se fallisce."""
        b = self.backend_cervello
        campo = {"local": "local_llm_model", "claude": "model",
                 "cloud": "cloud_llm_model"}.get(b)
        if campo is None:
            raise ValueError(
                "Il modello si cambia solo col cervello 'local', 'claude' o 'cloud'. "
                "Prima fai:  /cervello local")
        prec = getattr(self.config, campo)
        setattr(self.config, campo, nome)
        try:
            self.brain = build_brain(self.config, self.persona)
        except Exception:
            setattr(self.config, campo, prec)     # rollback
            raise
        return self.descrizione_cervello()

    # -- manopole di latenza/campionamento (a caldo, SENZA azzerare la memoria) --
    # Aggiornano la config E, dove possibile, l'oggetto cervello già vivo: così
    # cambiano al volo senza ricostruire il cervello (la conversazione resta).

    def set_think(self, modo: str) -> str:
        """Claude: 'adaptive' = ragionamento+effort (più qualità, più lento) /
        'off' = niente (TTFT basso, indispensabile con Haiku)."""
        m = (modo or "").lower().strip()
        if m in ("adaptive", "on", "si", "sì", "1"):
            valore = "adaptive"
        elif m in ("off", "no", "0", ""):
            valore = ""
        else:
            raise ValueError("Uso: /think off|adaptive")
        self.config.claude_think = valore
        if self.backend_cervello == "claude" and hasattr(self.brain, "think"):
            self.brain.think = valore
        return valore or "off"

    def set_max_tokens(self, n: int) -> int:
        """Lunghezza massima della risposta (corta = più rapida)."""
        if n <= 0:
            raise ValueError("La lunghezza dev'essere un numero > 0.")
        self.config.max_tokens = n
        if hasattr(self.brain, "max_tokens"):
            self.brain.max_tokens = n
        return n

    def set_temperatura(self, x: float) -> float:
        """Varietà/creatività del campionamento (per 'local' o 'cloud'; Claude
        non usa la temperature)."""
        b = self.backend_cervello
        if b == "local":
            self.config.local_llm_temp = x
        elif b == "cloud":
            self.config.cloud_llm_temp = x
        else:
            raise ValueError(
                "La temperatura vale solo col cervello 'local' o 'cloud' "
                "(Claude non la usa).")
        if hasattr(self.brain, "temperature"):
            self.brain.temperature = x
        return x

    def set_provider(self, nome_o_url: str) -> str:
        """Endpoint del cervello cloud: scorciatoie groq|openrouter|openai oppure
        un URL OpenAI-compatibile completo."""
        url = _PROVIDER_URLS.get(nome_o_url.lower().strip(), nome_o_url.strip())
        self.config.cloud_llm_url = url
        if self.backend_cervello == "cloud" and hasattr(self.brain, "base_url"):
            self.brain.base_url = url.rstrip("/")
        return url

    # -- controllo persona -------------------------------------------------

    @property
    def persona_nome(self) -> str:
        """Nome breve della personalità attiva (es. 'default', 'veterano')."""
        return self.persona_origine

    def set_persona(self, persona: Persona, origine: str = "personalizzata") -> None:
        """Carica un'altra personalità a runtime e ricostruisce il cervello col
        nuovo system prompt. La memoria della conversazione viene azzerata."""
        self.persona = persona
        self.persona_origine = origine
        self.brain = build_brain(self.config, self.persona)

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

    def parla(self, input_utente: str, su_frase=None) -> RisultatoParlato:
        """Pipeline completa: genera e fa parlare Emilio (col bip dove serve).

        `su_frase`, se passato, viene chiamato col testo (già bippato) PRIMA di
        pronunciarlo — per la modalità monitor della console (vedi /verboso)."""
        ris = self.genera(input_utente)
        if su_frase and ris.testo_detto.strip():
            su_frase(ris.testo_detto)
        # Si pronuncia il testo GREZZO: la voce sintetizza la frase naturale e
        # copre con un bip solo gli intervalli sporchi (span_censura).
        ris.voce = self._pronuncia(ris.testo_grezzo, ris.span_censura, ris.emozione)
        return ris

    def rispondi(self, input_utente: str, su_frase=None) -> RisultatoParlato:
        """Parla scegliendo la pipeline attiva: streaming o a blocco unico.

        `su_frase` (callback opzionale) riceve ogni frase, già bippata, appena
        prima che venga pronunciata: serve al terminale per mostrare in tempo
        reale ciò che Emilio sta per dire."""
        if self.streaming:
            return self.parla_streaming(input_utente, su_frase=su_frase)
        return self.parla(input_utente, su_frase=su_frase)

    def set_streaming(self, attivo: bool) -> None:
        """Attiva/disattiva la pipeline streaming a runtime (admin)."""
        self.streaming = attivo

    def parla_streaming(self, input_utente: str, su_frase=None) -> RisultatoParlato:
        """Come `parla`, ma pronuncia FRASE PER FRASE mentre l'LLM genera: la
        prima battuta parte appena pronta, senza aspettare tutta la risposta.

        Ogni frase passa dal supervisore singolarmente (stessa censura via BIP).
        Il tag di stato d'animo iniziale viene staccato prima di parlare.
        `su_frase` (callback opzionale) riceve ogni frase BIPPATA appena prima di
        pronunciarla (modalità monitor della console, /verboso).
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
            detto = self.moderator.testo_con_bip(frase, report)
            if report.has_profanity or report.has_blasphemy:
                arrabbiato = True
            if su_frase:                      # monitor: mostra cosa STA per dire
                su_frase(detto)
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
            frasi_dette.append(detto)
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
