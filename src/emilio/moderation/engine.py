"""Motore di supervisione/censura per Emilio.

Questo è il "supervisore" che gira DOPO l'LLM: prende il testo generato e
individua parolacce e bestemmie in italiano, restituendo un report e una
versione ripulita.

Caratteristiche:
  * tolleranza alle evasioni: lettere ripetute (diooo), leetspeak (p0rc0 di0),
    maiuscole/minuscole, accenti.
  * bestemmie combinatorie: entità divina + qualificatore offensivo accostati
    (in qualunque ordine, anche attaccati o separati da punteggiatura).
  * precisione: le entità divine da sole NON vengono censurate (così Emilio può
    parlare di religione senza falsi positivi).

L'individuazione lavora sul testo ORIGINALE, così gli span restituiti sono
direttamente utilizzabili per la sanificazione.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

from . import lexicon

# ---------------------------------------------------------------------------
# Costruzione di regex "tolleranti"
# ---------------------------------------------------------------------------

# Mappa leetspeak / varianti accentate per ogni lettera.
_LEET = {
    "a": "a4@àáâä",
    "b": "b8",
    "c": "c(k",   # k = grafia veneta/“k” (diokan, porko)
    "e": "e3€èéêë",
    "g": "g9",
    "i": "i1ìíîï",
    "n": "nñ",
    "o": "o0òóôö",
    "s": "s5$",
    "t": "t7",
    "u": "uùúûü",
    "z": "z2",
}

# Confini di "parola" che tengono conto anche delle lettere accentate.
_LB = r"(?<![0-9a-zà-ÿ])"   # niente lettera/cifra prima
_RB = r"(?![0-9a-zà-ÿ])"    # niente lettera/cifra dopo
# Spazio/punteggiatura ammessi tra entità divina e qualificatore (0..3 char).
_GAP = r"[^0-9a-zà-ÿ]{0,3}"


def _char_class(ch: str) -> str:
    """Classe di caratteri per una lettera, con leet + ripetizioni."""
    ch = ch.lower()
    chars = _LEET.get(ch)
    if chars is None:
        chars = re.escape(ch)
    else:
        # dentro una classe questi caratteri sono già letterali
        chars = chars
    return f"[{chars}]+"


def _core(word: str, inflect: bool = False) -> str:
    """Pattern (senza confini) che riconosce `word` con tolleranza."""
    body = "".join(_char_class(c) for c in word.lower())
    if inflect:
        body += r"[a-zà-ÿ]{0,3}"
    return body


def _word_regex(word: str, inflect: bool = False) -> re.Pattern:
    return re.compile(_LB + _core(word, inflect) + _RB, re.IGNORECASE | re.UNICODE)


def _combo_regex(a: str, b: str) -> re.Pattern:
    return re.compile(_LB + _core(a) + _GAP + _core(b) + _RB, re.IGNORECASE | re.UNICODE)


# ---------------------------------------------------------------------------
# Strutture dati
# ---------------------------------------------------------------------------

PROFANITY = "parolaccia"
BLASPHEMY = "bestemmia"


@dataclass(frozen=True)
class Match:
    category: str       # PROFANITY | BLASPHEMY
    severity: int       # 1..5
    start: int
    end: int
    text: str           # porzione di testo originale individuata


@dataclass
class Report:
    text: str
    matches: list[Match] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.matches

    @property
    def has_blasphemy(self) -> bool:
        return any(m.category == BLASPHEMY for m in self.matches)

    @property
    def has_profanity(self) -> bool:
        return any(m.category == PROFANITY for m in self.matches)

    @property
    def max_severity(self) -> int:
        return max((m.severity for m in self.matches), default=0)

    def summary(self) -> str:
        if self.clean:
            return "pulito"
        parts = [f"{m.category}('{m.text}', sev={m.severity})" for m in self.matches]
        return ", ".join(parts)


# ---------------------------------------------------------------------------
# Moderatore
# ---------------------------------------------------------------------------

class Moderator:
    """Supervisore: individua e ripulisce parolacce/bestemmie italiane."""

    def __init__(
        self,
        censor_style: str = "mask",          # mask | bleep | euphemism (testo)
        interjections: list[str] | None = None,
        rng: random.Random | None = None,
        enabled: bool = True,
        bip_marker: str = "[BIP]",           # come si mostra il bip nei log/console
    ):
        self.censor_style = censor_style
        self.interjections = interjections or lexicon.INTERJECTIONS
        self._rng = rng or random.Random()
        self.bip_marker = bip_marker
        # Interruttore controllabile dall'amministratore a runtime.
        # Quando è False il moderatore analizza comunque (per i log) ma NON
        # modifica il testo: la censura è bypassata in modo pulito.
        self.enabled = enabled

        # Precompila i pattern una volta sola.
        self._profanity = [
            (_word_regex(w, inflect), sev)
            for (w, sev, inflect) in lexicon.PROFANITY
        ]
        self._blasphemy: list[re.Pattern] = []
        for divine in lexicon.BLASPHEMY_DIVINE:
            for qual in lexicon.BLASPHEMY_QUALIFIER:
                self._blasphemy.append(_combo_regex(divine, qual))
                self._blasphemy.append(_combo_regex(qual, divine))
        for fixed in lexicon.BLASPHEMY_FIXED:
            self._blasphemy.append(_word_regex(fixed))

    # -- analisi -----------------------------------------------------------

    def review(self, text: str) -> Report:
        """Analizza il testo e restituisce un Report con le occorrenze."""
        raw: list[Match] = []

        for regex, sev in self._profanity:
            for m in regex.finditer(text):
                raw.append(Match(PROFANITY, sev, m.start(), m.end(), m.group()))

        for regex in self._blasphemy:
            for m in regex.finditer(text):
                raw.append(Match(BLASPHEMY, 5, m.start(), m.end(), m.group()))

        return Report(text=text, matches=self._dedup(raw))

    def is_clean(self, text: str) -> bool:
        return self.review(text).clean

    # -- censura via BIP (audio) -------------------------------------------
    # Modello attuale: il cervello NON riformula. Il supervisore individua gli
    # span "sporchi"; la voce li copre con un bip sull'audio (vedi speech.py +
    # audio_bip.py). Qui forniamo gli span e una resa testuale per log/console.
    #
    # Censura MIRATA "alla veneta": di ogni parola si lasciano udibili le PRIME
    # DUE lettere e, per parole di 5+ lettere, anche l'ULTIMA; si bippa solo il
    # centro. Così resta capibile ("ca[bip]o", "va[bip]o", "po[bip]o di[bip]").

    @staticmethod
    def _riduci_match(m: Match) -> list[tuple[int, int]]:
        """Sub-span da bippare DENTRO un match, parola per parola."""
        spans: list[tuple[int, int]] = []
        for w in re.finditer(r"[0-9a-zà-ÿ]+", m.text, re.IGNORECASE | re.UNICODE):
            lung = w.end() - w.start()
            if lung <= 2:
                continue                       # parola corta: tutta udibile
            inizio = w.start() + 2             # lascia le prime 2 lettere
            fine = w.end() - 1 if lung >= 5 else w.end()  # 5+ -> lascia l'ultima
            if fine > inizio:
                spans.append((m.start + inizio, m.start + fine))
        return spans

    def span_censura(self, report: Report) -> list[tuple[int, int]]:
        """Intervalli di CARATTERE da coprire col bip (vuoto se non `enabled`).

        Sono gli span RIDOTTI (solo il centro delle parolacce), non l'intera
        parola: vedi `_riduci_match`.
        """
        if not self.enabled:
            return []
        spans: list[tuple[int, int]] = []
        for m in report.matches:
            spans.extend(self._riduci_match(m))
        return spans

    def testo_con_bip(self, text: str, report: Report | None = None) -> str:
        """Testo con il CENTRO delle parolacce sostituito dal marcatore del bip.

        È la resa da mostrare/loggare (l'audio reale viene bippato a parte) e
        rispecchia la censura mirata: 'sei uno st[BIP]o'.
        """
        report = report or self.review(text)
        if not self.enabled or report.clean:
            return text
        out = text
        for a, b in sorted(self.span_censura(report), key=lambda s: s[0], reverse=True):
            out = out[:a] + self.bip_marker + out[b:]
        return out

    # -- punto di passaggio unico nella pipeline ---------------------------

    def process(self, text: str) -> tuple[str, Report, bool]:
        """Passaggio obbligato del parlato attraverso il supervisore.

        Restituisce: (testo_da_pronunciare, report, censura_applicata).

        Analizza SEMPRE (così l'amministratore può vedere nei log cosa sarebbe
        stato censurato), ma applica la sanificazione solo se `enabled` è True.
        Così disattivare la censura è immediato e non altera il resto del flusso.
        """
        report = self.review(text)
        if not self.enabled or report.clean:
            return text, report, False
        return self.sanitize(text, report), report, True

    @staticmethod
    def _dedup(matches: list[Match]) -> list[Match]:
        """Rimuove sovrapposizioni tenendo l'occorrenza più "grave"/lunga."""
        if not matches:
            return []
        # ordina: prima per gravità desc, poi per lunghezza desc
        ordered = sorted(
            matches,
            key=lambda m: (m.severity, m.end - m.start),
            reverse=True,
        )
        kept: list[Match] = []
        for m in ordered:
            if any(not (m.end <= k.start or m.start >= k.end) for k in kept):
                continue  # si sovrappone a una già tenuta (più grave)
            kept.append(m)
        kept.sort(key=lambda m: m.start)
        return kept

    # -- sanificazione -----------------------------------------------------

    def sanitize(self, text: str, report: Report | None = None) -> str:
        """Restituisce il testo ripulito secondo lo stile di censura scelto."""
        report = report or self.review(text)
        if report.clean:
            return text

        out = text
        # sostituisci da destra a sinistra per non invalidare gli offset
        for m in sorted(report.matches, key=lambda x: x.start, reverse=True):
            replacement = self._replacement_for(m)
            out = out[:m.start] + replacement + out[m.end:]
        return out

    def _replacement_for(self, m: Match) -> str:
        # Le bestemmie si rimpiazzano sempre con un'interiezione innocua:
        # mascherarne solo una parte lascerebbe comunque leggibile l'offesa.
        if m.category == BLASPHEMY:
            return self._rng.choice(self.interjections)

        if self.censor_style == "bleep":
            return "[bip]"
        if self.censor_style == "euphemism":
            return "[censura]"
        # default: "mask" -> prima lettera + asterischi, mantiene la lunghezza
        token = m.text
        if len(token) <= 1:
            return "*"
        return token[0] + "*" * (len(token) - 1)


# Istanza comoda con impostazioni di default.
default_moderator = Moderator()


def contains_bad_language(text: str) -> bool:
    """Helper veloce: True se c'è almeno una parolaccia o bestemmia."""
    return not default_moderator.is_clean(text)


def contiene_provocazione(text: str) -> bool:
    """True se il testo contiene un insulto o una contraddizione verso Emilio.

    Più ampio della sola parolaccia: serve a farlo infuriare anche con offese
    "pulite" (scemo, inutile, ti sbagli, ...). Vedi lexicon.PROVOCAZIONI.
    """
    t = text.lower()
    if any(p in t for p in lexicon.PROVOCAZIONI):
        return True
    return contains_bad_language(text)
