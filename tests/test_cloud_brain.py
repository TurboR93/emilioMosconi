"""Test del cervello cloud generico (OpenAI-compatibile) e della taratura
latenza di Claude — tutto OFFLINE: nessuna rete, nessun SDK, nessuna chiave.

CloudBrain importa `requests` solo dentro reply/reply_stream (import pigro), e il
suo costruttore non tocca la rete: si può istanziare e ispezionare il payload
senza chiamare nessun provider. La logica thinking/effort di Claude è in una
funzione pura (`_claude_extra_kwargs`), testabile senza il pacchetto anthropic."""

import unittest
from unittest.mock import patch

from emilio.agent import EmilioAgent
from emilio.brain import CloudBrain, _claude_extra_kwargs, build_brain
from emilio.config import EmilioConfig
from emilio.persona import Persona


class TestClaudeThinking(unittest.TestCase):
    def test_off_non_manda_nulla(self):
        # default (off): niente thinking/effort -> richiesta minima, ok con Haiku
        self.assertEqual(_claude_extra_kwargs("", "medium"), {})
        self.assertEqual(_claude_extra_kwargs("off", "high"), {})

    def test_adaptive_manda_thinking_e_effort(self):
        kw = _claude_extra_kwargs("adaptive", "high")
        self.assertEqual(kw["thinking"], {"type": "adaptive"})
        self.assertEqual(kw["output_config"], {"effort": "high"})

    def test_build_brain_passa_think(self):
        # build_brain instrada 'claude' a ClaudeBrain passando il think; non lo
        # costruiamo davvero (richiede anthropic+chiave). Verifichiamo che il
        # default di config sia 'off'.
        cfg = EmilioConfig()
        self.assertEqual(cfg.claude_think, "")


class TestCloudPayload(unittest.TestCase):
    def _brain(self) -> CloudBrain:
        return CloudBrain(persona=Persona(), base_url="https://api.groq.com/openai/v1/",
                          model="llama-3.1-8b-instant", max_tokens=220, api_key="x",
                          temperature=0.7)

    def test_payload_struttura(self):
        b = self._brain()
        b._messages.append({"role": "user", "content": "ciao"})
        p = b._payload(stream=True)
        self.assertEqual(p["model"], "llama-3.1-8b-instant")
        self.assertEqual(p["max_tokens"], 220)
        self.assertEqual(p["temperature"], 0.7)
        self.assertTrue(p["stream"])
        # il system prompt della persona è il PRIMO messaggio
        self.assertEqual(p["messages"][0]["role"], "system")
        self.assertIn("Emilio", p["messages"][0]["content"])
        self.assertEqual(p["messages"][-1], {"role": "user", "content": "ciao"})

    def test_payload_stream_flag(self):
        b = self._brain()
        self.assertFalse(b._payload(stream=False)["stream"])

    def test_base_url_normalizzato(self):
        # la slash finale va tolta (poi si concatena /chat/completions)
        self.assertEqual(self._brain().base_url, "https://api.groq.com/openai/v1")

    def test_headers_con_chiave(self):
        h = self._brain()._headers()
        self.assertEqual(h["authorization"], "Bearer x")

    def test_headers_senza_chiave(self):
        b = CloudBrain(api_key="")
        self.assertNotIn("authorization", b._headers())


class TestFactoryEAgente(unittest.TestCase):
    def test_build_brain_cloud(self):
        cfg = EmilioConfig()
        cfg.llm_backend = "cloud"
        cfg.cloud_llm_model = "llama-3.3-70b-versatile"
        b = build_brain(cfg, Persona())
        self.assertIsInstance(b, CloudBrain)
        self.assertEqual(b.model, "llama-3.3-70b-versatile")

    def test_agent_passa_a_cloud(self):
        a = EmilioAgent(EmilioConfig())          # default: mock
        d = a.set_cervello("cloud")
        self.assertEqual(a.backend_cervello, "cloud")
        self.assertIsInstance(a.brain, CloudBrain)
        self.assertTrue(d.startswith("cloud ("))

    def test_set_modello_su_cloud(self):
        a = EmilioAgent(EmilioConfig())
        a.set_cervello("cloud")
        d = a.set_modello("llama-3.1-8b-instant")
        self.assertEqual(d, "cloud (llama-3.1-8b-instant)")
        self.assertEqual(a.brain.model, "llama-3.1-8b-instant")


class TestManopoleLatenzaRuntime(unittest.TestCase):
    """I setter a caldo aggiornano config + cervello vivo SENZA azzerare la memoria."""

    def test_max_tokens_aggiorna_cervello_vivo(self):
        a = EmilioAgent(EmilioConfig())
        a.set_cervello("cloud")
        a.brain._messages.append({"role": "user", "content": "ciao"})  # memoria
        n = a.set_max_tokens(140)
        self.assertEqual(n, 140)
        self.assertEqual(a.config.max_tokens, 140)
        self.assertEqual(a.brain.max_tokens, 140)            # patch in-place
        self.assertEqual(len(a.brain._messages), 1)          # memoria preservata

    def test_max_tokens_invalido(self):
        a = EmilioAgent(EmilioConfig())
        with self.assertRaises(ValueError):
            a.set_max_tokens(0)

    def test_think_normalizza(self):
        a = EmilioAgent(EmilioConfig())
        self.assertEqual(a.set_think("adaptive"), "adaptive")
        self.assertEqual(a.config.claude_think, "adaptive")
        self.assertEqual(a.set_think("off"), "off")
        self.assertEqual(a.config.claude_think, "")
        with self.assertRaises(ValueError):
            a.set_think("forse")

    def test_temperatura_su_cloud(self):
        a = EmilioAgent(EmilioConfig())
        a.set_cervello("cloud")
        a.set_temperatura(0.4)
        self.assertEqual(a.config.cloud_llm_temp, 0.4)
        self.assertEqual(a.brain.temperature, 0.4)

    def test_temperatura_rifiutata_su_mock(self):
        a = EmilioAgent(EmilioConfig())          # mock: niente temperature
        with self.assertRaises(ValueError):
            a.set_temperatura(0.5)

    def test_provider_scorciatoia_e_url(self):
        a = EmilioAgent(EmilioConfig())
        a.set_cervello("cloud")
        a.set_provider("openrouter")
        self.assertEqual(a.config.cloud_llm_url, "https://openrouter.ai/api/v1")
        self.assertEqual(a.brain.base_url, "https://openrouter.ai/api/v1")
        a.set_provider("https://mio.endpoint/v1/")
        self.assertEqual(a.brain.base_url, "https://mio.endpoint/v1")  # slash tolta


class TestRollbackSeFallisce(unittest.TestCase):
    """Se build_brain fallisce (es. SDK/chiave mancante) lo stato non resta a metà."""

    def test_set_cervello_rollback(self):
        a = EmilioAgent(EmilioConfig())          # default: mock
        brain_prima = a.brain
        with patch("emilio.agent.build_brain", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                a.set_cervello("cloud")
        self.assertEqual(a.backend_cervello, "mock")
        self.assertIs(a.brain, brain_prima)

    def test_set_modello_rollback(self):
        a = EmilioAgent(EmilioConfig())
        a.set_cervello("cloud")
        modello_prima = a.config.cloud_llm_model
        with patch("emilio.agent.build_brain", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                a.set_modello("inesistente")
        self.assertEqual(a.config.cloud_llm_model, modello_prima)


if __name__ == "__main__":
    unittest.main()
