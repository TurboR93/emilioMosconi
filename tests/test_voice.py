"""Test del sistema voce: selezione profili a runtime e metriche (offline)."""

import unittest

from emilio.config import EmilioConfig
from emilio.speech import SpeechMetrics, VoiceManager, VoiceProfile


class TestVoiceManager(unittest.TestCase):
    def setUp(self):
        self.cfg = EmilioConfig()

    def test_profili_predefiniti(self):
        vm = VoiceManager(self.cfg)
        nomi = [p.name for p in vm.lista()]
        for atteso in ["mock", "offline", "veloce", "realistico", "espressivo"]:
            self.assertIn(atteso, nomi)

    def test_default_attiva_da_tts_backend(self):
        cfg = EmilioConfig()
        cfg.voice_profile = None
        cfg.tts_backend = "elevenlabs"
        self.assertEqual(VoiceManager(cfg).attiva, "realistico")
        cfg.tts_backend = "pyttsx3"
        self.assertEqual(VoiceManager(cfg).attiva, "offline")
        cfg.tts_backend = "mock"
        self.assertEqual(VoiceManager(cfg).attiva, "mock")

    def test_voice_profile_ha_priorita(self):
        cfg = EmilioConfig()
        cfg.voice_profile = "veloce"
        cfg.tts_backend = "mock"
        self.assertEqual(VoiceManager(cfg).attiva, "veloce")

    def test_cambio_voce_runtime(self):
        vm = VoiceManager(self.cfg, attiva="mock")
        vm.imposta("veloce")
        self.assertEqual(vm.attiva, "veloce")
        self.assertEqual(vm.profilo_attivo().model, "eleven_flash_v2_5")

    def test_voce_sconosciuta(self):
        vm = VoiceManager(self.cfg)
        with self.assertRaises(ValueError):
            vm.imposta("inesistente")

    def test_aggiungi_profilo(self):
        vm = VoiceManager(self.cfg)
        vm.aggiungi(VoiceProfile("custom", "mock", "voce su misura"))
        vm.imposta("custom")
        self.assertEqual(vm.attiva, "custom")

    def test_say_mock_restituisce_metriche(self):
        vm = VoiceManager(self.cfg, attiva="mock")
        m = vm.say("ciao")
        self.assertIsInstance(m, SpeechMetrics)
        self.assertEqual(m.backend, "mock")
        self.assertEqual(m.caratteri, 4)
        self.assertGreaterEqual(m.totale, 0.0)


if __name__ == "__main__":
    unittest.main()
