"""Ascolto di Emilio: riconoscimento vocale (STT) per parlargli a voce.

Sta **a monte** della pipeline: cattura il microfono, trascrive in testo, e il
testo va al cervello (come se l'avessi digitato). Stesso pattern degli altri
componenti (ABC + factory + backend mock/reale):

  * MockAscoltatore    -> ritorna una frase fissa (sviluppo/test, nessun audio)
  * WhisperAscoltatore -> registra dal microfono (ffmpeg, avfoundation su macOS)
                          e trascrive con faster-whisper (offline, italiano).

Come l'LLM locale, lo STT gira sul **Mac**; sul prodotto finale il Raspberry,
che non regge l'inferenza, userà eventualmente un servizio cloud o un modello
piccolo. Il microfono su macOS richiede il permesso (la prima volta il sistema
lo chiede al terminale/app che lancia Emilio).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod


class Ascoltatore(ABC):
    @abstractmethod
    def ascolta(self, secondi: float = 5.0) -> str:
        """Registra ~`secondi` di audio dal microfono e ritorna il testo."""
        ...


class MockAscoltatore(Ascoltatore):
    """Non usa il microfono: ritorna sempre la stessa frase (test/sviluppo)."""

    def __init__(self, frase: str = "Ciao Emilio, come butta?"):
        self.frase = frase

    def ascolta(self, secondi: float = 5.0) -> str:
        return self.frase


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


class WhisperAscoltatore(Ascoltatore):
    """Microfono (ffmpeg) + trascrizione con faster-whisper (offline, IT)."""

    def __init__(self, model: str = "small", lingua: str = "it",
                 device_audio: str = "", compute: str = "int8"):
        self.model_name = model
        self.lingua = lingua
        self.compute = compute
        self.device_audio = device_audio or _microfono_default()
        self._model = None

    def _carica(self):
        if self._model is None:
            from faster_whisper import WhisperModel  # import pigro
            self._model = WhisperModel(self.model_name, device="cpu",
                                       compute_type=self.compute)
        return self._model

    def _registra(self, secondi: float, wav: str) -> None:
        if not shutil.which("ffmpeg"):
            raise RuntimeError("ffmpeg non trovato: serve per registrare dal microfono.")
        cmd = ["ffmpeg", "-y", "-f", "avfoundation", "-i", f":{self.device_audio}",
               "-t", str(secondi), "-ar", "16000", "-ac", "1", wav]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    def trascrivi(self, wav: str) -> str:
        """Trascrive un file audio già pronto (utile anche per i test)."""
        model = self._carica()
        segmenti, _ = model.transcribe(wav, language=self.lingua)
        return " ".join(s.text for s in segmenti).strip()

    def ascolta(self, secondi: float = 5.0) -> str:
        wav = os.path.join(tempfile.gettempdir(), "emilio_mic.wav")
        self._registra(secondi, wav)
        return self.trascrivi(wav)


def build_ascoltatore(config) -> Ascoltatore:
    """Factory: sceglie il backend di ascolto in base alla configurazione."""
    backend = getattr(config, "stt_backend", "mock").lower()
    if backend in ("whisper", "reale"):
        return WhisperAscoltatore(
            model=getattr(config, "stt_model", "small"),
            lingua=getattr(config, "stt_lingua", "it"),
            device_audio=getattr(config, "mic_device", ""),
        )
    return MockAscoltatore()
