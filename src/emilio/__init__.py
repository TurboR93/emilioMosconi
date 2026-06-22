"""Emilio — base per un robottino anni '90 con cervello LLM e supervisore.

Componenti:
  * persona     -> chi è Emilio e come si comporta
  * brain       -> base LLM (Claude) o cervello finto offline
  * moderation  -> supervisore che censura parolacce e bestemmie (disattivabile)
  * speech      -> voce TTS (ElevenLabs realistico / offline / mock)
  * actuators   -> movimento del robottino (seriale / simulato)
  * agent       -> orchestrazione dell'intera pipeline del parlato
"""

from .agent import EmilioAgent, RisultatoParlato
from .config import EmilioConfig
from .persona import Persona

__version__ = "0.1.0"

__all__ = ["EmilioAgent", "RisultatoParlato", "EmilioConfig", "Persona", "__version__"]
