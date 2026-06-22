"""Test del cervello locale (selezione backend) e degli occhi (offline).

Nessuna rete: si verifica solo la SELEZIONE/costruzione del LocalBrain (non la
chiamata HTTP) e il comportamento degli occhi mock.
"""

import unittest

from emilio.agent import EmilioAgent
from emilio.brain import LocalBrain, MockBrain, build_brain
from emilio.config import EmilioConfig
from emilio.occhi import ESPRESSIONI, OcchiError, OcchiMock, build_occhi
from emilio.persona import Persona


class TestSelezioneCervello(unittest.TestCase):
    def test_default_e_mock(self):
        self.assertIsInstance(build_brain(EmilioConfig(), Persona()), MockBrain)

    def test_backend_local(self):
        cfg = EmilioConfig()
        cfg.llm_backend = "local"
        cfg.local_llm_model = "gemma4:12b"
        b = build_brain(cfg, Persona())
        self.assertIsInstance(b, LocalBrain)
        self.assertEqual(b.model, "gemma4:12b")
        self.assertTrue(b.base_url.endswith("/v1"))

    def test_use_real_llm_retrocompat_resta_mock_se_non_anthropic(self):
        # EMILIO_LLM vuoto + use_real_llm False => mock (non tocca la rete)
        cfg = EmilioConfig()
        cfg.use_real_llm = False
        self.assertIsInstance(build_brain(cfg, Persona()), MockBrain)


class TestOcchi(unittest.TestCase):
    def setUp(self):
        self.occhi = OcchiMock()

    def test_default_factory_e_mock(self):
        self.assertIsInstance(build_occhi(EmilioConfig()), OcchiMock)

    def test_imposta_espressione(self):
        s = self.occhi.imposta("arrabbiato")
        self.assertEqual(s.espressione, "arrabbiato")
        self.assertEqual(s.colore, ESPRESSIONI["arrabbiato"][0])
        self.assertTrue(s.aperti)

    def test_espressione_sconosciuta(self):
        with self.assertRaises(OcchiError):
            self.occhi.imposta("inesistente")

    def test_spegni(self):
        self.occhi.imposta("felice")
        self.occhi.spegni()
        self.assertEqual(self.occhi.stato.espressione, "spento")
        self.assertFalse(self.occhi.stato.aperti)

    def test_guarda(self):
        self.occhi.guarda("sinistra")
        self.assertEqual(self.occhi.stato.direzione, "sinistra")
        with self.assertRaises(OcchiError):
            self.occhi.guarda("altrove")


class TestOcchiNellaPipeline(unittest.TestCase):
    def test_dopo_parla_occhi_neutri(self):
        ag = EmilioAgent(EmilioConfig(), brain=MockBrain(seed=1))
        ag.parla("ciao")
        # _pronuncia mette "parla" durante e "neutro" alla fine
        self.assertEqual(ag.occhi.stato.espressione, "neutro")

    def test_set_occhi_runtime(self):
        ag = EmilioAgent(EmilioConfig(), brain=MockBrain(seed=1))
        ag.set_occhi("sorpreso")
        self.assertEqual(ag.occhi.stato.espressione, "sorpreso")


if __name__ == "__main__":
    unittest.main()
