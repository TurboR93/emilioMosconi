"""Test del cambio a runtime di cervello/modello/persona dalla console — tutto
offline, senza Ollama né rete (si resta sui backend 'mock' e 'local', che NON
contattano nulla in fase di costruzione)."""

import os
import unittest
from unittest.mock import patch

from emilio.agent import EmilioAgent, _nome_persona
from emilio.brain import LocalBrain, MockBrain
from emilio.cli import _lista_persone, _risolvi_persona
from emilio.config import EmilioConfig
from emilio.persona import Persona


def _agente_mock() -> EmilioAgent:
    # backend mock di default (EMILIO_LLM non impostato nei test)
    return EmilioAgent(EmilioConfig())


class TestNomePersona(unittest.TestCase):
    def test_default_se_vuoto(self):
        self.assertEqual(_nome_persona(None), "default")
        self.assertEqual(_nome_persona(""), "default")

    def test_toglie_prefisso_e_estensione(self):
        self.assertEqual(_nome_persona("tools/persona_germano.json"), "germano")
        self.assertEqual(_nome_persona("/x/y/persona_burbero.json"), "burbero")
        self.assertEqual(_nome_persona("mia.json"), "mia")


class TestCambioCervello(unittest.TestCase):
    def test_descrizione_iniziale_mock(self):
        a = _agente_mock()
        self.assertEqual(a.backend_cervello, "mock")
        self.assertEqual(a.descrizione_cervello(), "mock")
        self.assertIsInstance(a.brain, MockBrain)

    def test_passa_a_local_e_torna(self):
        a = _agente_mock()
        d = a.set_cervello("local")
        self.assertEqual(a.backend_cervello, "local")
        self.assertIn("local (", d)
        self.assertIsInstance(a.brain, LocalBrain)
        a.set_cervello("mock")
        self.assertIsInstance(a.brain, MockBrain)

    def test_backend_sconosciuto(self):
        a = _agente_mock()
        with self.assertRaises(ValueError):
            a.set_cervello("pippo")


class TestModelloClaudeDefault(unittest.TestCase):
    """Claude parte da Haiku (rapido/economico, TTFT basso per la voce); l'env
    EMILIO_CLAUDE_MODEL esplicito continua a vincere."""

    def test_default_e_haiku(self):
        self.assertEqual(EmilioConfig().claude_model, "claude-haiku-4-5")

    def test_env_esplicito_vince(self):
        # i default leggono os.environ all'import: per provare la precedenza
        # dell'env va ricaricato il modulo config sotto l'ambiente modificato.
        import importlib

        import emilio.config as cfgmod
        with patch.dict(os.environ, {"EMILIO_CLAUDE_MODEL": "claude-opus-4-8"}):
            importlib.reload(cfgmod)
            try:
                self.assertEqual(cfgmod.EmilioConfig().claude_model, "claude-opus-4-8")
            finally:
                importlib.reload(cfgmod)   # ripristina i default dall'ambiente reale


class TestCambioModello(unittest.TestCase):
    def test_su_local_cambia_modello(self):
        a = _agente_mock()
        a.set_cervello("local")
        d = a.set_modello("gemma2:9b")
        self.assertEqual(d, "local (gemma2:9b)")
        self.assertEqual(a.brain.model, "gemma2:9b")

    def test_su_mock_rifiuta(self):
        a = _agente_mock()
        with self.assertRaises(ValueError):
            a.set_modello("gemma2:9b")


class TestCambioPersona(unittest.TestCase):
    def test_set_persona_aggiorna_prompt_e_nome(self):
        a = _agente_mock()
        self.assertEqual(a.persona_nome, "default")
        nuova = Persona(biografia="Sei un VETERANO di prova.", eta="cento")
        a.set_persona(nuova, "prova")
        self.assertEqual(a.persona_nome, "prova")
        self.assertIs(a.persona, nuova)
        # il cervello ricostruito usa il nuovo system prompt
        self.assertIn("VETERANO di prova", a.brain.persona.system_prompt())

    def test_risolvi_default(self):
        persona, origine = _risolvi_persona("default")
        self.assertEqual(origine, "default")
        self.assertEqual(persona.eta, Persona().eta)

    def test_risolvi_germano_dal_file(self):
        # tools/persona_germano.json è versionato nel repo
        persona, origine = _risolvi_persona("germano")
        self.assertEqual(origine, "germano")
        self.assertIn("trevigiano", persona.eta.lower())   # vecchio veneto incazzato
        self.assertEqual(persona.voce, "germano")           # porta la sua voce

    def test_risolvi_inesistente(self):
        with self.assertRaises(ValueError):
            _risolvi_persona("non_esiste_questa_persona")

    def test_lista_include_default_e_germano(self):
        nomi = _lista_persone()
        self.assertIn("default", nomi)
        self.assertIn("germano", nomi)


class TestPersonaPortaLaSuaVoce(unittest.TestCase):
    """Una persona che dichiara `voce` impone quel profilo all'agente quando la
    si seleziona: il personaggio si porta dietro la sua voce."""

    def test_set_persona_attiva_la_voce_dichiarata(self):
        a = _agente_mock()
        a.set_voce("mock")
        nuova = Persona(biografia="Sei un vècio incazzà.", voce="germano")
        attivata = a.set_persona(nuova, "prova")
        self.assertEqual(attivata, "germano")
        self.assertEqual(a.voce_attiva, "germano")

    def test_voce_sconosciuta_non_cambia_nulla(self):
        a = _agente_mock()
        a.set_voce("mock")
        a.set_persona(Persona(voce="non_esiste"), "prova")
        self.assertEqual(a.voce_attiva, "mock")        # nessun cambio, best-effort

    def test_persona_senza_voce_lascia_quella_attiva(self):
        a = _agente_mock()
        a.set_voce("veloce")
        self.assertIsNone(a.set_persona(Persona(), "default"))
        self.assertEqual(a.voce_attiva, "veloce")

    def test_file_germano_dichiara_la_sua_voce(self):
        persona, _ = _risolvi_persona("germano")
        self.assertEqual(persona.voce, "germano")


if __name__ == "__main__":
    unittest.main()
