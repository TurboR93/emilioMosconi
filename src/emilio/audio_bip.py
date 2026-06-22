"""Censura audio di Emilio: copre le parolacce/bestemmie con un BIP.

Modello (deciso col committente):
  * il cervello dice la sua battuta naturale (nessuna riformulazione dell'LLM);
  * il supervisore individua gli intervalli "sporchi" come offset di CARATTERE
    nel testo (vedi `moderation/`);
  * qui mappiamo quegli offset su intervalli di TEMPO nell'audio sintetizzato
    (usando l'allineamento carattere→tempo della voce) e li copriamo con un
    file **BIP** scelto (a caso) da una lista — per ora il classico bip in
    `assets/beeps/`. Tutta l'elaborazione audio passa da **ffmpeg**.

La censura è DISATTIVABILE dall'amministratore: se la supervisione è spenta non
arrivano span da bippare e questo modulo non viene nemmeno invocato.

Le funzioni "di logica" (mappatura span→tempo, sostituzioni testuali, costruzione
del filtro) sono pure e testabili offline, senza audio reale.
"""

from __future__ import annotations

import random
import shutil
import subprocess
from pathlib import Path

# Cartella dei BIP pacchettizzati col modulo.
BEEPS_DIR = Path(__file__).resolve().parent / "assets" / "beeps"

_ESTENSIONI_AUDIO = (".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aiff")


# ---------------------------------------------------------------------------
# Scelta del BIP (lista → per ora un solo file classico)
# ---------------------------------------------------------------------------

def beep_disponibili(directory: str | Path | None = None) -> list[Path]:
    d = Path(directory) if directory else BEEPS_DIR
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir()
                  if p.is_file() and p.suffix.lower() in _ESTENSIONI_AUDIO)


def scegli_beep(directory: str | Path | None = None,
                rng: random.Random | None = None) -> Path | None:
    """Sceglie un BIP dalla lista (a caso). Oggi la lista ha un solo file."""
    files = beep_disponibili(directory)
    if not files:
        return None
    return (rng or random).choice(files)


# ---------------------------------------------------------------------------
# Logica: span di caratteri → intervalli di tempo
# ---------------------------------------------------------------------------

def intervalli_da_allineamento(
    span: list[tuple[int, int]],
    char_start: list[float],
    char_end: list[float],
) -> list[tuple[float, float]]:
    """Mappa span di CARATTERI `(start, end)` su intervalli di TEMPO `(t0, t1)`.

    `char_start`/`char_end` sono gli array di tempi per-carattere (in secondi)
    restituiti dalla voce con timestamp (ElevenLabs with-timestamps). Gli
    intervalli risultanti vengono ordinati e fusi se contigui/sovrapposti.
    """
    n = min(len(char_start), len(char_end))
    intervalli: list[tuple[float, float]] = []
    for a, b in span:
        a = max(0, a)
        b = min(b, n)
        if b <= a:
            continue
        t0 = float(char_start[a])
        t1 = float(char_end[b - 1])
        if t1 > t0:
            intervalli.append((t0, t1))
    return fondi_intervalli(intervalli)


def fondi_intervalli(intervalli: list[tuple[float, float]],
                     tolleranza: float = 0.02) -> list[tuple[float, float]]:
    if not intervalli:
        return []
    ordinati = sorted(intervalli)
    out = [list(ordinati[0])]
    for t0, t1 in ordinati[1:]:
        if t0 <= out[-1][1] + tolleranza:
            out[-1][1] = max(out[-1][1], t1)
        else:
            out.append([t0, t1])
    return [(a, b) for a, b in out]


# ---------------------------------------------------------------------------
# Logica: sostituzioni testuali (per display e per il ripiego "sicuro")
# ---------------------------------------------------------------------------

def applica_span(testo: str, span: list[tuple[int, int]], sostituto: str) -> str:
    """Sostituisce ogni intervallo di caratteri con `sostituto` (da destra)."""
    out = testo
    for a, b in sorted(span, key=lambda s: s[0], reverse=True):
        a = max(0, a)
        b = min(b, len(out))
        if b <= a:
            continue
        out = out[:a] + sostituto + out[b:]
    return out


def testo_sicuro(testo: str, span: list[tuple[int, int]], parola: str = "bip") -> str:
    """Versione del testo SENZA turpiloquio (parolaccia → 'bip' pronunciato).

    Usata come ripiego: se per qualsiasi motivo non riusciamo a bippare l'audio,
    risintetizziamo questa versione, così la parolaccia non viene mai udita.
    """
    return applica_span(testo, span, f" {parola} ")


# ---------------------------------------------------------------------------
# ffmpeg: muta gli intervalli "sporchi" e ci sovrappone il BIP
# ---------------------------------------------------------------------------

def costruisci_filtro(intervalli: list[tuple[float, float]],
                      idx_beep: int = 1) -> str | None:
    """filter_complex ffmpeg: muta l'audio principale negli intervalli e
    ci sovrappone il BIP (ripetuto/troncato alla durata della parola)."""
    if not intervalli:
        return None
    mute = ",".join(
        f"volume=enable='between(t,{t0:.3f},{t1:.3f})':volume=0"
        for t0, t1 in intervalli
    )
    parti = [f"[0:a]{mute}[main]"]
    n = len(intervalli)
    parti.append(f"[{idx_beep}:a]asplit={n}" + "".join(f"[b{i}]" for i in range(n)))
    etichette = ["[main]"]
    for i, (t0, t1) in enumerate(intervalli):
        dur = max(0.05, t1 - t0)
        delay = int(round(t0 * 1000))
        fade_out = max(0.0, dur - 0.02)
        parti.append(
            f"[b{i}]atrim=duration={dur:.3f},"
            f"afade=t=in:st=0:d=0.01,afade=t=out:st={fade_out:.3f}:d=0.02,"
            f"adelay={delay}|{delay}[d{i}]"
        )
        etichette.append(f"[d{i}]")
    parti.append("".join(etichette) + f"amix=inputs={n + 1}:normalize=0[out]")
    return ";".join(parti)


def _durata(path: str | Path) -> float | None:
    """Durata in secondi di un file audio (via ffprobe), o None se ignota."""
    if not shutil.which("ffprobe"):
        return None
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=10,
        )
        return float(r.stdout.strip())
    except Exception:
        return None


def applica_bip(audio_in: str | Path,
                intervalli: list[tuple[float, float]],
                beep_path: str | Path | None,
                audio_out: str | Path) -> bool:
    """Sovrappone il BIP sugli intervalli dell'audio. True se va a buon fine.

    Il BIP viene messo in loop (`-stream_loop`) e troncato alla durata di ogni
    parola, così copre per intero anche le parole più lunghe del file bip.
    Se un intervallo cade FUORI dalla durata reale dell'audio (allineamento
    sballato), fallisce di proposito: meglio il ripiego sicuro che un bip a
    vuoto con la parolaccia udibile.
    """
    if not intervalli or not beep_path:
        return False
    if not shutil.which("ffmpeg"):
        return False
    # Validazione: intervalli monotoni e dentro la durata reale dell'audio.
    dur = _durata(audio_in)
    for t0, t1 in intervalli:
        if t0 < 0 or t1 <= t0 or (dur is not None and t1 > dur + 0.05):
            return False
    filtro = costruisci_filtro(intervalli, idx_beep=1)
    if not filtro:
        return False
    cmd = [
        "ffmpeg", "-y",
        "-i", str(audio_in),
        "-stream_loop", "-1", "-i", str(beep_path),
        "-filter_complex", filtro,
        "-map", "[out]",
        str(audio_out),
    ]
    try:
        r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return r.returncode == 0 and Path(audio_out).exists()
    except Exception:
        return False
