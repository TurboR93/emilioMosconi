"""Test della pipeline STREAMING (parla frase per frase) e del backend STT mlx.

Tutto offline: niente rete, niente microfono, niente modelli. Si usano cervelli
finti che emettono pezzi di testo e una voce finta che registra cosa viene detto.
"""

import unittest

from emilio.agent import (
    EmilioAgent, _estrai_emozione, _fondi_metriche, _spezza_frasi,
)
from emilio.ascolto import (
    MlxAscoltatore, MockAscoltatore, WhisperAscoltatore, _risolvi_repo_mlx,
    _vad_stato, build_ascoltatore,
)
from emilio.brain import Brain, MockBrain
from emilio.config import EmilioConfig
from emilio.speech import SpeechMetrics


# --- doppi di test ---------------------------------------------------------

class _CervelloPezzi(Brain):
    """Cervello finto che emette una sequenza di pezzi (simula lo streaming)."""

    def __init__(self, pezzi):
        self.pezzi = list(pezzi)

    def reply(self, user_text="", umore=""):
        return "".join(self.pezzi)

    def reply_stream(self, user_text="", umore=""):
        yield from self.pezzi

    def revise(self, motivo=""):
        return ""


class _VoceFinta:
    """Registra le frasi pronunciate, gli span di censura e il contesto."""

    def __init__(self):
        self.dette = []
        self.span = []
        self.prev = []

    def say(self, text, bleep_spans=None, previous_text="", next_text=""):
        self.dette.append(text)
        self.span.append(bleep_spans or [])
        self.prev.append(previous_text)
        return SpeechMetrics("finta", "finta", ttfb=0.01, totale=0.02, caratteri=len(text))


def _agente(brain, voci=None):
    return EmilioAgent(EmilioConfig(), brain=brain, voci=voci)


# --- segmentazione in frasi ------------------------------------------------

class TestSpezzaFrasi(unittest.TestCase):
    def test_frase_in_coda_resta_in_sospeso(self):
        # il punto finale è in fondo al buffer: non sappiamo se la frase è finita
        frasi, resto = _spezza_frasi("Ciao a tutti.")
        self.assertEqual(frasi, [])
        self.assertEqual(resto, "Ciao a tutti.")

    def test_estrae_frasi_complete(self):
        frasi, resto = _spezza_frasi("Uno. Due! Tre")
        self.assertEqual(frasi, ["Uno.", "Due!"])
        self.assertEqual(resto.strip(), "Tre")

    def test_punteggiatura_multipla_e_chiusure(self):
        frasi, resto = _spezza_frasi('Ma davvero?! "Sì." E poi')
        self.assertEqual(frasi, ['Ma davvero?!', '"Sì."'])
        self.assertEqual(resto.strip(), "E poi")

    def test_puntini_sospensione_non_spezzano(self):
        # i "..." sono una pausa nel parlato di Emilio, non fine frase
        frasi, resto = _spezza_frasi("Eh... ci sono qua. Ma")
        self.assertEqual(frasi, ["Eh... ci sono qua."])
        self.assertEqual(resto.strip(), "Ma")


class TestFondiMetriche(unittest.TestCase):
    def test_somma_e_primo_ttfb(self):
        m = _fondi_metriche([
            SpeechMetrics("x", "v", ttfb=None, totale=1.0, caratteri=3),
            SpeechMetrics("x", "v", ttfb=0.4, totale=2.0, caratteri=5),
        ])
        self.assertEqual(m.ttfb, 0.4)
        self.assertAlmostEqual(m.totale, 3.0)
        self.assertEqual(m.caratteri, 8)

    def test_lista_vuota(self):
        self.assertIsNone(_fondi_metriche([]))


# --- pipeline streaming ----------------------------------------------------

class TestParlaStreaming(unittest.TestCase):
    def test_tag_e_chunking_prima_frase_poi_blocco(self):
        voci = _VoceFinta()
        brain = _CervelloPezzi(["[fel", "ice] Ciao a ", "tutti. Come va", " oggi? Bene."])
        ris = _agente(brain, voci).parla_streaming("ciao")
        # il tag spezzato fra due pezzi viene comunque staccato (non si pronuncia)
        self.assertEqual(ris.emozione, "felice")
        self.assertNotIn("felice]", " ".join(voci.dette))
        # prima frase subito (TTFT basso), poi TUTTO il resto in un blocco unico
        self.assertEqual(voci.dette, ["Ciao a tutti.", "Come va oggi? Bene."])
        # la seconda sintesi riceve come contesto ciò che è già stato detto
        self.assertEqual(voci.prev, ["", "Ciao a tutti."])

    def test_insulto_bippa_frase_per_frase_e_occhi_arrabbiati(self):
        voci = _VoceFinta()
        ag = _agente(MockBrain(seed=0), voci)
        ris = ag.parla_streaming("sei uno stronzo")
        self.assertEqual(ris.emozione, "arrabbiato")
        self.assertTrue(ris.censura_applicata)
        self.assertTrue(any(s for s in voci.span))           # almeno una frase bippata
        self.assertEqual(ag.occhi.stato.espressione, "arrabbiato")
        self.assertNotIn("[arrabbiato]", ris.testo_grezzo)
        self.assertNotIn("[arrabbiato]", ris.testo_detto)

    def test_pulito_resta_calmo(self):
        ag = _agente(MockBrain(seed=1))
        ris = ag.parla_streaming("ciao, come stai oggi?")
        self.assertNotEqual(ris.emozione, "arrabbiato")
        self.assertFalse(ris.censura_applicata)


class TestToggleStreaming(unittest.TestCase):
    def test_default_streaming_da_config(self):
        ag = EmilioAgent(EmilioConfig(), brain=MockBrain(seed=0))
        self.assertTrue(ag.streaming)

    def test_rispondi_segue_il_toggle(self):
        cfg = EmilioConfig()
        cfg.streaming = False
        ag = EmilioAgent(cfg, brain=MockBrain(seed=0))
        self.assertFalse(ag.streaming)
        # con streaming OFF non deve esplodere e deve comunque rispondere
        ris = ag.rispondi("ciao")
        self.assertTrue(ris.testo_grezzo)
        ag.set_streaming(True)
        self.assertTrue(ag.streaming)


# --- ascolto: VAD e backend mlx --------------------------------------------

class TestVad(unittest.TestCase):
    def test_voce_sopra_soglia_azzera_silenzio(self):
        self.assertEqual(_vad_stato(2000, 500, False, 0.3, 0.03, 0.8),
                         (True, 0.0, False))

    def test_pausa_dopo_parlato_ferma(self):
        # accumulato 0.78s di silenzio + 0.03s -> supera la coda di 0.8s: stop
        parlato, acc, stop = _vad_stato(100, 500, True, 0.78, 0.03, 0.8)
        self.assertTrue(parlato)
        self.assertTrue(stop)

    def test_silenzio_iniziale_non_parte(self):
        self.assertEqual(_vad_stato(100, 500, False, 0.0, 0.03, 0.8),
                         (False, 0.0, False))


class TestBackendAscolto(unittest.TestCase):
    def test_default_e_mock(self):
        self.assertIsInstance(build_ascoltatore(EmilioConfig()), MockAscoltatore)

    def test_backend_mlx(self):
        cfg = EmilioConfig()
        cfg.stt_backend = "mlx"
        cfg.stt_model = "base"
        a = build_ascoltatore(cfg)
        self.assertIsInstance(a, MlxAscoltatore)
        self.assertEqual(a.repo, "mlx-community/whisper-base-mlx")

    def test_backend_whisper(self):
        cfg = EmilioConfig()
        cfg.stt_backend = "whisper"
        self.assertIsInstance(build_ascoltatore(cfg), WhisperAscoltatore)

    def test_repo_mlx(self):
        self.assertEqual(_risolvi_repo_mlx("small"), "mlx-community/whisper-small-mlx")
        self.assertEqual(_risolvi_repo_mlx("org/mio-modello"), "org/mio-modello")


if __name__ == "__main__":
    unittest.main()
