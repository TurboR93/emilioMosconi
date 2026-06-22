"""Test della censura via BIP sull'audio.

Modello: il cervello NON riformula; il supervisore individua le parti sporche e
la voce le copre con un bip. La censura è disattivabile dall'amministratore.
I test di logica girano offline (nessuna rete, nessuna chiave); il test ffmpeg
è saltato se ffmpeg non è installato.
"""

import contextlib
import io
import os
import shutil
import subprocess
import tempfile
import unittest

from emilio import audio_bip
from emilio.agent import EmilioAgent
from emilio.brain import MockBrain
from emilio.config import EmilioConfig
from emilio.moderation import Moderator
from emilio.speech import MockSpeaker


class TestLogicaSpan(unittest.TestCase):
    def test_mappa_caratteri_su_tempo(self):
        cs = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
        ce = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
        # span di caratteri [1,3) -> tempo [0.1, 0.3]
        self.assertEqual(audio_bip.intervalli_da_allineamento([(1, 3)], cs, ce),
                         [(0.1, 0.3)])

    def test_fonde_intervalli_contigui(self):
        self.assertEqual(audio_bip.fondi_intervalli([(0.0, 0.2), (0.21, 0.4)]),
                         [(0.0, 0.4)])

    def test_span_fuori_limite_ignorati(self):
        cs = [0.0, 0.1]
        ce = [0.1, 0.2]
        self.assertEqual(audio_bip.intervalli_da_allineamento([(5, 9)], cs, ce), [])

    def test_applica_span_e_testo_sicuro(self):
        self.assertEqual(audio_bip.applica_span("sei uno stronzo", [(8, 15)], "[BIP]"),
                         "sei uno [BIP]")
        self.assertNotIn("stronzo", audio_bip.testo_sicuro("sei uno stronzo", [(8, 15)]))

    def test_filtro_vuoto(self):
        self.assertIsNone(audio_bip.costruisci_filtro([]))

    def test_filtro_non_vuoto(self):
        f = audio_bip.costruisci_filtro([(0.5, 1.0)])
        self.assertIn("volume=enable", f)
        self.assertIn("amix=inputs=2", f)

    def test_beep_pacchettizzato_presente(self):
        self.assertTrue(audio_bip.beep_disponibili(), "manca il bip in assets/beeps/")


class TestModeratorBip(unittest.TestCase):
    def test_span_e_testo_con_bip(self):
        mod = Moderator()
        rep = mod.review("sei uno stronzo")
        self.assertTrue(mod.span_censura(rep))                 # c'è qualcosa da bippare
        self.assertIn("[BIP]", mod.testo_con_bip("sei uno stronzo", rep))

    def test_disattivato_niente_span(self):
        mod = Moderator(enabled=False)
        rep = mod.review("sei uno stronzo")
        self.assertEqual(mod.span_censura(rep), [])            # admin OFF -> niente bip
        self.assertEqual(mod.testo_con_bip("sei uno stronzo", rep), "sei uno stronzo")
        self.assertTrue(rep.has_profanity)                     # ma il report c'è (log)

    def test_pulito_niente_span(self):
        mod = Moderator()
        rep = mod.review("buongiorno a tutti")
        self.assertEqual(mod.span_censura(rep), [])


class TestPipelineCensura(unittest.TestCase):
    def _agente(self, naughty):
        cfg = EmilioConfig()  # voce mock, attuatori mock, supervisione ON
        return EmilioAgent(cfg, brain=MockBrain(naughty=naughty, seed=0))

    def test_frase_sporca_viene_bippata(self):
        ag = self._agente(naughty=True)
        ris = ag.parla("dimmi qualcosa")
        self.assertTrue(ris.censura_applicata)
        self.assertTrue(ris.span_censura)
        self.assertIn("[BIP]", ris.testo_detto)

    def test_admin_disattiva_il_bip(self):
        ag = self._agente(naughty=True)
        ag.set_moderazione(False)
        ris = ag.parla("dimmi qualcosa")
        self.assertFalse(ris.censura_applicata)
        self.assertEqual(ris.span_censura, [])
        self.assertEqual(ris.testo_detto, ris.testo_grezzo)   # audio grezzo, nessun bip

    def test_frase_pulita_nessuna_censura(self):
        ag = self._agente(naughty=False)
        ris = ag.parla("come va")
        self.assertFalse(ris.censura_applicata)
        self.assertEqual(ris.span_censura, [])


class TestMockSpeakerBip(unittest.TestCase):
    def test_mostra_bip_e_conta_caratteri_originali(self):
        sp = MockSpeaker()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            m = sp.say("sei uno stronzo", bleep_spans=[(8, 15)])
        self.assertIn("[BIP]", buf.getvalue())
        self.assertNotIn("stronzo", buf.getvalue())
        self.assertEqual(m.caratteri, len("sei uno stronzo"))


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg non installato")
class TestSpliceFfmpeg(unittest.TestCase):
    def test_applica_bip_produce_audio(self):
        d = tempfile.mkdtemp()
        sample = os.path.join(d, "sample.wav")
        out = os.path.join(d, "out.wav")
        # 1.0s di tono come finto "parlato"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=300:duration=1.0",
             "-ac", "1", sample],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
        )
        beep = audio_bip.scegli_beep()
        ok = audio_bip.applica_bip(sample, [(0.2, 0.5)], beep, out)
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(out))


if __name__ == "__main__":
    unittest.main()
