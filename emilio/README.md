# Emilio 🤖

Base per ridare vita a **Emilio** dentro un robottino anni '90: un cervello
LLM che lo fa parlare come una **persona vera**, un **supervisore** che censura
parolacce e bestemmie in italiano, una **voce realistica** e il **controllo del
movimento** (anche manuale).

L'idea è un personaggio italiano verace e brontolone (pensa al genere
"Germano Mosconi", ma ripulito): l'LLM dà spontaneità, il supervisore tiene la
bocca pulita.

## Architettura

```
input utente
   │
   ▼
[Cervello LLM]  brain.py        → genera la risposta in carattere
   │
   ▼
[Supervisore]   moderation/     → individua parolacce + bestemmie (IT)
   │                              se bestemmia: chiede riformulazione all'LLM,
   │                              poi comunque ripulisce. DISATTIVABILE.
   ▼
[Voce TTS]      speech.py       → ElevenLabs (realistico) / offline / mock
   │
[Movimento]     actuators.py    → seriale (Arduino/motori) / simulato
```

Orchestrazione in `agent.py`. Ogni componente è dietro un'interfaccia e ha un
backend "mock" che gira **offline e senza chiavi**, così sviluppi tutto sul Mac
e poi cambi solo la configurazione per il Raspberry.

## Componenti

| File | Ruolo |
|------|-------|
| `persona.py` | Chi è Emilio, come si comporta, system prompt (1ª difesa anti-turpiloquio) |
| `brain.py` | Base LLM: `ClaudeBrain` (API) o `MockBrain` (offline) |
| `moderation/` | **Supervisore**: lessico + motore di censura (2ª difesa) |
| `speech.py` | Voce: `ElevenLabsSpeaker` / `Pyttsx3Speaker` / `MockSpeaker` |
| `actuators.py` | Movimento: `SerialMover` / `MockMover` |
| `agent.py` | Pipeline completa |
| `cli.py` | Console di controllo manuale |

## Il supervisore (parolacce + bestemmie)

È il pezzo centrale. Caratteristiche:

- **Bestemmie combinatorie**: riconosce entità divina + qualificatore offensivo
  in qualunque ordine (`porco dio`, `dio cane`, `porca madonna`...), anche
  attaccati (`porcodio`) o con punteggiatura in mezzo.
- **Resistente alle evasioni**: lettere ripetute (`diooo`), leetspeak
  (`p0rc0 di0`), maiuscole, accenti.
- **Preciso**: le parole religiose da sole NON vengono censurate (`credo in Dio`,
  `madonna che bello` passano lisce).
- **Parolacce con flessioni**: una radice intercetta le varianti (`cazz` →
  cazzo, cazzi, cazzata, cazzone).

Stili di censura (`EMILIO_CENSOR_STYLE`): `mask` (c\*\*\*o), `bleep` ([bip]),
`euphemism` ([censura]). Le bestemmie vengono sempre sostituite con
un'interiezione innocua ("santo cielo", "mannaggia"...).

### Controllo dell'amministratore

La censura è **attivabile/disattivabile a runtime** ed è un passaggio
obbligato del parlato (`Moderator.process`). Anche da spenta, il supervisore
continua ad **analizzare** il testo per i log (così sai cosa *sarebbe* stato
censurato).

```python
agent.set_moderazione(False)   # disattiva
agent.set_moderazione(True)    # riattiva
agent.moderazione_attiva       # stato
```

Da console: `/censura on|off|stato`.

### Ampliare il lessico

Aggiungi termini in `moderation/lexicon.py` (parolacce, entità divine,
qualificatori, espressioni fisse). Nessuna modifica al motore.

## Uso

### Console interattiva (offline, subito)

```bash
python -m emilio
```

```
tu> Come va Emilio?
🔊 [Emilio] Eh, ai miei tempi sì che si stava bene...
tu> /muovi avanti 2
🤖 [Emilio muove] vai avanti (x2)
tu> /censura off
tu> /di porco dio
🔊 [Emilio] porco dio        # con censura off passa invariato
```

### Con LLM reale + voce ElevenLabs

```bash
export ANTHROPIC_API_KEY=...        # cervello
export ELEVENLABS_API_KEY=...       # voce
export ELEVENLABS_VOICE_ID=...      # voce italiana scelta sul tuo account
export EMILIO_USE_LLM=1
export EMILIO_TTS=elevenlabs
python -m emilio
```

### Da codice

```python
from emilio import EmilioAgent

emilio = EmilioAgent()
ris = emilio.parla("Raccontami una cosa dei tuoi tempi")
print(ris.testo_detto)        # ciò che ha detto (post-supervisore)
print(ris.report.summary())   # esito dell'analisi
```

## Configurazione (variabili d'ambiente)

| Variabile | Default | Note |
|-----------|---------|------|
| `EMILIO_USE_LLM` | `0` | `1` per usare Claude |
| `EMILIO_MODEL` | `claude-opus-4-8` | modello LLM |
| `EMILIO_MODERATION` | `1` | supervisione on/off all'avvio |
| `EMILIO_CENSOR_STYLE` | `mask` | `mask`/`bleep`/`euphemism` |
| `EMILIO_MAX_REGEN` | `2` | tentativi di riformulazione su bestemmia |
| `EMILIO_VOICE` | (deriva da `EMILIO_TTS`) | profilo voce: `mock`/`offline`/`veloce`/`realistico`/`espressivo` |
| `EMILIO_TTS` | `mock` | ripiego se `EMILIO_VOICE` non impostato |
| `ELEVENLABS_API_KEY` / `ELEVENLABS_VOICE_ID` | — | voce realistica IT |
| `EMILIO_ACTUATORS` | `mock` | `serial`/`mock` |
| `EMILIO_SERIAL_PORT` | `/dev/ttyUSB0` | porta seriale motori |
| `EMILIO_PERSONA` | — | file JSON con una persona custom |

## Hardware (Raspberry / Mac)

- Il carico pesante (LLM + TTS) è **nel cloud**: il Raspberry fa da
  orchestratore, quindi basta un modello modesto (Pi 3/4/5).
- La voce ElevenLabs viene salvata in MP3 e riprodotta col player di sistema
  (`afplay` su macOS, `mpg123`/`ffplay`/`aplay` su Linux/Raspberry).
- Il movimento usa una seriale testuale: `MOVE <azione> <valore>\n`. Lato
  robottino puoi mettere un Arduino/microcontrollore che pilota motori e LED.

## Test

```bash
python -m unittest emilio.tests.test_moderation -v
```

## Dipendenze

Il nucleo gira con la sola **libreria standard**. I componenti reali sono
opzionali — vedi `requirements.txt` (`anthropic`, `requests`, `pyttsx3`,
`pyserial`).
