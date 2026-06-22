"""Test del supervisore (parolacce + bestemmie italiane).

Esecuzione:
    python -m unittest emilio.tests.test_moderation
    # oppure
    python -m pytest emilio/tests/test_moderation.py
"""

import unittest

from emilio.moderation import Moderator


class TestBestemmie(unittest.TestCase):
    def setUp(self):
        self.mod = Moderator()

    def test_combinazioni_classiche(self):
        for frase in [
            "porco dio che giornata",
            "ma dio cane",
            "porca madonna",
            "dio boia",
            "madonna puttana",
            "dio ladro",
        ]:
            with self.subTest(frase=frase):
                self.assertTrue(self.mod.review(frase).has_blasphemy, frase)

    def test_forme_attaccate_e_leet(self):
        for frase in [
            "porcodio",
            "diocane!!!",
            "p0rc0 di0",          # leetspeak
            "DIO  CANE",          # maiuscole + doppio spazio
            "diooo cane",         # lettere ripetute
        ]:
            with self.subTest(frase=frase):
                self.assertTrue(self.mod.review(frase).has_blasphemy, frase)

    def test_bestemmie_fisse(self):
        self.assertTrue(self.mod.review("dio morto").has_blasphemy)
        self.assertTrue(self.mod.review("cristo morto").has_blasphemy)

    def test_no_falsi_positivi_religiosi(self):
        # entità divina da sola: NON deve scattare
        for frase in [
            "il dio greco Zeus era potente",
            "madonna che bella giornata",
            "ho visto una statua di Cristo",
            "addio amici, ci vediamo",      # 'addio' contiene 'dio'
            "credo in Dio",
        ]:
            with self.subTest(frase=frase):
                self.assertFalse(self.mod.review(frase).has_blasphemy, frase)

    def test_eufemismi_non_bestemmie(self):
        # questi sono moccoli "puliti": NON devono essere classificati bestemmia
        for frase in ["porca miseria", "porca paletta", "porca vacca"]:
            with self.subTest(frase=frase):
                self.assertFalse(self.mod.review(frase).has_blasphemy, frase)


class TestParolacce(unittest.TestCase):
    def setUp(self):
        self.mod = Moderator()

    def test_volgarita(self):
        for frase in [
            "ma che cazzo fai",
            "vaffanculo",
            "sei uno stronzo",
            "che merda di situazione",
            "non capisci una minchia",
            "sei un coglione",
        ]:
            with self.subTest(frase=frase):
                self.assertTrue(self.mod.review(frase).has_profanity, frase)

    def test_flessioni(self):
        for frase in ["che cazzata", "cazzone", "stronzata", "incazzato nero"]:
            with self.subTest(frase=frase):
                self.assertTrue(self.mod.review(frase).has_profanity, frase)

    def test_parole_innocenti(self):
        for frase in [
            "ho fatto un calcolo",
            "che pezzo di musica",
            "il calzino è bucato",
            "andiamo al mare",
            "che bella mazza da baseball",
        ]:
            with self.subTest(frase=frase):
                self.assertTrue(self.mod.review(frase).clean, frase)


class TestSanificazione(unittest.TestCase):
    def setUp(self):
        self.mod = Moderator(censor_style="mask")

    def test_mascheramento_parolaccia(self):
        out = self.mod.sanitize("sei uno stronzo")
        self.assertNotIn("stronzo", out)
        self.assertIn("s", out)   # prima lettera mantenuta

    def test_bestemmia_sostituita_con_interiezione(self):
        out = self.mod.sanitize("porco dio che rabbia")
        self.assertNotIn("dio", out.lower())
        # il testo "innocuo" attorno resta
        self.assertIn("che rabbia", out)

    def test_testo_pulito_invariato(self):
        frase = "buongiorno a tutti, oggi è una bella giornata"
        self.assertEqual(self.mod.sanitize(frase), frase)


class TestControlloAmministratore(unittest.TestCase):
    def test_disattivazione_runtime(self):
        mod = Moderator(enabled=True)
        frase = "porco dio"

        # attiva: censura applicata
        out, report, applied = mod.process(frase)
        self.assertTrue(applied)
        self.assertNotIn("dio", out.lower())
        self.assertTrue(report.has_blasphemy)   # report comunque popolato

        # disattivata: testo invariato ma report ancora disponibile per i log
        mod.enabled = False
        out2, report2, applied2 = mod.process(frase)
        self.assertFalse(applied2)
        self.assertEqual(out2, frase)
        self.assertTrue(report2.has_blasphemy)  # l'amministratore vede cosa "sarebbe" stato censurato


if __name__ == "__main__":
    unittest.main()
