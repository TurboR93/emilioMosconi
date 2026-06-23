"""Test della modalità monitor (/verboso): l'agente, se gli passi un callback
`su_frase`, lo chiama col testo (già bippato) appena prima di pronunciarlo —
così la console può mostrarlo in tempo reale. Tutto offline (mock)."""

import unittest

from emilio.agent import EmilioAgent
from emilio.config import EmilioConfig


class TestMonitorCallback(unittest.TestCase):
    def test_flag_default_on(self):
        # Il monitor è ON di default (EMILIO_VERBOSO, default vero).
        self.assertTrue(EmilioAgent(EmilioConfig()).verboso)

    def test_su_frase_streaming(self):
        a = EmilioAgent(EmilioConfig())          # streaming ON di default
        viste: list[str] = []
        ris = a.rispondi("ciao, come va oggi", su_frase=viste.append)
        self.assertTrue(viste)                                   # mostrata ≥1 frase
        # ciò che è stato mostrato == ciò che ha detto davvero (post-bip)
        self.assertEqual(" ".join(viste).strip(), ris.testo_detto)

    def test_su_frase_blocco(self):
        a = EmilioAgent(EmilioConfig())
        a.set_streaming(False)
        viste: list[str] = []
        ris = a.rispondi("ciao", su_frase=viste.append)
        self.assertEqual(len(viste), 1)
        self.assertEqual(viste[0], ris.testo_detto)

    def test_senza_callback_non_crasha(self):
        a = EmilioAgent(EmilioConfig())
        ris = a.rispondi("ciao")
        self.assertTrue(ris.testo_detto)

    def test_callback_mostra_il_bip(self):
        # provocazione + (eventuale) turpiloquio: il testo mostrato deve contenere
        # il marcatore [BIP] esattamente come il testo_detto pronunciato.
        a = EmilioAgent(EmilioConfig())
        viste: list[str] = []
        ris = a.rispondi("sei un coglione di robot", su_frase=viste.append)
        self.assertEqual(" ".join(viste).strip(), ris.testo_detto)


if __name__ == "__main__":
    unittest.main()
