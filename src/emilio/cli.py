"""Console di controllo manuale di Emilio.

Avvio:
    python -m emilio                                  # mock, offline (nessuna chiave)
    EMILIO_LLM=local python -m emilio                 # cervello locale (Ollama/gemma)
    EMILIO_PERSONA=tools/persona_veterano.json python -m emilio   # un'altra persona

PARLARE
    <testo>                 scrivi e premi invio: parli con Emilio (a TESTO)
    /conversa [secondi]     CONVERSAZIONE A VOCE a mani libere (parli e ti risponde)
    /ascolta [secondi]      parla a voce UNA volta sola
    /di <testo>             fagli dire una frase esatta (prova voce/bip)

CAMBIARE AL VOLO (senza riavviare) — senza argomenti compare un MENU numerato
    /cervello [..]                 scegli il "cervello": mock|local|claude|cloud
    /modello [nome]                scegli il modello LLM (menu, o nome diretto)
    /persona [nome|file]           scegli la personalità (menu, o nome diretto)
    /voce [nome]                   scegli la voce (menu) · /voce test [testo]
    /censura on|off                bip delle bestemmie on/off
    /streaming on|off              parla a frasi (on) o a blocco unico (off)

LATENZA / CAMPIONAMENTO (a caldo, senza azzerare la memoria)
    /think off|adaptive            Claude: off = veloce (Haiku) · adaptive = più qualità
    /lunghezza [n]                 lunghezza max risposta (max_tokens): corta = più rapida
    /provider [groq|openrouter|openai|<url>]   endpoint del cervello cloud
    /temp [n]                      varietà/creatività (local/cloud; es. 0.6)

ALTRO
    /verboso on|off         MONITOR: mostra in tempo reale il testo che sta per dire (💬)
    /stato                  mostra la configurazione attuale
    /occhi [espressione]    cambia gli occhi (senza arg: elenca) · /occhi guarda <dir>
    /muovi <azione> [val]   muovi il robottino  ·  /azioni per l'elenco
    /mod <testo>            analizza un testo col supervisore (debug)
    /reset                  azzera la memoria della conversazione
    /aiuto                  questo aiuto        ·        /esci  per uscire
"""

from __future__ import annotations

import os
import sys

from .actuators import MOVES
from .agent import EmilioAgent, _nome_persona, _nome_provider
from .config import EmilioConfig
from .moderation import default_moderator
from .occhi import ESPRESSIONI
from .persona import Persona


AIUTO = __doc__


def _stato_testo(agent: EmilioAgent, config: EmilioConfig) -> str:
    """Riga compatta con la configurazione attiva (cervello, persona, voce...)."""
    return (
        f"Cervello: {agent.descrizione_cervello()} | Persona: {agent.persona_nome} | "
        f"Voce: {agent.voce_attiva} | Occhi: {config.eyes_backend} | "
        f"Ascolto: {config.stt_backend} | "
        f"Pipeline: {'streaming' if agent.streaming else 'blocco'} | "
        f"BIP: {'ON' if agent.moderazione_attiva else 'OFF'} | "
        f"Monitor: {'ON' if agent.verboso else 'OFF'}"
    )


def _dettagli_testo(agent: EmilioAgent, config: EmilioConfig) -> str:
    """Manopole di latenza/campionamento del cervello attivo (per /stato)."""
    parti = [f"MaxTok {config.max_tokens}"]
    b = agent.backend_cervello
    if b == "claude":
        parti.append(f"Think {config.claude_think or 'off'}")
    elif b == "cloud":
        parti.append(f"Provider {_nome_provider(config.cloud_llm_url)}")
        parti.append(f"Temp {config.cloud_llm_temp}")
    elif b == "local":
        parti.append(f"Temp {config.local_llm_temp}")
    return "Latenza: " + " | ".join(parti)


def _banner(agent: EmilioAgent, config: EmilioConfig) -> None:
    """Schermata d'avvio: stato + le azioni principali, ben in chiaro."""
    print("============================================================")
    print("  E M I L I O   ·   console di controllo")
    print("============================================================")
    print(_stato_testo(agent, config))
    print()
    print("COSA PUOI FARE:")
    print("  • scrivi e premi invio    →  parli con Emilio (a testo)")
    print("  • /conversa               →  conversazione a VOCE (mani libere)")
    print("  • /cervello               →  scegli il cervello (menu): mock · local · claude · cloud")
    print("  • /modello                →  scegli il modello da un menu numerato")
    print("  • /persona                →  scegli la personalità da un menu numerato")
    print("  • /voce                   →  scegli la voce da un menu numerato")
    print("  • /aiuto                  →  tutti i comandi        ·    /esci  per uscire")
    print()


def _lista_persone() -> list[str]:
    """Nomi brevi delle persona disponibili: 'default' + i file persona_*.json."""
    import glob
    nomi = ["default"]
    trovati = sorted(glob.glob(os.path.join("tools", "persona_*.json"))
                     + glob.glob("persona_*.json"))
    for p in trovati:
        n = _nome_persona(p)
        if n not in nomi:
            nomi.append(n)
    return nomi


def _risolvi_persona(arg: str) -> tuple[Persona, str]:
    """Da un nome/percorso a (Persona, etichetta). 'default' = persona di serie.

    Un nome semplice (es. 'veterano') viene cercato come
    tools/persona_veterano.json, persona_veterano.json, veterano.json.
    """
    if arg.lower() in ("default", "base", "emilio"):
        return Persona(), "default"
    if arg.endswith(".json"):
        candidati = [arg]
    else:
        candidati = [
            os.path.join("tools", f"persona_{arg}.json"),
            f"persona_{arg}.json",
            f"{arg}.json",
            os.path.join("tools", f"{arg}.json"),
        ]
    for c in candidati:
        if os.path.isfile(c):
            return Persona.from_json(c), _nome_persona(c)
    raise ValueError(
        f"Persona '{arg}' non trovata. Disponibili: {', '.join(_lista_persone())} "
        f"(oppure indica un file .json).")


def _scegli(titolo: str, opzioni: list[str], attivo: str | None = None) -> str | None:
    """Menu numerato interattivo: stampa le opzioni e legge la scelta (numero o
    nome). Ritorna l'opzione scelta, o None se l'utente annulla (invio vuoto)."""
    if not opzioni:
        return None
    print(titolo)
    for i, o in enumerate(opzioni, 1):
        print(f"  {i}) {o}" + ("   ← attivo" if o == attivo else ""))
    try:
        scelta = input("Scegli (numero o nome, vuoto = annulla) > ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    if not scelta:
        return None
    if scelta.isdigit():
        i = int(scelta)
        if 1 <= i <= len(opzioni):
            return opzioni[i - 1]
        print("Numero fuori elenco.")
        return None
    return scelta            # nome libero: anche fuori elenco (per i power user)


def _ollama_modelli() -> list[str]:
    """Modelli scaricati su Ollama (best-effort; [] se Ollama non c'è)."""
    try:
        import subprocess
        out = subprocess.run(["ollama", "list"], capture_output=True,
                             text=True, timeout=5)
    except Exception:
        return []
    if out.returncode != 0 or not out.stdout.strip():
        return []
    return [r.split()[0] for r in out.stdout.strip().splitlines()[1:] if r.split()]


# Sottostringhe di id che NON sono modelli di chat (TTS/STT/embeddings/immagini/
# moderation): le API /models dei provider li mescolano ai modelli di chat —
# qui li scartiamo, così il menu resta pulito.
_NON_CHAT = ("whisper", "tts", "embed", "dall-e", "dalle", "moderation",
             "guard", "rerank", "stable-diffusion", "sdxl", "flux", "sora",
             "transcribe", "gpt-image", "playai", "bge-")


def _cloud_modelli(url: str, key: str) -> list[str]:
    """Modelli LIVE dal provider cloud via API OpenAI-compatibile
    `GET {url}/models` (Groq/OpenRouter/OpenAI/...). Così l'elenco si aggiorna da
    solo quando il provider aggiunge modelli. Scarta le voci non-chat
    (whisper/tts/embeddings...). [] se rete/chiave non disponibili."""
    try:
        import requests
        headers = {"authorization": f"Bearer {key}"} if key else {}
        r = requests.get(url.rstrip("/") + "/models", headers=headers, timeout=6)
        r.raise_for_status()
        dati = r.json().get("data") or []
        ids = [m["id"] for m in dati if isinstance(m, dict) and m.get("id")]
        chat = [i for i in ids if not any(s in i.lower() for s in _NON_CHAT)]
        return sorted(chat or ids)         # se il filtro azzera tutto, torna grezzo
    except Exception:
        return []


def _claude_modelli() -> list[str]:
    """Modelli Claude LIVE dalla Models API di Anthropic (`client.models.list()`),
    filtrati ai `claude-*`. Si aggiorna da solo coi nuovi modelli. [] senza SDK/chiave."""
    try:
        import anthropic
        client = anthropic.Anthropic()
        return [m.id for m in client.models.list()
                if str(getattr(m, "id", "")).startswith("claude")]
    except Exception:
        return []


# Suggerimenti curati per i backend che non hanno un elenco "vivo".
_MODELLI_CLAUDE = ["claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-8"]
_MODELLI_CLOUD = {
    "groq": ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"],
    "openai": ["gpt-4o-mini", "gpt-4o"],
    "openrouter": ["meta-llama/llama-3.3-70b-instruct", "google/gemini-2.0-flash-001"],
}


def _modello_attuale(agent: EmilioAgent) -> str | None:
    return {"local": agent.config.local_llm_model,
            "claude": agent.config.model,
            "cloud": agent.config.cloud_llm_model}.get(agent.backend_cervello)


def _modelli_disponibili(agent: EmilioAgent) -> list[str]:
    """Lista di modelli scegliibili per il cervello attivo (vuota su mock).

    Si aggiorna DA SOLA: local → `ollama list`; cloud → `GET /models` del provider;
    claude → Models API di Anthropic. Se la fonte live non è raggiungibile
    (offline/senza chiave) si ripiega sui suggerimenti curati (_MODELLI_*).
    Il modello attuale è sempre incluso (in testa) anche se fuori elenco.
    """
    b = agent.backend_cervello
    if b == "local":
        nomi = _ollama_modelli()
    elif b == "claude":
        nomi = _claude_modelli() or list(_MODELLI_CLAUDE)
    elif b == "cloud":
        vivi = _cloud_modelli(agent.config.cloud_llm_url, agent.config.cloud_llm_key)
        # Alcuni provider (es. OpenRouter) ne hanno centinaia: tetto per il menu,
        # gli altri restano raggiungibili scrivendo il nome.
        nomi = vivi[:60] if vivi else list(
            _MODELLI_CLOUD.get(_nome_provider(agent.config.cloud_llm_url), []))
    else:
        return []
    attuale = _modello_attuale(agent)
    if attuale and attuale not in nomi:
        nomi.insert(0, attuale)
    return nomi


def _rispondi(agent: EmilioAgent, testo: str) -> None:
    """Fa rispondere Emilio con la pipeline attiva (streaming o blocco) e
    stampa il riepilogo di emozione/latenza/censura. In modalità monitor
    (`agent.verboso`) mostra IN TEMPO REALE il testo che sta per dire, frase per
    frase. Un errore del cervello (Ollama spento, modello non scaricato, rete)
    non deve far cadere la sessione."""
    # Monitor: stampa ogni frase (già bippata) appena prima che venga pronunciata.
    su_frase = (lambda f: print(f"   💬 {f}")) if agent.verboso else None
    try:
        ris = agent.rispondi(testo, su_frase=su_frase)
    except Exception as e:
        print(f"⚠️  {e}")
        return
    voce = f" | {ris.voce}" if ris.voce else ""
    etichetta = "TTFT" if agent.streaming else "latenza LLM"
    print(f"   [emozione: {ris.emozione} | {etichetta}: {ris.latenza_llm*1000:.0f}ms{voce}]")
    if ris.censura_applicata:
        print(f"   [supervisore: {ris.report.summary()} | bip: {len(ris.span_censura)}]")
    elif agent.verboso:
        print(f"   [supervisore: {ris.report.summary() or 'niente da bippare'}]")


def _stampa_azioni() -> None:
    print("Movimenti disponibili:")
    for nome, descr in MOVES.items():
        print(f"  {nome:<12} {descr}")


def _comando(agent: EmilioAgent, linea: str) -> bool:
    """Gestisce un comando '/...'. Ritorna False se bisogna uscire."""
    parti = linea.split()
    cmd = parti[0].lower()
    args = parti[1:]

    if cmd in ("/esci", "/quit", "/exit"):
        return False

    if cmd in ("/aiuto", "/help"):
        print(AIUTO)
    elif cmd == "/stato":
        print(_stato_testo(agent, agent.config))
        print(_dettagli_testo(agent, agent.config))
    elif cmd == "/cervello":
        scelto = args[0] if args else _scegli(
            "Cervelli (mock=finto · local=Ollama · claude=Anthropic · cloud=Groq/OpenRouter/OpenAI):",
            ["mock", "local", "claude", "cloud"], attivo=agent.backend_cervello)
        if scelto:
            try:
                print(f"✅ Cervello: {agent.set_cervello(scelto)}  (memoria azzerata)")
            except Exception as e:
                print(f"⚠️  {e}")
    elif cmd in ("/modello", "/modelli"):
        # senza argomenti: menu numerato; con argomento: scelta diretta (nome).
        scelto = args[0] if args else _scegli(
            f"Modelli per il cervello '{agent.backend_cervello}':",
            _modelli_disponibili(agent), attivo=_modello_attuale(agent))
        if scelto is None and not args:
            if not _modelli_disponibili(agent):
                print(f"Modello attivo: {agent.descrizione_cervello()}. "
                      "Il modello si cambia col cervello local/claude/cloud.")
        elif scelto:
            try:
                print(f"✅ Cervello: {agent.set_modello(scelto)}  (memoria azzerata)")
            except Exception as e:
                print(f"⚠️  {e}")
    elif cmd in ("/persona", "/persone"):
        scelto = args[0] if args else _scegli(
            "Personalità disponibili:", _lista_persone(), attivo=agent.persona_nome)
        if scelto:
            try:
                persona, origine = _risolvi_persona(scelto)
                agent.set_persona(persona, origine)
                print(f"✅ Persona attiva: {origine} — \"{persona.nome}\" "
                      f"({persona.eta}).  Memoria azzerata.")
            except Exception as e:
                print(f"⚠️  {e}")
    elif cmd == "/think":
        if not args:
            print(f"Think (Claude): {agent.config.claude_think or 'off'}. "
                  "Uso: /think off|adaptive  (off=veloce/Haiku, adaptive=più qualità)")
        else:
            try:
                v = agent.set_think(args[0])
                print(f"✅ Think (Claude): {v}")
            except Exception as e:
                print(f"⚠️  {e}")
    elif cmd in ("/lunghezza", "/maxtoken", "/lung"):
        if not args:
            print(f"Lunghezza max (max_tokens): {agent.config.max_tokens}. "
                  "Uso: /lunghezza <numero>  (corta = più rapida)")
        else:
            try:
                print(f"✅ Lunghezza max: {agent.set_max_tokens(int(args[0]))} token")
            except Exception as e:
                print(f"⚠️  {e}")
    elif cmd in ("/temp", "/temperatura"):
        if not args:
            print("Uso: /temp <numero>  (es. 0.6 = più sobrio, 1.0 = più vario; "
                  "vale per local/cloud)")
        else:
            try:
                print(f"✅ Temperatura: {agent.set_temperatura(float(args[0]))}")
            except Exception as e:
                print(f"⚠️  {e}")
    elif cmd == "/provider":
        if not args:
            print(f"Provider cloud: {_nome_provider(agent.config.cloud_llm_url)} "
                  f"({agent.config.cloud_llm_url})")
            print("Uso: /provider groq|openrouter|openai|<url>")
        else:
            try:
                url = agent.set_provider(args[0])
                print(f"✅ Provider cloud: {_nome_provider(url)} ({url})")
            except Exception as e:
                print(f"⚠️  {e}")
    elif cmd == "/azioni":
        _stampa_azioni()
    elif cmd == "/muovi":
        if not args:
            print("Uso: /muovi <azione> [valore]")
        else:
            valore = float(args[1]) if len(args) > 1 else 1.0
            try:
                agent.muovi(args[0], valore)
            except Exception as e:
                print(f"⚠️  {e}")
    elif cmd == "/occhi":
        if not args:
            print("Espressioni disponibili:")
            for nome, (colore, descr) in ESPRESSIONI.items():
                print(f"  {nome:<12} {colore}  {descr}")
            print("Uso: /occhi <espressione> | /occhi guarda <direzione>")
        elif args[0] == "guarda":
            try:
                agent.guarda(args[1] if len(args) > 1 else "centro")
            except Exception as e:
                print(f"⚠️  {e}")
        else:
            try:
                s = agent.set_occhi(args[0])
                print(f"👀 Occhi: {s.espressione} ({s.colore})")
            except Exception as e:
                print(f"⚠️  {e}")
    elif cmd == "/di":
        if args:
            m = agent.di(" ".join(args))
            print(f"   [{m}]")
        else:
            print("Uso: /di <testo>")
    elif cmd == "/voci":
        print(f"Voce attiva: {agent.voce_attiva}")
        for p in agent.lista_voci():
            attiva = "→" if p.name == agent.voce_attiva else " "
            print(f" {attiva} {p.name:<12} [{p.backend}] {p.descrizione}")
    elif cmd == "/voce":
        if args and args[0] == "test":
            frase = " ".join(args[1:]) or "Buongiorno, sono Emilio. Come va oggi?"
            m = agent.di(frase)
            print(f"   [{m}]")
        else:
            scelto = args[0] if args else _scegli(
                "Voci disponibili:", [p.name for p in agent.lista_voci()],
                attivo=agent.voce_attiva)
            if scelto:
                try:
                    p = agent.set_voce(scelto)
                    print(f"✅ Voce attiva: {p.name} ({p.descrizione})")
                except ValueError as e:
                    print(f"⚠️  {e}")
    elif cmd == "/ascolta":
        sec = None
        if args:
            try:
                sec = float(args[0])
            except ValueError:
                pass
        print("🎤 Ascolto... parla pure (poi attendi la trascrizione).")
        try:
            testo = agent.ascolta(sec)
        except Exception as e:
            print(f"⚠️  microfono/STT non disponibile: {e}")
            return True
        print(f"🎤 Hai detto: {testo!r}")
        if testo.strip():
            _rispondi(agent, testo)
    elif cmd == "/conversa":
        sec = None
        if args:
            try:
                sec = float(args[0])
            except ValueError:
                pass
        print("🎤 Modalità voce a MANI LIBERE. Parla quando vuoi; "
              "di' 'basta' (o Ctrl-C) per uscire.")
        try:
            while True:
                print("🎤 Parla ora…")
                try:
                    testo = agent.ascolta(sec)
                except Exception as e:
                    print(f"⚠️  microfono/STT non disponibile: {e}")
                    break
                if not testo.strip():
                    print("   (non ho sentito niente, riprova)")
                    continue
                print(f"🎤 Hai detto: {testo!r}")
                low = testo.lower()
                if any(w in low for w in ("basta", "esci", "ferma", "stop", "arrivederci")):
                    print("Ok, smetto di ascoltare.")
                    break
                if not testo.strip():
                    continue
                _rispondi(agent, testo)
        except KeyboardInterrupt:
            print("\n(uscito dalla modalità voce)")
    elif cmd == "/streaming":
        sub = args[0].lower() if args else "stato"
        if sub == "on":
            agent.set_streaming(True)
            print("✅ Pipeline STREAMING attiva (parla frase per frase).")
        elif sub == "off":
            agent.set_streaming(False)
            print("✅ Pipeline a BLOCCO UNICO attiva (genera tutto, poi parla).")
        else:
            print(f"Pipeline: {'streaming' if agent.streaming else 'blocco unico'}")
    elif cmd in ("/verboso", "/monitor", "/log"):
        sub = args[0].lower() if args else "toggle"
        if sub in ("on", "off"):
            agent.verboso = (sub == "on")
        elif sub == "toggle":
            agent.verboso = not agent.verboso
        else:
            print(f"Monitor: {'ON' if agent.verboso else 'OFF'}. Uso: /verboso on|off")
            return True
        stato = "ON" if agent.verboso else "OFF"
        extra = " — vedi in tempo reale ciò che sta per dire (💬)" if agent.verboso else ""
        print(f"✅ Monitor (verboso): {stato}{extra}")
    elif cmd == "/censura":
        sub = args[0].lower() if args else "stato"
        if sub == "on":
            agent.set_moderazione(True)
            print("✅ Supervisione ATTIVA.")
        elif sub == "off":
            agent.set_moderazione(False)
            print("⚠️  Supervisione DISATTIVATA (Emilio può dire di tutto).")
        else:
            stato = "ATTIVA" if agent.moderazione_attiva else "DISATTIVATA"
            print(f"Supervisione: {stato}")
    elif cmd == "/mod":
        testo = " ".join(args)
        rep = default_moderator.review(testo)
        print(f"Analisi: {rep.summary()}")
        if not rep.clean:
            print(f"Ripulito: {default_moderator.sanitize(testo, rep)}")
    elif cmd == "/reset":
        agent.reset()
        print("Memoria azzerata.")
    else:
        print(f"Comando sconosciuto: {cmd}. Digita /aiuto.")
    return True


def main(argv: list[str] | None = None) -> int:
    config = EmilioConfig()
    agent = EmilioAgent(config)

    _banner(agent, config)

    while True:
        try:
            linea = input("tu> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not linea:
            continue
        if linea.startswith("/"):
            if not _comando(agent, linea):
                break
        else:
            _rispondi(agent, linea)

    print("Alla prossima!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
