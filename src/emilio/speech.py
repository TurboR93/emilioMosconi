"""Voce di Emilio: sistema TTS flessibile, a bassa latenza e misurabile.

Obiettivi:
  * FLESSIBILE  -> più "profili voce" selezionabili (anche a runtime), così puoi
                   provare voci/modelli diversi senza toccare il codice.
  * VELOCE      -> ElevenLabs in STREAMING (l'audio parte mentre viene sintetizzato)
                   + modello a bassa latenza (Flash v2.5).
  * MISURABILE  -> ogni `say()` restituisce le metriche di latenza (TTFB e totale),
                   per capire subito se la risposta è fluida.

Backend:
  * MockSpeaker       -> stampa (sviluppo/test, nessuna dipendenza)
  * Pyttsx3Speaker    -> TTS offline (senza rete)
  * ElevenLabsSpeaker -> TTS cloud realistico in italiano, con streaming

Il testo che arriva qui è già passato dal supervisore (vedi agent.py): questo
modulo si limita a pronunciarlo.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from . import audio_bip


# ---------------------------------------------------------------------------
# Metriche di latenza
# ---------------------------------------------------------------------------

@dataclass
class SpeechMetrics:
    """Tempi di una sintesi vocale (in secondi)."""
    backend: str
    profilo: str
    ttfb: float | None = None     # time-to-first-byte audio (None se non in streaming)
    totale: float = 0.0           # tempo totale fino a fine riproduzione/sintesi
    caratteri: int = 0

    def __str__(self) -> str:
        ttfb = f"{self.ttfb*1000:.0f}ms" if self.ttfb is not None else "n/d"
        return (f"voce='{self.profilo}' backend={self.backend} "
                f"TTFB={ttfb} totale={self.totale*1000:.0f}ms ({self.caratteri} car.)")


# ---------------------------------------------------------------------------
# Profilo voce (descrive UNA voce: backend, modello, parametri)
# ---------------------------------------------------------------------------

@dataclass
class VoiceProfile:
    name: str
    backend: str                       # elevenlabs | pyttsx3 | mock
    descrizione: str = ""
    # --- parametri ElevenLabs ---
    voice_id: str = ""                 # se vuoto usa ELEVENLABS_VOICE_ID
    model: str = "eleven_flash_v2_5"   # flash = bassa latenza
    stability: float = 0.4
    similarity_boost: float = 0.85
    style: float = 0.0
    speed: float = 1.0
    streaming: bool = True
    optimize_streaming_latency: int = 3  # 0..4 (più alto = meno latenza)
    output_format: str = "mp3_44100_128"


def default_profiles(config) -> list[VoiceProfile]:
    """Profili predefiniti. `voice_id` vuoto eredita da ELEVENLABS_VOICE_ID."""
    vid = config.elevenlabs_voice_id or ""
    return [
        VoiceProfile("mock", "mock", "Stampa soltanto (sviluppo/test)"),
        VoiceProfile("offline", "pyttsx3", "TTS offline, senza rete"),
        VoiceProfile(
            "veloce", "elevenlabs",
            "Bassa latenza per dialogo dal vivo (Flash v2.5, streaming)",
            voice_id=vid, model="eleven_flash_v2_5",
            streaming=True, optimize_streaming_latency=4,
        ),
        VoiceProfile(
            "realistico", "elevenlabs",
            "Massimo realismo (Multilingual v2)",
            voice_id=vid, model="eleven_multilingual_v2",
            streaming=True, optimize_streaming_latency=2,
            stability=0.5, similarity_boost=0.85,
        ),
        VoiceProfile(
            "espressivo", "elevenlabs",
            "Più espressivo/teatrale (Multilingual v2, stabilità bassa)",
            voice_id=vid, model="eleven_multilingual_v2",
            streaming=True, optimize_streaming_latency=2,
            stability=0.25, similarity_boost=0.8, style=0.6,
        ),
    ]


# ---------------------------------------------------------------------------
# Speaker
# ---------------------------------------------------------------------------

class Speaker(ABC):
    @abstractmethod
    def say(self, text: str, bleep_spans: list[tuple[int, int]] | None = None) -> SpeechMetrics:
        """Pronuncia `text`. Se `bleep_spans` è valorizzato, copre quegli
        intervalli di CARATTERE con un BIP sull'audio (censura amministratore)."""
        ...


class MockSpeaker(Speaker):
    def __init__(self, profilo: str = "mock", bip_marker: str = "[BIP]"):
        self.profilo = profilo
        self.bip_marker = bip_marker

    def say(self, text: str, bleep_spans: list[tuple[int, int]] | None = None) -> SpeechMetrics:
        t0 = time.perf_counter()
        mostrato = (audio_bip.applica_span(text, bleep_spans, self.bip_marker)
                    if bleep_spans else text)
        print(f"🔊 [Emilio/{self.profilo}] {mostrato}")
        return SpeechMetrics("mock", self.profilo, None, time.perf_counter() - t0, len(text))


class Pyttsx3Speaker(Speaker):
    def __init__(self, profilo: str = "offline", language: str = "it", voce: str = ""):
        import pyttsx3
        self.profilo = profilo
        self._engine = pyttsx3.init()
        voci = self._engine.getProperty("voices")
        lang = language.lower()

        def _blob(v):
            return f"{v.id} {getattr(v, 'name', '')}".lower()

        scelta = None
        # 1) voce richiesta esplicitamente (per nome o id, es. "Grandpa")
        if voce:
            scelta = next((v.id for v in voci if voce.lower() in _blob(v)), None)
        # 2) altrimenti la prima voce della lingua giusta
        if scelta is None:
            scelta = next(
                (v.id for v in voci
                 if f"{lang}-{lang}" in _blob(v) or f"{lang}_{lang}" in _blob(v)
                 or "ital" in _blob(v)),
                None,
            )
        if scelta:
            self._engine.setProperty("voice", scelta)

    def say(self, text: str, bleep_spans: list[tuple[int, int]] | None = None) -> SpeechMetrics:
        t0 = time.perf_counter()
        # TTS offline senza timestamp: ripiego "sicuro" — la parolaccia non viene
        # pronunciata (sostituita da "bip" parlato). Approssima il bip audio.
        da_dire = audio_bip.testo_sicuro(text, bleep_spans) if bleep_spans else text
        self._engine.say(da_dire)
        self._engine.runAndWait()
        return SpeechMetrics("pyttsx3", self.profilo, None, time.perf_counter() - t0, len(text))


def _stream_player() -> list[str] | None:
    """Comando di un player che legge audio MP3 da stdin (per lo streaming)."""
    if shutil.which("mpg123"):
        return ["mpg123", "-q", "-"]
    if shutil.which("ffplay"):
        return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "-i", "pipe:0"]
    return None


def _play_file(path: str) -> bool:
    """Riproduce un file audio col primo player disponibile (no streaming)."""
    for player in ("afplay", "mpg123", "ffplay", "cvlc", "aplay"):
        exe = shutil.which(player)
        if not exe:
            continue
        args = [exe]
        if player == "ffplay":
            args += ["-nodisp", "-autoexit", "-loglevel", "quiet"]
        if player == "cvlc":
            args += ["--play-and-exit", "--intf", "dummy"]
        args.append(path)
        try:
            subprocess.run(args, check=False)
            return True
        except Exception:
            continue
    return False


class ElevenLabsSpeaker(Speaker):
    """TTS ElevenLabs con streaming a bassa latenza e misura della latenza.

    In streaming: apre il flusso audio e lo invia al player man mano che arriva
    (l'audio inizia prima che la frase sia interamente sintetizzata).
    """

    BASE = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    def __init__(self, profile: VoiceProfile, api_key: str,
                 audio_out: str = "emilio_voce.mp3", bip_dir: str | None = None):
        if not api_key:
            raise RuntimeError("ELEVENLABS_API_KEY mancante.")
        if not profile.voice_id:
            raise RuntimeError(
                "voice_id mancante: imposta ELEVENLABS_VOICE_ID o il voice_id del profilo."
            )
        self.p = profile
        self.api_key = api_key
        self.audio_out = audio_out
        self.bip_dir = bip_dir

    def _payload(self, text: str) -> dict:
        return {
            "text": text,
            "model_id": self.p.model,
            "voice_settings": {
                "stability": self.p.stability,
                "similarity_boost": self.p.similarity_boost,
                "style": self.p.style,
                "speed": self.p.speed,
            },
        }

    def say(self, text: str, bleep_spans: list[tuple[int, int]] | None = None) -> SpeechMetrics:
        if bleep_spans:
            return self._say_censura(text, bleep_spans)
        return self._say_diretto(text)

    def _say_diretto(self, text: str) -> SpeechMetrics:
        """Sintesi normale: streaming a bassa latenza, o file di ripiego."""
        import requests

        headers = {"xi-api-key": self.api_key, "content-type": "application/json"}
        t0 = time.perf_counter()
        ttfb: float | None = None

        if self.p.streaming:
            url = self.BASE.format(voice_id=self.p.voice_id) + "/stream"
            params = {
                "optimize_streaming_latency": self.p.optimize_streaming_latency,
                "output_format": self.p.output_format,
            }
            player_cmd = _stream_player()
            if player_cmd is not None:
                with requests.post(url, headers=headers, params=params,
                                   json=self._payload(text), stream=True, timeout=30) as r:
                    r.raise_for_status()
                    proc = subprocess.Popen(player_cmd, stdin=subprocess.PIPE)
                    for chunk in r.iter_content(chunk_size=4096):
                        if not chunk:
                            continue
                        if ttfb is None:
                            ttfb = time.perf_counter() - t0
                        try:
                            proc.stdin.write(chunk)
                        except BrokenPipeError:
                            break
                    if proc.stdin:
                        proc.stdin.close()
                    proc.wait()
                return SpeechMetrics("elevenlabs", self.p.name, ttfb,
                                     time.perf_counter() - t0, len(text))
            # nessun player da stdin: ripiega su file
        # --- non streaming (o fallback): sintetizza su file e riproduci ---
        url = self.BASE.format(voice_id=self.p.voice_id)
        params = {"output_format": self.p.output_format}
        resp = requests.post(url, headers=headers, params=params,
                             json=self._payload(text), timeout=30)
        resp.raise_for_status()
        ttfb = time.perf_counter() - t0
        with open(self.audio_out, "wb") as f:
            f.write(resp.content)
        if not _play_file(self.audio_out):
            print(f"🔊 [Emilio] (audio salvato in {self.audio_out}, nessun player)")
        return SpeechMetrics("elevenlabs", self.p.name, ttfb,
                             time.perf_counter() - t0, len(text))

    def _say_censura(self, text: str, bleep_spans: list[tuple[int, int]]) -> SpeechMetrics:
        """Sintesi CON timestamp + BIP sugli intervalli sporchi.

        Chiede a ElevenLabs l'audio con l'allineamento carattere→tempo
        (endpoint with-timestamps), mappa gli span sporchi su intervalli di
        tempo e ci sovrappone il file BIP via ffmpeg. Se qualcosa va storto,
        ripiego SICURO: risintetizza il testo con "bip" parlato, così la
        parolaccia non viene mai udita.
        """
        import base64
        import requests

        headers = {"xi-api-key": self.api_key, "content-type": "application/json"}
        url = self.BASE.format(voice_id=self.p.voice_id) + "/with-timestamps"
        params = {"output_format": self.p.output_format}
        t0 = time.perf_counter()
        try:
            resp = requests.post(url, headers=headers, params=params,
                                 json=self._payload(text), timeout=30)
            resp.raise_for_status()
            ttfb = time.perf_counter() - t0
            data = resp.json()
            audio = base64.b64decode(data["audio_base64"])
            align = data.get("alignment") or {}
            cs = align.get("character_start_times_seconds") or []
            ce = align.get("character_end_times_seconds") or []

            grezzo = self.audio_out + ".raw"
            with open(grezzo, "wb") as f:
                f.write(audio)

            intervalli = audio_bip.intervalli_da_allineamento(bleep_spans, cs, ce)
            beep = audio_bip.scegli_beep(self.bip_dir)
            if audio_bip.applica_bip(grezzo, intervalli, beep, self.audio_out):
                try:
                    os.remove(grezzo)
                except OSError:
                    pass
                if not _play_file(self.audio_out):
                    print(f"🔊 [Emilio] (audio bippato salvato in {self.audio_out}, nessun player)")
                return SpeechMetrics("elevenlabs", self.p.name, ttfb,
                                     time.perf_counter() - t0, len(text))
        except Exception as e:  # pragma: no cover - dipende dalla rete/ffmpeg
            print(f"⚠️  Bip audio non riuscito ({e}); ripiego sicuro senza turpiloquio.")

        # Ripiego sicuro: niente parolaccia udibile.
        return self._say_diretto(audio_bip.testo_sicuro(text, bleep_spans))


# ---------------------------------------------------------------------------
# Gestore voci: tiene i profili e permette di cambiarli a runtime
# ---------------------------------------------------------------------------

class VoiceManager:
    """Catalogo di profili voce con voce attiva selezionabile a runtime."""

    def __init__(self, config, profiles: list[VoiceProfile] | None = None,
                 attiva: str | None = None):
        self.config = config
        self.profiles: dict[str, VoiceProfile] = {
            p.name: p for p in (profiles or default_profiles(config))
        }
        self.attiva = attiva or self._default_attiva()
        self._speaker: Speaker | None = None

    def _default_attiva(self) -> str:
        # rispetta EMILIO_VOICE; altrimenti deriva dal vecchio EMILIO_TTS
        scelta = getattr(self.config, "voice_profile", None)
        if scelta and scelta in self._all_names():
            return scelta
        mappa = {"elevenlabs": "realistico", "pyttsx3": "offline", "mock": "mock"}
        return mappa.get(getattr(self.config, "tts_backend", "mock"), "mock")

    def _all_names(self) -> list[str]:
        return list((self.profiles or {}).keys())

    def lista(self) -> list[VoiceProfile]:
        return list(self.profiles.values())

    def profilo_attivo(self) -> VoiceProfile:
        return self.profiles[self.attiva]

    def imposta(self, nome: str) -> VoiceProfile:
        if nome not in self.profiles:
            raise ValueError(
                f"Voce '{nome}' sconosciuta. Disponibili: {', '.join(self.profiles)}"
            )
        self.attiva = nome
        self._speaker = None  # ricostruisci alla prossima frase
        return self.profiles[nome]

    def aggiungi(self, profilo: VoiceProfile) -> None:
        self.profiles[profilo.name] = profilo

    @property
    def speaker(self) -> Speaker:
        if self._speaker is None:
            self._speaker = self._build(self.profilo_attivo())
        return self._speaker

    def _build(self, p: VoiceProfile) -> Speaker:
        if p.backend == "elevenlabs":
            vid = p.voice_id or (self.config.elevenlabs_voice_id or "")
            prof = p if p.voice_id else VoiceProfile(**{**p.__dict__, "voice_id": vid})
            return ElevenLabsSpeaker(
                prof,
                api_key=self.config.elevenlabs_api_key or "",
                audio_out=self.config.audio_out,
                bip_dir=getattr(self.config, "bip_dir", None),
            )
        if p.backend == "pyttsx3":
            return Pyttsx3Speaker(profilo=p.name, language=self.config.tts_language,
                                  voce=getattr(self.config, "tts_voice", ""))
        return MockSpeaker(profilo=p.name,
                           bip_marker=getattr(self.config, "bip_marker", "[BIP]"))

    def say(self, text: str, bleep_spans: list[tuple[int, int]] | None = None) -> SpeechMetrics:
        return self.speaker.say(text, bleep_spans)


def list_elevenlabs_voices(api_key: str) -> list[dict]:
    """Elenca le voci disponibili sul tuo account ElevenLabs (nome + id)."""
    import requests
    r = requests.get(
        "https://api.elevenlabs.io/v1/voices",
        headers={"xi-api-key": api_key}, timeout=15,
    )
    r.raise_for_status()
    return [
        {"voice_id": v.get("voice_id"), "name": v.get("name"),
         "labels": v.get("labels", {})}
        for v in r.json().get("voices", [])
    ]


def build_voice_manager(config) -> VoiceManager:
    return VoiceManager(config)
