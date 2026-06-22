"""Ascolto di Emilio: riconoscimento vocale (STT) per parlargli a voce.

Sta **a monte** della pipeline: cattura il microfono, trascrive in testo, e il
testo va al cervello (come se l'avessi digitato). Stesso pattern degli altri
componenti (ABC + factory + backend mock/reale):

  * MockAscoltatore    -> ritorna una frase fissa (sviluppo/test, nessun audio)
  * WhisperAscoltatore -> faster-whisper su CPU (offline, italiano)
  * MlxAscoltatore     -> faster-whisper-mlx su GPU/ANE di Apple Silicon: sul Mac
                          è MOLTO più rapido di faster-whisper su CPU.

Registrazione: di default usa un VAD a energia (smette quando smetti di parlare,
serve `sounddevice`); con `EMILIO_STT_VAD=0` registra invece N secondi fissi via
`ffmpeg`. Come l'LLM locale, lo STT gira sul **Mac**; sul prodotto finale il
Raspberry, che non regge l'inferenza, userà un servizio cloud o un modello
piccolo. Il microfono su macOS richiede il permesso (la prima volta il sistema
lo chiede al terminale/app che lancia Emilio).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import wave
from abc import ABC, abstractmethod


# ---------------------------------------------------------------------------
# Utilità comuni
# ---------------------------------------------------------------------------

# Frasi che Whisper "allucina" sul silenzio (da sottotitoli nei dati): da scartare.
_ALLUCINAZIONI = (
    "sottotitoli", "qtss", "amara.org", "iscriviti al canale",
    "grazie per la visione", "sottotitoli e revisione",
)


def _scarta_allucinazione(testo: str) -> str:
    """Vuoto se il testo è una tipica allucinazione da silenzio, altrimenti il testo."""
    low = testo.lower()
    if any(a in low for a in _ALLUCINAZIONI):
        return ""
    return testo


def _microfono_default() -> str:
    """Indice del microfono di default per avfoundation (macOS).

    ffmpeg elenca i device su stderr; prendo il primo input audio. Se non riesco,
    ripiego su "0" (di solito il microfono interno/di default).
    """
    if not shutil.which("ffmpeg"):
        return "0"
    try:
        r = subprocess.run(
            ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
            capture_output=True, text=True, timeout=10,
        )
        in_audio = False
        for line in r.stderr.splitlines():
            if "audio devices" in line.lower():
                in_audio = True
                continue
            if in_audio:
                m = re.search(r"\[(\d+)\]", line)
                if m:
                    return m.group(1)
    except Exception:
        pass
    return "0"


def _rms_int16(arr) -> float:
    """Energia (RMS) di un blocco di campioni int16 (numpy array)."""
    if getattr(arr, "size", 0) == 0:
        return 0.0
    x = arr.astype("float32")
    return float((x * x).mean() ** 0.5)


def _vad_stato(rms: float, soglia: float, parlato: bool, silenzio_acc: float,
               dt: float, silenzio_coda: float) -> tuple[bool, float, bool]:
    """Aggiorna lo stato del VAD a energia per un blocco audio.

    Ritorna (parlato, silenzio_accumulato, stop). `stop` diventa True quando,
    dopo che si è iniziato a parlare, si accumula abbastanza silenzio in coda.
    """
    if rms >= soglia:
        return True, 0.0, False
    if parlato:
        silenzio_acc += dt
        return True, silenzio_acc, silenzio_acc >= silenzio_coda
    return False, 0.0, False


# ---------------------------------------------------------------------------
# Ascoltatori
# ---------------------------------------------------------------------------

class Ascoltatore(ABC):
    @abstractmethod
    def ascolta(self, secondi: float = 5.0) -> str:
        """Registra l'audio dal microfono e ritorna il testo trascritto."""
        ...

    def prewarm(self) -> None:
        """Pre-carica il modello (no-op di default). Chiamato in sottofondo
        all'avvio così la prima trascrizione non paga il caricamento."""


class MockAscoltatore(Ascoltatore):
    """Non usa il microfono: ritorna sempre la stessa frase (test/sviluppo)."""

    def __init__(self, frase: str = "Ciao Emilio, come butta?"):
        self.frase = frase

    def ascolta(self, secondi: float = 5.0) -> str:
        return self.frase


class AscoltatoreMic(Ascoltatore):
    """Base per i backend che registrano dal microfono.

    Gestisce la registrazione (VAD stop-on-silence via sounddevice, oppure N
    secondi fissi via ffmpeg) e delega la trascrizione alle sottoclassi.
    """

    def __init__(self, device_audio: str = "", usa_vad: bool = True,
                 max_secondi: float = 12.0, silenzio_coda: float = 0.8):
        self._device_audio = device_audio    # risolto pigramente (evita ffmpeg all'avvio)
        self.usa_vad = usa_vad
        self.max_secondi = float(max_secondi)
        self.silenzio_coda = float(silenzio_coda)

    @abstractmethod
    def trascrivi(self, wav: str) -> str:
        """Trascrive un file WAV già pronto (utile anche per i test)."""
        ...

    def ascolta(self, secondi: float = 5.0) -> str:
        wav = os.path.join(tempfile.gettempdir(), "emilio_mic.wav")
        # VAD: smette quando smetti di parlare; se non c'è sounddevice ripiega
        # sulla registrazione a tempo fisso con ffmpeg.
        if not (self.usa_vad and self._registra_vad(wav)):
            self._registra(secondi, wav)
        return self.trascrivi(wav)

    def _registra(self, secondi: float, wav: str) -> None:
        """Registra `secondi` fissi col microfono via ffmpeg (avfoundation)."""
        if not shutil.which("ffmpeg"):
            raise RuntimeError("ffmpeg non trovato: serve per registrare dal microfono.")
        device = self._device_audio or _microfono_default()
        cmd = ["ffmpeg", "-y", "-f", "avfoundation", "-i", f":{device}",
               "-t", str(secondi), "-ar", "16000", "-ac", "1", wav]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=float(secondi) + 15)
        except subprocess.TimeoutExpired:
            raise RuntimeError("registrazione bloccata: il device audio non risponde.") from None
        if r.returncode != 0:
            coda = "\n".join(r.stderr.strip().splitlines()[-3:])
            raise RuntimeError(
                "registrazione dal microfono fallita. Verifica il permesso Microfono "
                "(Impostazioni di Sistema > Privacy e Sicurezza > Microfono) e la "
                "variabile EMILIO_MIC_DEVICE.\n" + coda
            )

    def _registra_vad(self, wav: str) -> bool:
        """Registra finché parli, poi smette dopo una breve pausa (VAD a energia).

        Usa `sounddevice` (PortAudio) col microfono di sistema di default. Ritorna
        False se sounddevice non è installato o la cattura fallisce: il chiamante
        ripiega su ffmpeg a tempo fisso. Il device è quello di default del sistema
        (l'indice avfoundation di EMILIO_MIC_DEVICE vale solo per ffmpeg).
        """
        try:
            import sounddevice as sd
        except Exception:
            return False
        sr = 16000
        blocco = int(sr * 0.03)         # 30 ms
        dt = blocco / sr
        try:
            frames = []
            ambiente = []
            parlato = False
            silenzio_acc = 0.0
            elapsed = 0.0
            with sd.InputStream(samplerate=sr, channels=1, dtype="int16",
                                blocksize=blocco) as stream:
                # calibra il rumore di fondo (~0.3s) e fissa la soglia
                for _ in range(max(1, int(0.3 / dt))):
                    dati, _o = stream.read(blocco)
                    ambiente.append(_rms_int16(dati))
                base = sorted(ambiente)[len(ambiente) // 2] if ambiente else 0.0
                soglia = max(350.0, base * 3.0 + 150.0)
                while elapsed < self.max_secondi:
                    dati, _o = stream.read(blocco)
                    frames.append(dati.copy())
                    parlato, silenzio_acc, stop = _vad_stato(
                        _rms_int16(dati), soglia, parlato, silenzio_acc, dt,
                        self.silenzio_coda)
                    elapsed += dt
                    if stop:
                        break
                    # se non inizi mai a parlare entro ~6s, lascia perdere
                    if not parlato and elapsed >= min(self.max_secondi, 6.0):
                        break
            if not frames:
                return False
            import numpy as np
            audio = np.concatenate(frames, axis=0)
            with wave.open(wav, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(sr)
                w.writeframes(audio.tobytes())
            return True
        except Exception:
            return False


class WhisperAscoltatore(AscoltatoreMic):
    """Microfono + trascrizione con faster-whisper su CPU (offline, IT)."""

    def __init__(self, model: str = "base", lingua: str = "it",
                 compute: str = "int8", **kw):
        super().__init__(**kw)
        self.model_name = model
        self.lingua = lingua
        self.compute = compute
        self._model = None

    def _carica(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel  # import pigro
            except ImportError:
                raise RuntimeError(
                    "faster-whisper non installato. Esegui: pip install -e \".[listen]\""
                ) from None
            try:
                self._model = WhisperModel(self.model_name, device="cpu",
                                           compute_type=self.compute)
            except ValueError:
                # alcune build di CTranslate2 non supportano int8: ripiega
                self._model = WhisperModel(self.model_name, device="cpu",
                                           compute_type="float32")
        return self._model

    def prewarm(self) -> None:
        self._carica()

    def trascrivi(self, wav: str) -> str:
        """`vad_filter` salta i tratti di silenzio: migliora l'accuratezza ed
        evita le tipiche allucinazioni di Whisper quando non parli."""
        model = self._carica()
        segmenti, _ = model.transcribe(wav, language=self.lingua, vad_filter=True)
        testo = " ".join(s.text for s in segmenti).strip()
        return _scarta_allucinazione(testo)


# Nome corto (tiny/base/small/medium/large) -> repo dei pesi MLX su Hugging Face.
_REPO_MLX = {
    "tiny": "mlx-community/whisper-tiny-mlx",
    "base": "mlx-community/whisper-base-mlx",
    "small": "mlx-community/whisper-small-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "large": "mlx-community/whisper-large-v3-mlx",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "turbo": "mlx-community/whisper-large-v3-turbo",
}


def _risolvi_repo_mlx(model: str) -> str:
    if "/" in model:               # già un repo HF completo
        return model
    return _REPO_MLX.get(model, f"mlx-community/whisper-{model}-mlx")


class MlxAscoltatore(AscoltatoreMic):
    """Trascrizione con mlx-whisper su GPU/ANE di Apple Silicon (rapido sul Mac).

    Usa `mlx_whisper.transcribe`; il modello (pesi MLX) si scarica da Hugging
    Face alla prima esecuzione e resta in cache. `prewarm` lo scalda in anticipo.
    """

    def __init__(self, model: str = "base", lingua: str = "it", **kw):
        super().__init__(**kw)
        self.repo = _risolvi_repo_mlx(model)
        self.lingua = lingua

    def prewarm(self) -> None:
        try:
            import mlx_whisper
        except Exception:
            return
        # scalda su 0.2s di silenzio (scarica/compila i pesi una volta sola)
        warm = os.path.join(tempfile.gettempdir(), "emilio_warm.wav")
        try:
            with wave.open(warm, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(16000)
                w.writeframes(b"\x00\x00" * 3200)
            mlx_whisper.transcribe(warm, path_or_hf_repo=self.repo, language=self.lingua)
        except Exception:
            pass

    def trascrivi(self, wav: str) -> str:
        try:
            import mlx_whisper  # import pigro
        except ImportError:
            raise RuntimeError(
                "mlx-whisper non installato. Esegui: pip install -e \".[listen-mlx]\""
            ) from None
        res = mlx_whisper.transcribe(wav, path_or_hf_repo=self.repo, language=self.lingua)
        return _scarta_allucinazione((res.get("text") or "").strip())


def build_ascoltatore(config) -> Ascoltatore:
    """Factory: sceglie il backend di ascolto in base alla configurazione."""
    backend = getattr(config, "stt_backend", "mock").lower()
    comuni = dict(
        device_audio=getattr(config, "mic_device", ""),
        usa_vad=getattr(config, "stt_vad", True),
        max_secondi=getattr(config, "stt_max", 12.0),
        silenzio_coda=getattr(config, "stt_silenzio", 0.8),
    )
    if backend == "mlx":
        return MlxAscoltatore(model=getattr(config, "stt_model", "base"),
                              lingua=getattr(config, "stt_lingua", "it"), **comuni)
    if backend in ("whisper", "reale"):
        return WhisperAscoltatore(model=getattr(config, "stt_model", "base"),
                                  lingua=getattr(config, "stt_lingua", "it"),
                                  compute=getattr(config, "stt_compute", "int8"), **comuni)
    return MockAscoltatore()
