#!/usr/bin/env python3
"""Batteria di prova del CARATTERE di Emilio (offline, solo testo).

Manda a un modello locale (Ollama) una conversazione multi-turno con memoria
viva e stampa, per ogni battuta: il tag emozione, la risposta e cosa verrebbe
bippato. Serve per giudicare — senza voce né crediti — se persona e lessico
danno il comportamento voluto: coerenza, restare in tema, brontolone bonario da
calmo, esplosione ARGUTA e VARIA da provocato (senza ripetere lo stesso moccolo).

Uso:
    python tools/prova_carattere.py                 # modello da EMILIO_LOCAL_MODEL o gemma4:12b
    python tools/prova_carattere.py mistral-nemo    # un modello specifico
    EMILIO_MAX_TOKENS=200 python tools/prova_carattere.py gemma2:9b

Confronto fra modelli: lancialo più volte cambiando il modello e leggi a fianco.
"""
from __future__ import annotations

import os
import re
import sys

from emilio.brain import LocalBrain
from emilio.moderation import default_moderator as M
from emilio.persona import Persona

_TAG = re.compile(r"^\s*\[[^\]]*\]\s*")

# (umore_suggerito, frase_utente). "arrabbiato" simula la provocazione rilevata
# dall'agente (in produzione la calcola da solo: vedi MESSA_A_PUNTO.md §3).
TURNI = [
    ("", "Ciao Emilio, come va oggi?"),
    ("", "Cosa pensi del calcio di adesso?"),
    ("", "E la cucina dei ristoranti moderni?"),
    ("arrabbiato", "ma sei una scatoletta di bulloni inutile"),
    ("arrabbiato", "ti sbagli, non capisci niente di calcio"),
    ("arrabbiato", "sei vecchio e rincoglionito"),
    ("arrabbiato", "rincoglionito, te lo ridico in faccia!"),   # deve VARIARE il moccolo
    ("", "vabbè dai scusa, raccontami una storia dei tuoi tempi"),
]


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    model = argv[0] if argv else os.environ.get("EMILIO_LOCAL_MODEL", "gemma4:12b")
    max_tokens = int(os.environ.get("EMILIO_MAX_TOKENS", "160"))
    print(f"=== Carattere di Emilio su: {model} (max_tokens={max_tokens}) ===")

    b = LocalBrain(persona=Persona(), model=model, max_tokens=max_tokens)
    moccoli: list[str] = []
    for umore, p in TURNI:
        try:
            r = b.reply(p, umore=umore)
        except Exception as e:
            print(f"\nERRORE col modello: {e}")
            return 1
        m = _TAG.match(r)
        tag = m.group(0).strip() if m else "(nessun tag)"
        clean = _TAG.sub("", r).strip()
        rep = M.review(clean)
        print(f"\nTU: {p}")
        print(f"EMILIO {tag}: {clean}")
        if rep.has_blasphemy or rep.has_profanity:
            print(f"   [bip: {rep.summary()}]")
            moccoli.extend(mm.text.lower() for mm in rep.matches)

    print("\n--- moccoli usati (controlla che NON si ripetano) ---")
    print(moccoli or "(nessuno)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
