"""Test del sistema voce: selezione profili a runtime e metriche (offline)."""

import unittest

from emilio.config import EmilioConfig
from emilio.speech import (EMOZIONI_VOCE, ElevenLabsSpeaker, SpeechMetrics,
                           VoiceManager, VoiceProfile)


class TestVoiceManager(unittest.TestCase):
    def setUp(self):
        self.cfg = EmilioConfig()

    def test_profili_predefiniti(self):
        vm = VoiceManager(self.cfg)
        nomi = [p.name for p in vm.lista()]
        for atteso in ["mock", "offline", "veloce", "realistico", "espressivo"]:
            self.assertIn(atteso, nomi)

    def test_mock_nascosto_dal_menu(self):
        # 'mock' resta nel catalogo (selezionabile) ma è marcato nascosto: i menu
        # interattivi non lo mostrano (vedi agent.voci_visibili / CLI /voce).
        vm = VoiceManager(self.cfg)
        prof = {p.name: p for p in vm.lista()}
        self.assertTrue(prof["mock"].nascosto)
        for nome in ("offline", "veloce", "realistico", "espressivo"):
            self.assertFalse(prof[nome].nascosto)

    def test_mock_resta_selezionabile(self):
        # nascosto dal menu, ma /voce mock e EMILIO_VOICE=mock devono funzionare
        vm = VoiceManager(self.cfg)
        vm.imposta("mock")
        self.assertEqual(vm.attiva, "mock")

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


class TestPayloadEmozione(unittest.TestCase):
    """La voce ElevenLabs modula le voice_settings in base allo stato d'animo."""

    def _speaker(self, modula=True):
        p = VoiceProfile("espressivo", "elevenlabs", voice_id="x", style=0.6,
                         stability=0.5)
        return ElevenLabsSpeaker(p, api_key="k", modula_emozione=modula)

    def test_modula_voce_per_emozione(self):
        sp = self._speaker(modula=True)
        vs = sp._payload("ciao", emozione="arrabbiato")["voice_settings"]
        self.assertEqual(vs["stability"], EMOZIONI_VOCE["arrabbiato"]["stability"])
        self.assertEqual(vs["style"], EMOZIONI_VOCE["arrabbiato"]["style"])

    def test_neutro_e_default_usano_il_profilo(self):
        sp = self._speaker(modula=True)
        for emo in ("", "neutro"):
            vs = sp._payload("ciao", emozione=emo)["voice_settings"]
            self.assertEqual(vs["stability"], 0.5)
            self.assertEqual(vs["style"], 0.6)

    def test_flag_off_disattiva_la_modulazione(self):
        sp = self._speaker(modula=False)
        vs = sp._payload("ciao", emozione="arrabbiato")["voice_settings"]
        self.assertEqual(vs["stability"], 0.5)   # resta il valore del profilo
        self.assertEqual(vs["style"], 0.6)


if __name__ == "__main__":
    unittest.main()
