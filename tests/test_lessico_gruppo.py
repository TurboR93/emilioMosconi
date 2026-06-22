"""Test degli ampliamenti del lessico dal gruppo WhatsApp (stile veneto/creativo).

Verifica che le nuove combo siano riconosciute come bestemmie/parolacce e che
non si introducano falsi positivi su parole innocenti.
"""

import unittest

from emilio.moderation import default_moderator as M


class TestBestemmieNuove(unittest.TestCase):
    def test_combo_creative_riconosciute(self):
        for t in ("dio mostro", "madonna pantegana", "dio serpente",
                  "cristo impanato", "dio boja", "dio pterodattilo",
                  "dio letame", "cristo feroce"):
            self.assertTrue(M.review(t).has_blasphemy, f"non rilevata: {t}")

    def test_grafia_veneta_k(self):
        # "diokan", "porko dio": la k veneta vale come c
        self.assertTrue(M.review("diokan").has_blasphemy)
        self.assertTrue(M.review("porko dio").has_blasphemy)

    def test_espressioni_fisse(self):
        self.assertTrue(M.review("madonnaccia").has_blasphemy)
        self.assertTrue(M.review("dea madonna").has_blasphemy)
        self.assertTrue(M.review("dea madona").has_blasphemy)

    def test_parolacce_venete(self):
        self.assertTrue(M.review("sei un cojone").has_profanity)
        self.assertTrue(M.review("che smerdata").has_profanity)


class TestNessunFalsoPositivo(unittest.TestCase):
    def test_parole_innocenti_restano_pulite(self):
        for t in ("ho una bella idea", "credo in Dio", "le dee greche",
                  "un negroamaro buonissimo", "la madonna di Loreto",
                  "che bella serata"):
            self.assertTrue(M.review(t).clean, f"falso positivo: {t}")


if __name__ == "__main__":
    unittest.main()
