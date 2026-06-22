"""Configurazione centrale di Emilio.

Tutto è sovrascrivibile da variabili d'ambiente, così sul Mac (o sul Raspberry)
basta esportare le chiavi senza toccare il codice.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on", "si", "sì")


@dataclass
class EmilioConfig:
    # --- Cervello (LLM via API) ----------------------------------------
    use_real_llm: bool = _env_bool("EMILIO_USE_LLM", False)
    model: str = os.environ.get("EMILIO_MODEL", "claude-opus-4-8")
    max_tokens: int = int(os.environ.get("EMILIO_MAX_TOKENS", "800"))
    effort: str = os.environ.get("EMILIO_EFFORT", "medium")  # low|medium|high
    # Backend del cervello: mock | claude | local. Se vuoto, EMILIO_USE_LLM=1
    # equivale a "claude" (retrocompatibilità), altrimenti "mock".
    llm_backend: str = os.environ.get("EMILIO_LLM", "")
    # LLM locale via Ollama (API nativa) sul Mac. think=False evita il
    # "ragionamento" lento dei modelli come Gemma 4 (latenza ~30s -> pochi s).
    local_llm_url: str = os.environ.get("EMILIO_LOCAL_URL", "http://localhost:11434")
    local_llm_model: str = os.environ.get("EMILIO_LOCAL_MODEL", "gemma4:12b")
    local_llm_think: bool = _env_bool("EMILIO_LOCAL_THINK", False)
    local_llm_key: str = os.environ.get("EMILIO_LOCAL_KEY", "")

    # --- Supervisione / censura (BIP sull'audio) -----------------------
    # Attivabile/disattivabile dall'amministratore (anche a runtime).
    # Modello: il cervello NON riformula; il supervisore individua le parti
    # sporche e la voce le copre con un BIP. Disattivando la supervisione,
    # Emilio dice l'audio grezzo (nessun bip).
    moderation_enabled: bool = _env_bool("EMILIO_MODERATION", True)
    censor_style: str = os.environ.get("EMILIO_CENSOR_STYLE", "mask")  # mask|bleep|euphemism (resa testuale)
    moderate_input: bool = _env_bool("EMILIO_MODERATE_INPUT", True)
    # Marcatore con cui il bip appare in console/log; cartella dei file BIP
    # (vuota = quelli pacchettizzati in assets/beeps/).
    bip_marker: str = os.environ.get("EMILIO_BIP_MARKER", "[BIP]")
    bip_dir: str | None = os.environ.get("EMILIO_BIP_DIR")

    # --- Voce (TTS) -----------------------------------------------------
    # Profilo voce attivo (vedi speech.default_profiles): mock | offline |
    # veloce | realistico | espressivo. Se non impostato, deriva da EMILIO_TTS.
    voice_profile: str | None = os.environ.get("EMILIO_VOICE")
    # backend "storico" usato come ripiego se EMILIO_VOICE non è impostato.
    tts_backend: str = os.environ.get("EMILIO_TTS", "mock")
    tts_language: str = os.environ.get("EMILIO_TTS_LANG", "it")
    # Voce di sistema per il TTS offline (pyttsx3): id o pezzo di nome.
    # Default "Luca" (maschile it-IT); se non installata si ripiega su una voce
    # italiana vera (es. Alice). Le voci "eloquence" vengono evitate.
    tts_voice: str = os.environ.get("EMILIO_TTS_VOICE", "Luca")
    elevenlabs_api_key: str | None = os.environ.get("ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str = os.environ.get("ELEVENLABS_VOICE_ID", "")
    elevenlabs_model: str = os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")
    # Cartella dove salvare/riprodurre l'audio generato.
    audio_out: str = os.environ.get("EMILIO_AUDIO_OUT", "emilio_voce.mp3")

    # --- Attuatori / movimento -----------------------------------------
    actuator_backend: str = os.environ.get("EMILIO_ACTUATORS", "mock")  # mock|serial
    serial_port: str = os.environ.get("EMILIO_SERIAL_PORT", "/dev/ttyUSB0")
    serial_baud: int = int(os.environ.get("EMILIO_SERIAL_BAUD", "9600"))

    # --- Occhi (LED sul corpo / anteprima locale) ----------------------
    eyes_backend: str = os.environ.get("EMILIO_OCCHI", "mock")  # mock|preview
    eyes_preview_port: int = int(os.environ.get("EMILIO_OCCHI_PORT", "8473"))

    # --- Persona --------------------------------------------------------
    persona_path: str | None = os.environ.get("EMILIO_PERSONA")
