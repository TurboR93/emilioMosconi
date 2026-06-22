"""Test della reattività emotiva (occhi arrabbiati + bip se provocato) e
dell'ascolto vocale (STT) in mock — tutto offline, senza microfono né rete."""

import unittest

from emilio.agent import EmilioAgent, _estrai_emozione
from emilio.ascolto import MockAscoltatore, build_ascoltatore
from emilio.brain import MockBrain
from emilio.config import EmilioConfig


class TestTagEmozione(unittest.TestCase):
    def test_estrai_tag(self):
        self.assertEqual(_estrai_emozione("[arrabbiato] Ma vaffa..."),
                         ("arrabbiato", "Ma vaffa..."))

    def test_senza_tag(self):
        self.assertEqual(_estrai_emozione("nessun tag qui"), (None, "nessun tag qui"))


class TestReazione(unittest.TestCase):
    def _ag(self):
        return EmilioAgent(EmilioConfig(), brain=MockBrain(seed=0))

    def test_insulto_lo_fa_infuriare_e_bippa(self):
        ag = self._ag()
        ris = ag.parla("sei uno stronzo")
        self.assertEqual(ris.emozione, "arrabbiato")
        self.assertTrue(ris.censura_applicata)                       # sbotta sboccato -> bip
        self.assertEqual(ag.occhi.stato.espressione, "arrabbiato")   # occhi = forche del diavolo

    def test_contraddizione_lo_fa_infuriare(self):
        ag = self._ag()
        ris = ag.parla("ti sbagli, non è vero niente")
        self.assertEqual(ris.emozione, "arrabbiato")

    def test_gentile_resta_calmo(self):
        ag = self._ag()
        ris = ag.parla("ciao, come stai oggi?")
        self.assertNotEqual(ris.emozione, "arrabbiato")
        self.assertNotEqual(ag.occhi.stato.espressione, "arrabbiato")

    def test_insulto_mite_senza_parolacce(self):
        # offese "pulite" (scemo/inutile) devono comunque farlo infuriare
        ris = self._ag().parla("ma quanto sei inutile e scemo")
        self.assertEqual(ris.emozione, "arrabbiato")

    def test_due_insulti_di_fila_triggerano_entrambi(self):
        ag = self._ag()
        r1 = ag.parla("sei un cretino")
        r2 = ag.parla("ti sbagli, non vali niente")
        self.assertEqual(r1.emozione, "arrabbiato")
        self.assertEqual(r2.emozione, "arrabbiato")

    def test_il_tag_non_viene_pronunciato(self):
        ag = self._ag()
        ris = ag.parla("sei uno stronzo")
        # il tag di stato d'animo non finisce nel parlato (né grezzo né detto)
        self.assertNotIn("[arrabbiato]", ris.testo_grezzo)
        self.assertNotIn("[arrabbiato]", ris.testo_detto)
        # il testo grezzo non ha tag/parentesi a inizio (i [BIP] stanno nel detto)
        self.assertFalse(ris.testo_grezzo.lstrip().startswith("["))


class TestAscolto(unittest.TestCase):
    def test_default_e_mock(self):
        self.assertIsInstance(build_ascoltatore(EmilioConfig()), MockAscoltatore)

    def test_agent_ascolta_mock(self):
        ag = EmilioAgent(EmilioConfig(), brain=MockBrain(seed=0),
                         ascolto=MockAscoltatore("prova microfono"))
        self.assertEqual(ag.ascolta(), "prova microfono")
        # dopo l'ascolto gli occhi tornano neutri
        self.assertEqual(ag.occhi.stato.espressione, "neutro")


if __name__ == "__main__":
    unittest.main()
