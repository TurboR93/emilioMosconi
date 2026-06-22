# emilioMosconi 🤖

Ridare vita a **Emilio** in un robottino anni '90: un cervello **LLM (Claude)**
che lo fa parlare come una persona vera in stile "Germano Mosconi", una **voce
italiana realistica** (ElevenLabs, flessibile e a bassa latenza) e un
**supervisore** che censura parolacce e bestemmie — **disattivabile
dall'amministratore**.

Tutto il codice è nel package **`emilio/`**. Documentazione completa in
**`emilio/docs/`**:

- `emilio/README.md` — panoramica e uso
- `emilio/docs/PROGETTO.md` — documentazione esaustiva (architettura, voce,
  supervisore, configurazione, roadmap)
- `emilio/docs/HARDWARE.md` — componenti da comprare (Raspberry, microfono,
  altoparlante, motori)

## Avvio rapido (offline, senza chiavi)

```bash
python3 -m venv .venv && source .venv/bin/activate
python3 -m emilio
```

## Emilio "completo" (LLM + voce realistica)

```bash
pip install anthropic requests          # opz.: pyttsx3 pyserial
export ANTHROPIC_API_KEY=...            # cervello
export ELEVENLABS_API_KEY=...           # voce
export ELEVENLABS_VOICE_ID=...          # voce italiana del tuo account
export EMILIO_USE_LLM=1 EMILIO_VOICE=veloce
python3 -m emilio
```

## Test

```bash
python3 -m unittest emilio.tests.test_moderation emilio.tests.test_voice
```
