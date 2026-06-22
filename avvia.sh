#!/usr/bin/env bash
# Avvio "tutto incluso" di Emilio: attiva il venv, carica le chiavi locali,
# assicura che Ollama giri, imposta il profilo e lancia la console.
#
# Uso (da iTerm o qualsiasi terminale):
#     ./avvia.sh
# oppure da qualunque cartella:
#     /Users/riccardobrunello/websites/emilioMosconi/avvia.sh
#
# Per cambiare al volo un'opzione basta esportarla prima:
#     EMILIO_VOICE=offline ./avvia.sh
#     EMILIO_ASCOLTO=whisper ./avvia.sh

set -e
cd "$(dirname "$0")"

# 1) venv
if [ ! -f .venv/bin/activate ]; then
    echo "❌ Manca il venv (.venv). Crealo con: python3.11 -m venv .venv && source .venv/bin/activate && pip install -e \".[all,dev]\""
    exit 1
fi
source .venv/bin/activate

# 2) chiavi/segreti locali (ELEVENLABS_API_KEY, ...), se presenti
[ -f .env.local ] && source .env.local

# 3) Ollama acceso? (serve al cervello locale)
if command -v ollama >/dev/null 2>&1; then
    if ! pgrep -x ollama >/dev/null 2>&1; then
        echo "▶️  Avvio Ollama in sottofondo..."
        ollama serve >/tmp/ollama.log 2>&1 &
        sleep 2
    fi
fi

# 4) profilo di default (sovrascrivibile dall'ambiente già esportato)
export EMILIO_LLM="${EMILIO_LLM:-local}"
export EMILIO_VOICE="${EMILIO_VOICE:-veloce}"
export EMILIO_OCCHI="${EMILIO_OCCHI:-preview}"
export EMILIO_ASCOLTO="${EMILIO_ASCOLTO:-mlx}"

echo "🤖 Avvio Emilio (LLM=$EMILIO_LLM, voce=$EMILIO_VOICE, occhi=$EMILIO_OCCHI, ascolto=$EMILIO_ASCOLTO)"
exec emilio
