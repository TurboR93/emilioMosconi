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
    # Modello del CERVELLO Claude (specifico, coerente con EMILIO_LOCAL_MODEL /
    # EMILIO_CLOUD_MODEL / EMILIO_STT_MODEL). `EMILIO_MODEL` resta come ALIAS
    # DEPRECATO per retrocompatibilità. Default Haiku: il più rapido (TTFT basso
    # per la voce dal vivo) ed economico; /modello-llm passa a sonnet/opus.
    claude_model: str = (os.environ.get("EMILIO_CLAUDE_MODEL")
                         or os.environ.get("EMILIO_MODEL", "claude-haiku-4-5"))
    # Risposte BREVI: meno token = generazione più rapida e meno crediti voce
    # (ElevenLabs fattura a carattere). 220 basta per una o due battute.
    max_tokens: int = int(os.environ.get("EMILIO_MAX_TOKENS", "220"))
    effort: str = os.environ.get("EMILIO_EFFORT", "medium")  # low|medium|high
    # "Thinking" di Claude: di default SPENTO (bassa latenza per la voce dal vivo,
    # e compatibile con Haiku dove 'effort' darebbe errore). "adaptive" lo accende
    # (con effort) per più qualità su Opus/Sonnet. Vedi ClaudeBrain.
    claude_think: str = os.environ.get("EMILIO_CLAUDE_THINK", "")  # ""/off | adaptive
    # Backend del cervello: mock | claude | local | cloud. Se vuoto, EMILIO_USE_LLM=1
    # equivale a "claude" (retrocompatibilità), altrimenti "mock".
    llm_backend: str = os.environ.get("EMILIO_LLM", "")
    # LLM locale via Ollama (API nativa) sul Mac. think=False evita il
    # "ragionamento" lento dei modelli come Gemma 4 (latenza ~30s -> pochi s).
    local_llm_url: str = os.environ.get("EMILIO_LOCAL_URL", "http://localhost:11434")
    local_llm_model: str = os.environ.get("EMILIO_LOCAL_MODEL", "gemma4:12b")
    local_llm_think: bool = _env_bool("EMILIO_LOCAL_THINK", False)
    local_llm_key: str = os.environ.get("EMILIO_LOCAL_KEY", "")
    # Quanto Ollama tiene il modello caricato in RAM dopo una risposta. Di
    # default lo scarica dopo 5 min: col dialogo dal vivo conviene tenerlo caldo
    # ("30m", oppure "-1" = per sempre) così non si paga il reload a ogni pausa.
    local_llm_keep_alive: str = os.environ.get("EMILIO_LOCAL_KEEP_ALIVE", "30m")
    # Campionamento del modello locale: temperatura (varietà) e penalità di
    # ripetizione (evita che un modello piccolo pappagalli lo stesso moccolo).
    local_llm_temp: float = float(os.environ.get("EMILIO_LOCAL_TEMP", "0.85"))
    local_llm_repeat_penalty: float = float(os.environ.get("EMILIO_LOCAL_REPEAT_PENALTY", "1.3"))
    # LLM cloud generico via API OpenAI-compatibile (/v1/chat/completions): Groq,
    # OpenRouter, OpenAI, vLLM... Per la LATENZA MINIMA con modelli open (es. Groq).
    # Default: Groq. Imposta la chiave del provider in EMILIO_CLOUD_KEY.
    cloud_llm_url: str = os.environ.get("EMILIO_CLOUD_URL", "https://api.groq.com/openai/v1")
    cloud_llm_model: str = os.environ.get("EMILIO_CLOUD_MODEL", "llama-3.3-70b-versatile")
    cloud_llm_key: str = os.environ.get("EMILIO_CLOUD_KEY", "")
    cloud_llm_temp: float = float(os.environ.get("EMILIO_CLOUD_TEMP", "0.85"))
    # Pipeline del parlato: streaming (Emilio parla la PRIMA frase appena pronta,
    # mentre l'LLM genera ancora -> latenza percepita molto più bassa) oppure la
    # vecchia "a blocco unico" (genera tutto, poi parla). Scelta all'avvio:
    # EMILIO_STREAMING=0 per tornare alla vecchia. Anche da runtime: /streaming.
    streaming: bool = _env_bool("EMILIO_STREAMING", True)
    # Modalità monitor della console: mostra in tempo reale (💬) il testo che
    # Emilio sta per dire, frase per frase. ON di default; EMILIO_VERBOSO=0 per
    # spegnerla all'avvio, oppure /verboso off a runtime.
    verboso: bool = _env_bool("EMILIO_VERBOSO", True)

    # --- Supervisione / censura (BIP sull'audio) -----------------------
    # Attivabile/disattivabile dall'amministratore (anche a runtime).
    # Modello: il cervello NON riformula; il supervisore individua le parti
    # sporche e la voce le copre con un BIP. Disattivando la supervisione,
    # Emilio dice l'audio grezzo (nessun bip).
    moderation_enabled: bool = _env_bool("EMILIO_MODERATION", True)
    censor_style: str = os.environ.get("EMILIO_CENSOR_STYLE", "mask")  # mask|bleep|euphemism (resa testuale)
    moderate_input: bool = _env_bool("EMILIO_MODERATE_INPUT", True)
    # Bippa SOLO le bestemmie (religiose), non le parolacce: Emilio può dire
    # parolacce in chiaro, mentre le bestemmie restano coperte dal BIP. Le
    # parolacce vengono comunque rilevate (log, stato d'animo), solo non bippate.
    censura_solo_bestemmie: bool = _env_bool("EMILIO_BIP_SOLO_BESTEMMIE", True)
    # Marcatore con cui il bip appare in console/log; cartella dei file BIP
    # (vuota = quelli pacchettizzati in assets/beeps/).
    bip_marker: str = os.environ.get("EMILIO_BIP_MARKER", "[BIP]")
    bip_dir: str | None = os.environ.get("EMILIO_BIP_DIR")

    # --- Voce (TTS) -----------------------------------------------------
    # Profilo voce attivo (vedi speech.default_profiles): mock | offline |
    # veloce | realistico | espressivo | germano. Se non impostato, deriva da
    # EMILIO_TTS. Una persona può imporre la sua voce (campo Persona.voce): la
    # selezione della persona attiva quella voce, salvo pin esplicito EMILIO_VOICE.
    voice_profile: str | None = os.environ.get("EMILIO_VOICE")
    # backend "storico" usato come ripiego se EMILIO_VOICE non è impostato.
    tts_backend: str = os.environ.get("EMILIO_TTS", "mock")
    tts_language: str = os.environ.get("EMILIO_TTS_LANG", "it")
    # Voce di sistema per il TTS offline (pyttsx3): id o pezzo di nome.
    # Default "Luca" (maschile it-IT); se non installata si ripiega su una voce
    # italiana vera (es. Alice). Le voci "eloquence" vengono evitate.
    tts_voice: str = os.environ.get("EMILIO_TTS_VOICE", "Luca")
    elevenlabs_api_key: str | None = os.environ.get("ELEVENLABS_API_KEY")
    # Default per i test: "Adam", voce premade maschile usabile anche col piano
    # Free via API (le voci della Library richiedono un piano a pagamento).
    # Sostituisci con la TUA voce italiana via ELEVENLABS_VOICE_ID (piano $5+).
    elevenlabs_voice_id: str = os.environ.get("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")
    elevenlabs_model: str = os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")
    # La voce ElevenLabs modula il TONO in base allo stato d'animo (EMOZIONI_VOCE):
    # arrabbiato più instabile/enfatico, triste più posato... Metti a 0 per un tono
    # fisso da profilo. La voce offline resta comunque piatta.
    voce_emozione: bool = _env_bool("EMILIO_VOCE_EMOZIONE", True)
    # Cartella dove salvare/riprodurre l'audio generato.
    audio_out: str = os.environ.get("EMILIO_AUDIO_OUT", "emilio_voce.mp3")

    # --- Attuatori / movimento -----------------------------------------
    actuator_backend: str = os.environ.get("EMILIO_ACTUATORS", "mock")  # mock|serial
    serial_port: str = os.environ.get("EMILIO_SERIAL_PORT", "/dev/ttyUSB0")
    serial_baud: int = int(os.environ.get("EMILIO_SERIAL_BAUD", "9600"))

    # --- Occhi (LED sul corpo / anteprima locale) ----------------------
    eyes_backend: str = os.environ.get("EMILIO_OCCHI", "mock")  # mock|preview
    eyes_preview_port: int = int(os.environ.get("EMILIO_OCCHI_PORT", "8473"))

    # --- Ascolto (STT / microfono) -------------------------------------
    # Per parlare a Emilio a voce. mock = frase fissa (test); whisper = microfono
    # reale + faster-whisper (offline, italiano) sul Mac.
    # mock | whisper (faster-whisper, CPU) | mlx (faster-whisper-mlx su GPU/ANE
    # Apple Silicon: molto più rapido sul Mac).
    stt_backend: str = os.environ.get("EMILIO_ASCOLTO", "mock")  # mock|whisper|mlx
    stt_model: str = os.environ.get("EMILIO_STT_MODEL", "base")  # tiny|base|small|medium
    stt_lingua: str = os.environ.get("EMILIO_STT_LANG", "it")
    stt_compute: str = os.environ.get("EMILIO_STT_COMPUTE", "int8")  # int8|int8_float32|float32
    mic_device: str = os.environ.get("EMILIO_MIC_DEVICE", "")    # indice avfoundation; vuoto=auto
    stt_secondi: float = float(os.environ.get("EMILIO_STT_SECONDI", "5"))
    # Endpointing: invece di registrare N secondi fissi, smette quando smetti di
    # parlare (VAD a energia, via sounddevice). EMILIO_STT_VAD=0 -> torna ai
    # secondi fissi. stt_max = tetto massimo; stt_silenzio = quanta pausa serve.
    stt_vad: bool = _env_bool("EMILIO_STT_VAD", True)
    stt_max: float = float(os.environ.get("EMILIO_STT_MAX", "12"))
    stt_silenzio: float = float(os.environ.get("EMILIO_STT_SILENZIO", "0.8"))

    # --- Persona --------------------------------------------------------
    persona_path: str | None = os.environ.get("EMILIO_PERSONA")
