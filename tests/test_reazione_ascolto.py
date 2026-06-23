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

    def test_tag_inventato_staccato(self):
        # tag d'animo non canonico (il modello a volte li inventa): va STACCATO
        # comunque, così non viene pronunciato (emozione -> neutro/None).
        self.assertEqual(_estrai_emozione("[scettico] eh, vabbè"), (None, "eh, vabbè"))
        self.assertEqual(_estrai_emozione("[brontolo bonario] ciao"), (None, "ciao"))

    def test_contenuto_vero_preservato(self):
        # contenuto legittimo fra parentesi (maiuscole/cifre): NON va toccato
        self.assertEqual(_estrai_emozione("[Bologna] che squadra"),
                         (None, "[Bologna] che squadra"))
        self.assertEqual(_estrai_emozione("[3-1] partitone"), (None, "[3-1] partitone"))

    def test_tag_nudo_senza_parentesi_staccato(self):
        # i modelli (spesso LOCALI) a volte dimenticano le [] e scrivono il tag
        # "nudo": va staccato comunque, così non finisce PRONUNCIATO.
        self.assertEqual(_estrai_emozione("felice: ciao a tutti"),
                         ("felice", "ciao a tutti"))
        self.assertEqual(_estrai_emozione("Felice - ciao"), ("felice", "ciao"))
        self.assertEqual(_estrai_emozione("triste; che giornata"),
                         ("triste", "che giornata"))
        # avvolto da parentesi tonde / asterischi: l'involucro segnala il tag
        self.assertEqual(_estrai_emozione("(felice) ciao"), ("felice", "ciao"))
        self.assertEqual(_estrai_emozione("*arrabbiato* ma cosa"),
                         ("arrabbiato", "ma cosa"))
        # parola d'animo da sola = tutta la risposta
        self.assertEqual(_estrai_emozione("felice"), ("felice", ""))

    def test_tag_nudo_non_mangia_frasi_legittime(self):
        # parola d'animo seguita da testo SENZA separatore: è una frase vera,
        # NON un tag -> resta intatta (niente falsi positivi).
        self.assertEqual(_estrai_emozione("Felice di vederti, come stai?"),
                         (None, "Felice di vederti, come stai?"))
        self.assertEqual(_estrai_emozione("Bologna è una bella città"),
                         (None, "Bologna è una bella città"))


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
