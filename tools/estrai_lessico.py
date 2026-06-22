#!/usr/bin/env python3
"""Estrae vocabolario candidato per Emilio da un export di chat WhatsApp.

NON è uno scraper: legge il file `.txt` prodotto dall'**esportazione ufficiale**
di WhatsApp (Impostazioni chat → Esporta chat → Senza media). Da quel testo:

  * butta via nomi mittenti, orari, numeri, URL e segnaposto media (PRIVACY:
    nessun dato personale entra nell'output, solo parole e loro frequenza);
  * conta le parole e i modi di dire (n-grammi) più ricorrenti;
  * segnala le **bestemmie nuove** (entità divina + parola) NON ancora coperte
    dal supervisore, da aggiungere a `lexicon.py`;
  * raccoglie possibili **versi/onomatopee** (rutti, scoregge, risate) per dare
    colore alla persona.

L'output è un report di SOLI termini+conteggi, da rivedere a mano: le parole
buone si copiano poi nel lessico. L'export grezzo e il report restano in `data/`
(ignorata da git): nel repo pubblico finisce solo il vocabolario curato.

Uso:
    python tools/estrai_lessico.py data/whatsapp/_chat.txt
    python tools/estrai_lessico.py data/whatsapp/_chat.txt --top 100 -o data/whatsapp/lessico.txt
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter

# Lo strumento usa il supervisore già pronto (richiede `pip install -e .`).
try:
    from emilio.moderation import default_moderator
    from emilio.moderation.lexicon import BLASPHEMY_DIVINE
except ImportError:
    sys.stderr.write(
        "Manca il pacchetto 'emilio'. Esegui prima:  pip install -e .\n")
    raise SystemExit(1)


# --- formati di riga dell'export WhatsApp (iOS e Android) ------------------
# iOS:     [28/06/24, 14:35:12] Mario Rossi: messaggio
# Android: 28/06/24, 14:35 - Mario Rossi: messaggio
_RE_IOS = re.compile(r"^\[(?P<dt>[^\]]+)\]\s*(?P<resto>.*)$")
_RE_ANDROID = re.compile(
    r"^(?P<dt>\d{1,2}[/.]\d{1,2}[/.]\d{2,4},?\s+\d{1,2}:\d{2}(?::\d{2})?"
    r"(?:\s*[APap]\.?[Mm]\.?)?)\s+-\s+(?P<resto>.*)$")

# Robaccia da ripulire dentro ai messaggi.
_RE_URL = re.compile(r"https?://\S+|www\.\S+")
_RE_NUM = re.compile(r"\+?\d[\d\s().-]{5,}\d")        # numeri di telefono
_RE_MENTION = re.compile(r"@\S+")
_MEDIA = (
    "<media omessi>", "<media omitted>", "immagine omessa", "video omesso",
    "audio omesso", "gif omessa", "sticker omesso", "documento omesso",
    "‎immagine omessa", "questo messaggio è stato eliminato",
    "messaggio eliminato", "null",
)

# Parola: lettere italiane (con accenti) e apostrofo interno (va', l'ostia).
_RE_PAROLA = re.compile(r"[a-zàèéìòùáíóúü][a-zàèéìòùáíóúü']*[a-zàèéìòùáíóúü]|[a-zàèéìòùáíóúü]")

# Onomatopee/versi: 3+ lettere uguali di fila (braaap, prrr, ahahah, puzzz).
_RE_VERSO = re.compile(r"(.)\1{2,}")

# Stopword italiane (parole comunissime da escludere dalle classifiche).
_STOP = set("""
a ad ai al all alla alle allo agli anche ancora avere aveva avevo c c' che chi
ci co coi col come con cosa cui da dai dal dall dalla dalle dallo degli dei del
dell della delle dello di do dopo dove e è ecco ed era erano essere fa fare
fatto fra gli ha hai hanno ho i il in io l l' la le lei li lo loro lui ma mai me
mi mia mie miei mio molto ne né nei nel nell nella nelle nello no noi non
nostro o od ogni oh ok per perché perche piu più po po' poco poi qua qual quale
quando quanto quel quella quelle quelli quello questa queste questi questo qui
sarà se sei senza si sì sia siamo sono sopra sotto sta stai stanno state stato
su sua sue sui sul sull sulla sulle suo te ti tra troppo tu tua tue tuo tutta
tutti tutto un un' una uno va vai voi vostro
""".split())


def parse_messaggi(path: str) -> list[str]:
    """Legge l'export e ritorna SOLO i testi dei messaggi (niente mittenti)."""
    messaggi: list[str] = []
    corrente: list[str] = []

    def _chiudi():
        if corrente:
            messaggi.append(" ".join(corrente).strip())
            corrente.clear()

    with open(path, encoding="utf-8", errors="ignore") as f:
        for raw in f:
            riga = raw.replace("‎", "").replace("‏", "").rstrip("\n")
            m = _RE_IOS.match(riga) or _RE_ANDROID.match(riga)
            if m:
                _chiudi()
                resto = m.group("resto")
                # "Mittente: testo" -> tieni solo "testo" (scarta i messaggi di
                # sistema, che non hanno la forma "nome: testo").
                if ":" in resto:
                    _, _, testo = resto.partition(":")
                    corrente.append(testo.strip())
                # else: riga di sistema -> ignora
            elif corrente:
                corrente.append(riga.strip())   # continuazione multilinea
    _chiudi()
    return messaggi


def pulisci(testo: str) -> str:
    t = testo.lower()
    if t.strip() in _MEDIA or any(t.strip() == m for m in _MEDIA):
        return ""
    t = _RE_URL.sub(" ", t)
    t = _RE_NUM.sub(" ", t)
    t = _RE_MENTION.sub(" ", t)
    for m in _MEDIA:
        t = t.replace(m, " ")
    return t


def tokenizza(testo: str) -> list[str]:
    return _RE_PAROLA.findall(testo)


def ngrammi(tokens: list[str], n: int) -> list[str]:
    return [" ".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


def scrivi_classifica(out, titolo: str, coppie, soglia: int = 2) -> None:
    out.write(f"\n## {titolo}\n")
    for termine, c in coppie:
        if c < soglia:
            break
        out.write(f"  {c:>5}  {termine}\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Estrai vocabolario da export WhatsApp.")
    ap.add_argument("export", help="file _chat.txt esportato da WhatsApp")
    ap.add_argument("--top", type=int, default=80, help="quanti termini per classifica")
    ap.add_argument("-o", "--out", default=None, help="file di report (default accanto all'export)")
    args = ap.parse_args(argv)

    if not os.path.exists(args.export):
        sys.stderr.write(f"File non trovato: {args.export}\n")
        return 1

    messaggi = parse_messaggi(args.export)
    uni, bi, tri, versi = Counter(), Counter(), Counter(), Counter()
    sporchi = 0
    bestemmie_nuove = Counter()

    for msg in messaggi:
        t = pulisci(msg)
        if not t.strip():
            continue
        rep = default_moderator.review(t)
        if rep.has_profanity or rep.has_blasphemy:
            sporchi += 1
        tok = tokenizza(t)
        uni.update(w for w in tok if w not in _STOP and len(w) > 2)
        for w in tok:
            if _RE_VERSO.search(w):
                versi[w] += 1
        b = ngrammi(tok, 2)
        tr = ngrammi(tok, 3)
        bi.update(b)
        tri.update(tr)
        # bestemmie candidate: n-grammi con un'entità divina + parole "piene"
        # (niente stopword/filler) che il supervisore NON segnala ancora come
        # bestemmia -> probabile combo nuova da aggiungere a lexicon.py
        for ng in b + tr:
            parole = ng.split()
            if not any(p in BLASPHEMY_DIVINE for p in parole):
                continue
            altri = [p for p in parole if p not in BLASPHEMY_DIVINE]
            if not altri or any(p in _STOP or len(p) <= 2 for p in altri):
                continue
            if not default_moderator.review(ng).has_blasphemy:
                bestemmie_nuove[ng] += 1

    dest = args.out or (os.path.splitext(args.export)[0] + "_lessico.txt")
    with open(dest, "w", encoding="utf-8") as out:
        out.write("# Vocabolario candidato per Emilio (da export WhatsApp)\n")
        out.write("# Solo termini + frequenza. Niente nomi/numeri/messaggi interi.\n")
        out.write(f"\n## Statistiche\n")
        out.write(f"  messaggi analizzati : {len(messaggi)}\n")
        out.write(f"  con turpiloquio     : {sporchi} "
                  f"({100*sporchi//max(1,len(messaggi))}%)\n")
        scrivi_classifica(out, f"BESTEMMIE NUOVE da aggiungere a lexicon.py (top {args.top})",
                          bestemmie_nuove.most_common(args.top), soglia=1)
        scrivi_classifica(out, f"Versi/onomatopee — rutti, scoregge, risate (top {args.top})",
                          versi.most_common(args.top), soglia=1)
        scrivi_classifica(out, f"Parole più frequenti (top {args.top})",
                          uni.most_common(args.top), soglia=3)
        scrivi_classifica(out, f"Modi di dire — bigrammi (top {args.top})",
                          bi.most_common(args.top), soglia=3)
        scrivi_classifica(out, f"Modi di dire — trigrammi (top {args.top})",
                          tri.most_common(args.top), soglia=3)

    print(f"✅ {len(messaggi)} messaggi analizzati ({sporchi} con turpiloquio).")
    print(f"📄 Report scritto in: {dest}")
    print("   Rivedilo e copia le parole buone in src/emilio/moderation/lexicon.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
