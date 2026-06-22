# Strumenti — arricchire il vocabolario di Emilio

## `estrai_lessico.py` — da chat WhatsApp a vocabolario

Estrae parole, modi di dire, bestemmie nuove e versi (rutti/scoregge/risate) da
un **export ufficiale** di WhatsApp, per ampliare il lessico di Emilio
([`src/emilio/moderation/lexicon.py`](../src/emilio/moderation/lexicon.py)).

> **Privacy.** Non è uno scraper e non automatizza WhatsApp (vietato dai termini
> e fragile). Usa l'esportazione ufficiale. L'export grezzo e il report restano
> in `data/` (**ignorata da git**): nel repo pubblico finisce solo il vocabolario
> curato che scegli tu. Lo strumento butta via nomi, numeri, orari e URL: nel
> report ci sono **solo parole e frequenze**, mai messaggi interi o mittenti.

### 1. Esporta la chat da WhatsApp

- **iPhone**: apri la chat di gruppo → tocca il **nome del gruppo** in alto →
  scorri in fondo → **Esporta chat** → **Senza media** → salva il file (o
  "Salva su File" / invialo a te stesso) e portalo sul Mac.
- **Android**: apri la chat → **⋮** (tre puntini) → **Altro** → **Esporta chat**
  → **Senza media**.

Ottieni un file tipo `_chat.txt` (iOS) o `Chat WhatsApp con ....txt` (Android).

### 2. Mettilo nella cartella locale (ignorata da git)

```bash
mkdir -p data/whatsapp
mv ~/Downloads/_chat.txt data/whatsapp/      # o dovunque l'hai salvato
```

### 3. Lancia l'estrattore

```bash
source .venv/bin/activate
python tools/estrai_lessico.py data/whatsapp/_chat.txt --top 100
```

Scrive un report accanto all'export (es. `data/whatsapp/_chat_lessico.txt`) con:

- **Bestemmie nuove** — combo "entità divina + parola" non ancora riconosciute
  dal supervisore (es. `dio mostro`): le più ricorrenti sono quelle da aggiungere.
- **Versi/onomatopee** — `braaap`, `prrr`, `ahahah`... per dare colore alla persona.
- **Parole** e **modi di dire** (bi/tri-grammi) più frequenti del gruppo.

### 4. Cura e aggiungi

Apri il report, scegli i termini buoni e aggiungili a `lexicon.py`:

- nuovi **qualificatori** di bestemmia (es. `cancro`, `mostro`) → `BLASPHEMY_QUALIFIER`
- **espressioni fisse** → `BLASPHEMY_FIXED`
- **parolacce** nuove → `PROFANITY` (radice, gravità, inflect)
- **insulti** che lo fanno infuriare → `PROVOCAZIONI`

Poi lancia i test (`python -m pytest`) e prova in console (`/mod <frase>` per
verificare che il supervisore ora la riconosca). Solo `lexicon.py` va committato;
`data/` resta in locale.
