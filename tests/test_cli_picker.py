"""Test del menu numerato di selezione (modelli/persone/cervello/voce) — offline.
`_scegli` legge da input(): lo mockiamo; gli elenchi sono logica pura."""

import unittest
from unittest.mock import patch

from emilio.agent import EmilioAgent
from emilio.cli import _modelli_disponibili, _modello_attuale, _scegli
from emilio.config import EmilioConfig


class TestScegli(unittest.TestCase):
    def test_per_numero(self):
        with patch("builtins.input", return_value="2"):
            self.assertEqual(_scegli("t", ["a", "b", "c"]), "b")

    def test_per_nome(self):
        with patch("builtins.input", return_value="veterano"):
            self.assertEqual(_scegli("t", ["default", "veterano"]), "veterano")

    def test_vuoto_annulla(self):
        with patch("builtins.input", return_value=""):
            self.assertIsNone(_scegli("t", ["a", "b"]))

    def test_numero_fuori_range(self):
        with patch("builtins.input", return_value="9"):
            self.assertIsNone(_scegli("t", ["a", "b"]))

    def test_eof_annulla(self):
        with patch("builtins.input", side_effect=EOFError):
            self.assertIsNone(_scegli("t", ["a", "b"]))

    def test_lista_vuota(self):
        self.assertIsNone(_scegli("t", []))


class TestModelliDisponibili(unittest.TestCase):
    def _agente(self, backend) -> EmilioAgent:
        a = EmilioAgent(EmilioConfig())
        a.config.llm_backend = backend       # solo per leggere backend_cervello
        return a

    def test_claude_suggeriti(self):
        # senza SDK/chiave usa il fallback curato; con la Models API usa i live:
        # in entrambi i casi devono essere modelli 'claude-*'.
        m = _modelli_disponibili(self._agente("claude"))
        self.assertTrue(m)
        self.assertTrue(any(x.startswith("claude") for x in m))

    def test_cloud_groq_con_attuale_in_testa(self):
        a = self._agente("cloud")
        a.config.cloud_llm_model = "mio-modello-custom"
        m = _modelli_disponibili(a)
        self.assertEqual(m[0], "mio-modello-custom")   # l'attuale è sempre incluso
        self.assertIn("llama-3.1-8b-instant", m)

    def test_mock_nessun_modello(self):
        self.assertEqual(_modelli_disponibili(EmilioAgent(EmilioConfig())), [])

    def test_modello_attuale(self):
        a = self._agente("local")
        self.assertEqual(_modello_attuale(a), a.config.local_llm_model)


if __name__ == "__main__":
    unittest.main()
