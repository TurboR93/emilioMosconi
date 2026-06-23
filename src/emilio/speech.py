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

import gc
import os
import shutil
import subprocess
import tempfile
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
# Resa: artefatto pronto alla riproduzione (sintesi anticipata / prefetch)
# ---------------------------------------------------------------------------

@dataclass
class Resa:
    """Artefatto prodotto da `Speaker.prepara`, da dare poi a `Speaker.riproduci`.

    Permette di SINTETIZZARE una frase senza riprodurla subito, così la pipeline
    streaming sintetizza la frase successiva mentre la corrente suona (niente
    pause). Tiene una delle tre forme:
      * `path` -> file audio già sintetizzato (con `cleanup` = cartella temporanea
        da rimuovere dopo la riproduzione);
      * `testo` -> testo da stampare (mock);
      * `_say`  -> ripiego (speaker, text, spans, prev): la sintesi+riproduzione
        avviene in `riproduci` chiamando `say` (per i backend senza prefetch).
    """
    backend: str = ""
    profilo: str = ""
    caratteri: int = 0
    ttfb: float | None = None
    synth: float = 0.0                 # tempo di sola sintesi (entra nel totale)
    path: str | None = None            # file audio da riprodurre
    cleanup: str | None = None         # cartella temporanea da rimuovere dopo
    testo: str | None = None           # mock: testo da stampare
    _say: tuple | None = None          # ripiego: (speaker, text, spans, prev)


# ---------------------------------------------------------------------------
# Profilo voce (descrive UNA voce: backend, modello, parametri)
# ---------------------------------------------------------------------------

@dataclass
class VoiceProfile:
    name: str
    backend: str                       # elevenlabs | pyttsx3 | mock
    descrizione: str = ""
    nascosto: bool = False             # non mostrare nei menu interattivi (es. 'mock')
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
        VoiceProfile("mock", "mock", "Stampa soltanto (sviluppo/test)", nascosto=True),
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
        # Voce dedicata alla persona "germano" (vecchio trevigiano incazzato,
        # acido e arguto alla Germano Mosconi): voice_id FISSO (è la sua voce
        # firma, clonata da audio veneto reale, non eredita da ELEVENLABS_VOICE_ID).
        # Multilingual v2 per il realismo italiano, stabilità bassa + style alto per
        # il piglio espressivo/sboccato, un filo più lenta per dargli gravità da
        # vecchio. La persona la attiva da sola (campo "voce").
        VoiceProfile(
            "germano", "elevenlabs",
            "Vecchio trevigiano incazzato, acido e sboccato (Multilingual v2, espressivo)",
            voice_id="uW2tUtSymsTeJDUJjn8E", model="eleven_multilingual_v2",
            streaming=True, optimize_streaming_latency=2,
            stability=0.3, similarity_boost=0.85, style=0.5, speed=0.97,
        ),
    ]


# Modulazione delle impostazioni voce ElevenLabs per stato d'animo: parte dai
# valori del profilo e sovrascrive solo le chiavi presenti, per "recitare"
# l'emozione (voce instabile/enfatica se arrabbiato, più posata se triste...).
# Emozioni assenti -> profilo invariato. Disattivabile con EMILIO_VOCE_EMOZIONE=0.
EMOZIONI_VOCE: dict[str, dict[str, float]] = {
    "arrabbiato": {"stability": 0.2, "style": 0.85},
    "felice":     {"stability": 0.4, "style": 0.55},
    "sorpreso":   {"stability": 0.3, "style": 0.6},
    "triste":     {"stability": 0.75, "style": 0.2, "speed": 0.95},
    "pensa":      {"stability": 0.7, "style": 0.25},
}


# ---------------------------------------------------------------------------
# Speaker
# ---------------------------------------------------------------------------

class Speaker(ABC):
    @abstractmethod
    def say(self, text: str, bleep_spans: list[tuple[int, int]] | None = None,
            previous_text: str = "", next_text: str = "",
            emozione: str = "") -> SpeechMetrics:
        """Pronuncia `text`. Se `bleep_spans` è valorizzato, copre quegli
        intervalli di CARATTERE con un BIP sull'audio (censura amministratore).

        `previous_text`/`next_text` danno al TTS il contesto di ciò che è già
        stato detto / verrà detto: serve nella pipeline streaming perché le frasi
        sintetizzate separatamente mantengano un'intonazione CONTINUA (niente
        salti di tono). `emozione` (stato d'animo) permette ai backend espressivi
        di modulare il tono (vedi EMOZIONI_VOCE). I backend che non li supportano
        li ignorano."""
        ...

    def prepara(self, text: str, bleep_spans: list[tuple[int, int]] | None = None,
                previous_text: str = "", next_text: str = "",
                emozione: str = "") -> "Resa":
        """Sintesi ANTICIPATA: prepara un artefatto pronto SENZA riprodurlo, così
        la pipeline streaming sintetizza la frase successiva mentre quella corrente
        suona (vedi agent.parla_streaming). Default: nessun prefetch — la
        sintesi+riproduzione avviene in `riproduci` via `say`. Gli speaker che sanno
        sintetizzare su file (pyttsx3, elevenlabs) la sovrascrivono."""
        return Resa(_say=(self, text, bleep_spans, previous_text))

    def riproduci(self, resa: "Resa") -> SpeechMetrics:
        """Riproduce (bloccante) un artefatto prodotto da `prepara`. Sicura fuori
        dal thread principale: riproduce un sottoprocesso o stampa, mai sintetizza
        (la sintesi è già avvenuta in `prepara`, salvo il ripiego `_say`)."""
        if resa._say is not None:
            sp, text, spans, prev = resa._say
            return sp.say(text, spans, prev)
        t0 = time.perf_counter()
        if resa.testo is not None:
            print(f"🔊 [Emilio/{resa.profilo}] {resa.testo}")
        elif resa.path:
            if not _play_file(resa.path):
                print(f"🔊 [Emilio] (audio in {resa.path}, nessun player)")
        if resa.cleanup:
            shutil.rmtree(resa.cleanup, ignore_errors=True)
        return SpeechMetrics(resa.backend, resa.profilo, resa.ttfb,
                             resa.synth + (time.perf_counter() - t0), resa.caratteri)


class MockSpeaker(Speaker):
    def __init__(self, profilo: str = "mock", bip_marker: str = "[BIP]"):
        self.profilo = profilo
        self.bip_marker = bip_marker

    def say(self, text: str, bleep_spans: list[tuple[int, int]] | None = None,
            previous_text: str = "", next_text: str = "",
            emozione: str = "") -> SpeechMetrics:
        t0 = time.perf_counter()
        mostrato = (audio_bip.applica_span(text, bleep_spans, self.bip_marker)
                    if bleep_spans else text)
        print(f"🔊 [Emilio/{self.profilo}] {mostrato}")
        return SpeechMetrics("mock", self.profilo, None, time.perf_counter() - t0, len(text))


class Pyttsx3Speaker(Speaker):
    """TTS offline. Engine USA-E-GETTA per ogni battuta.

    Su macOS pyttsx3 (driver `nsss`) ha un bug noto: riusando lo STESSO engine,
    `runAndWait()` parla solo la PRIMA volta e poi torna subito senza dire nulla
    ("Emilio si incastra"). pyttsx3 però cachea l'engine per driver finché ne
    esiste un riferimento vivo, quindi NON teniamo `self._engine`: per ogni
    battuta creiamo un engine nuovo, lo usiamo e lo liberiamo (`gc.collect()`),
    così il successivo `init()` ne restituisce uno fresco che parla davvero.
    """

    def __init__(self, profilo: str = "offline", language: str = "it", voce: str = "",
                 bip_dir: str | None = None):
        import pyttsx3
        self.profilo = profilo
        self.bip_dir = bip_dir
        self._voce = voce
        self._lang = language.lower()
        # Risolve una volta l'id della voce, poi libera l'engine temporaneo.
        eng = pyttsx3.init()
        self._voice_id = self._scegli_voce(eng.getProperty("voices"))
        self._libera(eng)

    def _scegli_voce(self, voci) -> str | None:
        lang = self._lang

        def _blob(v):
            return f"{v.id} {getattr(v, 'name', '')}".lower()

        def _it(v):
            b = _blob(v)
            return f"{lang}-{lang}" in b or f"{lang}_{lang}" in b or "ital" in b

        # 1) voce richiesta esplicitamente (per nome o id, es. "Luca")
        if self._voce:
            scelta = next((v.id for v in voci if self._voce.lower() in _blob(v)), None)
            if scelta:
                return scelta
        # 2) la prima voce della lingua NON "eloquence" (robotiche/incomprensibili)
        scelta = next((v.id for v in voci
                       if _it(v) and "eloquence" not in v.id.lower()), None)
        # 3) estrema ratio: qualunque voce della lingua
        return scelta or next((v.id for v in voci if _it(v)), None)

    def _nuovo_engine(self):
        """Un engine pyttsx3 nuovo (con la voce scelta) — usa-e-getta."""
        import pyttsx3
        eng = pyttsx3.init()
        if self._voice_id:
            eng.setProperty("voice", self._voice_id)
        return eng

    @staticmethod
    def _libera(eng) -> None:
        """Chiude e libera l'engine: il prossimo init() ne crea uno nuovo
        (altrimenti pyttsx3 ridà quello cachato → bug 'parla una volta sola')."""
        try:
            eng.stop()
        except Exception:
            pass
        gc.collect()

    def say(self, text: str, bleep_spans: list[tuple[int, int]] | None = None,
            previous_text: str = "", next_text: str = "",
            emozione: str = "") -> SpeechMetrics:
        # `emozione` ignorata: la voce offline è piatta (l'emozione guida gli occhi).
        t0 = time.perf_counter()
        if bleep_spans and self._say_con_bip(text, bleep_spans):
            return SpeechMetrics("pyttsx3", self.profilo, None,
                                 time.perf_counter() - t0, len(text))
        # Ripiego: se lo splice del bip non è possibile, la parolaccia NON viene
        # comunque pronunciata (sostituita da "bip" parlato).
        da_dire = audio_bip.testo_sicuro(text, bleep_spans) if bleep_spans else text
        eng = self._nuovo_engine()
        eng.say(da_dire)
        eng.runAndWait()
        self._libera(eng)
        return SpeechMetrics("pyttsx3", self.profilo, None, time.perf_counter() - t0, len(text))

    def prepara(self, text: str, bleep_spans: list[tuple[int, int]] | None = None,
                previous_text: str = "", next_text: str = "",
                emozione: str = "") -> Resa:
        """Sintesi anticipata su FILE temporaneo unico (no riproduzione).

        `emozione` ignorata (voce offline piatta). La sintesi pyttsx3 (`runAndWait`)
        resta qui sul thread CHIAMANTE: la
        pipeline streaming la invoca dal main (su macOS pyttsx3 non è thread-safe),
        mentre la sola riproduzione va su un worker. Ritorna l'artefatto pronto."""
        t0 = time.perf_counter()
        if bleep_spans:
            res = self._sintesi_con_bip(text, bleep_spans)
            if res:
                path, tmp = res
                return Resa("pyttsx3", self.profilo, len(text), None,
                            time.perf_counter() - t0, path=path, cleanup=tmp)
            da_dire = audio_bip.testo_sicuro(text, bleep_spans)
        else:
            da_dire = text
        tmp = tempfile.mkdtemp(prefix="emilio_tts_")
        wav = os.path.join(tmp, "voce.wav")
        eng = self._nuovo_engine()                  # engine usa-e-getta
        eng.save_to_file(da_dire, wav)              # un'unica sintesi su file
        eng.runAndWait()
        self._libera(eng)
        if not (os.path.exists(wav) and os.path.getsize(wav) > 0):
            shutil.rmtree(tmp, ignore_errors=True)
            # ripiego: sintesi+riproduzione insieme al momento di `riproduci`
            return Resa("pyttsx3", self.profilo, len(text), None,
                        time.perf_counter() - t0, _say=(self, da_dire, None, ""))
        return Resa("pyttsx3", self.profilo, len(text), None,
                    time.perf_counter() - t0, path=wav, cleanup=tmp)

    def _sintesi_con_bip(self, text: str,
                         spans: list[tuple[int, int]]) -> tuple[str, str] | None:
        """Sintetizza su file e ci sovrappone il BIP, SENZA riprodurre.

        Una SOLA sintesi dell'intera frase (pyttsx3 si rompe se chiamato tante
        volte di fila), poi `ffmpeg` muta e ci sovrappone il bip sugli intervalli
        sporchi. La voce offline non dà i timestamp: si stima la posizione nel
        tempo in proporzione ai caratteri — approssimato ma affidabile (con
        ElevenLabs il timing è invece esatto). Ritorna (file_finale, cartella_temp)
        oppure None: il chiamante riproduce e poi rimuove la cartella.
        """
        beep = audio_bip.scegli_beep(self.bip_dir)
        if not beep or not shutil.which("ffmpeg") or not text.strip() or not spans:
            return None
        tmp = tempfile.mkdtemp(prefix="emilio_bip_")
        ok = False
        try:
            voce = os.path.join(tmp, "voce.wav")
            eng = self._nuovo_engine()              # engine usa-e-getta
            eng.save_to_file(text, voce)            # un'unica sintesi
            eng.runAndWait()
            self._libera(eng)
            if not (os.path.exists(voce) and os.path.getsize(voce) > 0):
                return None
            dur = audio_bip._durata(voce)
            if not dur:
                return None
            # carattere -> tempo, stima uniforme; copre il centro di ogni parolaccia
            n = max(1, len(text))
            intervalli = audio_bip.fondi_intervalli(
                [(a / n * dur, b / n * dur) for a, b in spans])
            out = os.path.join(tmp, "finale.wav")
            if intervalli and audio_bip.applica_bip(voce, intervalli, beep, out):
                ok = True
                return out, tmp
            return None
        finally:
            if not ok:
                shutil.rmtree(tmp, ignore_errors=True)

    def _say_con_bip(self, text: str, spans: list[tuple[int, int]]) -> bool:
        """Voce offline col BIP VERO sul CENTRO delle parolacce: sintetizza e
        riproduce SUBITO (usato da `say`, pipeline a blocco unico). True se ok."""
        res = self._sintesi_con_bip(text, spans)
        if not res:
            return False
        out, tmp = res
        try:
            if not _play_file(out):
                print(f"🔊 [Emilio] (audio bippato in {out}, nessun player)")
            return True
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


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
                 audio_out: str = "emilio_voce.mp3", bip_dir: str | None = None,
                 modula_emozione: bool = True):
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
        self.modula_emozione = modula_emozione

    def _voice_settings(self, emozione: str = "") -> dict:
        """Impostazioni voce del profilo, modulate per stato d'animo (recita)."""
        vs = {
            "stability": self.p.stability,
            "similarity_boost": self.p.similarity_boost,
            "style": self.p.style,
            "speed": self.p.speed,
        }
        if self.modula_emozione and emozione in EMOZIONI_VOCE:
            vs.update(EMOZIONI_VOCE[emozione])      # sovrascrive solo le chiavi presenti
        return vs

    def _payload(self, text: str, previous_text: str = "", next_text: str = "",
                 emozione: str = "") -> dict:
        p = {
            "text": text,
            "model_id": self.p.model,
            "voice_settings": self._voice_settings(emozione),
        }
        # Contesto per un'intonazione CONTINUA fra frasi sintetizzate a parte.
        if previous_text:
            p["previous_text"] = previous_text
        if next_text:
            p["next_text"] = next_text
        return p

    def say(self, text: str, bleep_spans: list[tuple[int, int]] | None = None,
            previous_text: str = "", next_text: str = "",
            emozione: str = "") -> SpeechMetrics:
        if bleep_spans:
            return self._say_censura(text, bleep_spans, previous_text, next_text, emozione)
        return self._say_diretto(text, previous_text, next_text, emozione)

    def _say_diretto(self, text: str, previous_text: str = "",
                     next_text: str = "", emozione: str = "") -> SpeechMetrics:
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
                                   json=self._payload(text, previous_text, next_text, emozione),
                                   stream=True, timeout=30) as r:
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
                             json=self._payload(text, previous_text, next_text, emozione), timeout=30)
        resp.raise_for_status()
        ttfb = time.perf_counter() - t0
        with open(self.audio_out, "wb") as f:
            f.write(resp.content)
        if not _play_file(self.audio_out):
            print(f"🔊 [Emilio] (audio salvato in {self.audio_out}, nessun player)")
        return SpeechMetrics("elevenlabs", self.p.name, ttfb,
                             time.perf_counter() - t0, len(text))

    def _say_censura(self, text: str, bleep_spans: list[tuple[int, int]],
                     previous_text: str = "", next_text: str = "",
                     emozione: str = "") -> SpeechMetrics:
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
        payload = self._payload(text, previous_text, next_text, emozione)
        # Niente normalizzazione del testo: serve un allineamento 1:1 coi
        # caratteri (altrimenti gli offset del moderatore non combaciano).
        payload["apply_text_normalization"] = "off"
        t0 = time.perf_counter()
        try:
            resp = requests.post(url, headers=headers, params=params,
                                 json=payload, timeout=30)
            resp.raise_for_status()
            ttfb = time.perf_counter() - t0
            data = resp.json()
            audio = base64.b64decode(data["audio_base64"])
            align = data.get("alignment") or {}
            chars = align.get("characters") or []
            cs = align.get("character_start_times_seconds") or []
            ce = align.get("character_end_times_seconds") or []
            # L'allineamento DEVE combaciare 1:1 col testo: altrimenti gli offset
            # del moderatore puntano nel posto sbagliato e il bip mancherebbe la
            # parolaccia -> ripiego sicuro (mai turpiloquio in chiaro).
            if not (len(chars) == len(cs) == len(ce) == len(text)):
                raise ValueError("allineamento non 1:1 col testo")

            grezzo = self.audio_out + ".raw"
            with open(grezzo, "wb") as f:
                f.write(audio)

            intervalli = audio_bip.intervalli_da_allineamento(bleep_spans, cs, ce)
            beep = audio_bip.scegli_beep(self.bip_dir)
            if intervalli and audio_bip.applica_bip(grezzo, intervalli, beep, self.audio_out):
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
        return self._say_diretto(audio_bip.testo_sicuro(text, bleep_spans),
                                 previous_text, next_text, emozione)

    # -- Sintesi anticipata (prefetch): sintetizza su FILE, NON riproduce -----

    def prepara(self, text: str, bleep_spans: list[tuple[int, int]] | None = None,
                previous_text: str = "", next_text: str = "",
                emozione: str = "") -> Resa:
        if bleep_spans:
            return self._prepara_censura(text, bleep_spans, previous_text, next_text, emozione)
        return self._prepara_diretto(text, previous_text, next_text, emozione)

    def _prepara_diretto(self, text: str, previous_text: str = "",
                         next_text: str = "", emozione: str = "") -> Resa:
        """Sintesi su file temporaneo UNICO (no riproduzione), per il prefetch.

        Non usa lo streaming-to-player (che fonde sintesi e riproduzione): qui la
        riproduzione avviene dopo, su un altro thread, leggendo questo file."""
        import requests

        headers = {"xi-api-key": self.api_key, "content-type": "application/json"}
        url = self.BASE.format(voice_id=self.p.voice_id)
        params = {"output_format": self.p.output_format}
        t0 = time.perf_counter()
        resp = requests.post(url, headers=headers, params=params,
                             json=self._payload(text, previous_text, next_text, emozione), timeout=30)
        resp.raise_for_status()
        ttfb = time.perf_counter() - t0
        tmp = tempfile.mkdtemp(prefix="emilio_tts_")
        path = os.path.join(tmp, "voce.mp3")
        with open(path, "wb") as f:
            f.write(resp.content)
        return Resa("elevenlabs", self.p.name, len(text), ttfb,
                    time.perf_counter() - t0, path=path, cleanup=tmp)

    def _prepara_censura(self, text: str, bleep_spans: list[tuple[int, int]],
                         previous_text: str = "", next_text: str = "",
                         emozione: str = "") -> Resa:
        """Come `_say_censura` ma scrive l'audio bippato su file temporaneo UNICO
        e NON lo riproduce (per il prefetch). Ripiego sicuro: testo con 'bip'."""
        import base64
        import requests

        headers = {"xi-api-key": self.api_key, "content-type": "application/json"}
        url = self.BASE.format(voice_id=self.p.voice_id) + "/with-timestamps"
        params = {"output_format": self.p.output_format}
        payload = self._payload(text, previous_text, next_text, emozione)
        payload["apply_text_normalization"] = "off"
        t0 = time.perf_counter()
        try:
            resp = requests.post(url, headers=headers, params=params,
                                 json=payload, timeout=30)
            resp.raise_for_status()
            ttfb = time.perf_counter() - t0
            data = resp.json()
            audio = base64.b64decode(data["audio_base64"])
            align = data.get("alignment") or {}
            chars = align.get("characters") or []
            cs = align.get("character_start_times_seconds") or []
            ce = align.get("character_end_times_seconds") or []
            if not (len(chars) == len(cs) == len(ce) == len(text)):
                raise ValueError("allineamento non 1:1 col testo")
            tmp = tempfile.mkdtemp(prefix="emilio_bip_")
            grezzo = os.path.join(tmp, "voce.mp3")
            with open(grezzo, "wb") as f:
                f.write(audio)
            intervalli = audio_bip.intervalli_da_allineamento(bleep_spans, cs, ce)
            beep = audio_bip.scegli_beep(self.bip_dir)
            out = os.path.join(tmp, "finale.mp3")
            if intervalli and audio_bip.applica_bip(grezzo, intervalli, beep, out):
                try:
                    os.remove(grezzo)
                except OSError:
                    pass
                return Resa("elevenlabs", self.p.name, len(text), ttfb,
                            time.perf_counter() - t0, path=out, cleanup=tmp)
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception as e:  # pragma: no cover - dipende dalla rete/ffmpeg
            print(f"⚠️  Bip audio non riuscito ({e}); ripiego sicuro senza turpiloquio.")
        return self._prepara_diretto(audio_bip.testo_sicuro(text, bleep_spans),
                                     previous_text, next_text, emozione)


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
                modula_emozione=getattr(self.config, "voce_emozione", True),
            )
        if p.backend == "pyttsx3":
            return Pyttsx3Speaker(profilo=p.name, language=self.config.tts_language,
                                  voce=getattr(self.config, "tts_voice", ""),
                                  bip_dir=getattr(self.config, "bip_dir", None))
        return MockSpeaker(profilo=p.name,
                           bip_marker=getattr(self.config, "bip_marker", "[BIP]"))

    def say(self, text: str, bleep_spans: list[tuple[int, int]] | None = None,
            previous_text: str = "", next_text: str = "",
            emozione: str = "") -> SpeechMetrics:
        return self.speaker.say(text, bleep_spans, previous_text, next_text, emozione)

    def prepara(self, text: str, bleep_spans: list[tuple[int, int]] | None = None,
                previous_text: str = "", next_text: str = "",
                emozione: str = "") -> Resa:
        """Sintesi anticipata (prefetch): vedi Speaker.prepara."""
        return self.speaker.prepara(text, bleep_spans, previous_text, next_text, emozione)

    def riproduci(self, resa: Resa) -> SpeechMetrics:
        """Riproduce un artefatto preparato: vedi Speaker.riproduci."""
        return self.speaker.riproduci(resa)


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
