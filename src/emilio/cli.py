"""Console di controllo manuale di Emilio.

Avvio:
    python -m emilio                # modalità interattiva (mock, offline)
    EMILIO_LLM=local EMILIO_VOICE=offline python -m emilio

Comandi:
    <testo>                 parla con Emilio (LLM -> supervisore -> voce)
    /di <testo>             fai dire una frase esatta (passa dal supervisore)
    /voci                   elenca i profili voce disponibili
    /voce <nome>            cambia la voce attiva (es. /voce veloce)
    /voce test [testo]      prova la voce e misura la latenza
    /muovi <azione> [val]   muovi il robottino (manuale)
    /azioni                 elenca i movimenti disponibili
    /occhi [espressione]    cambia l'espressione degli occhi (senza arg: elenca)
    /occhi guarda <dir>     fai guardare gli occhi (centro/sinistra/destra/su/giu)
    /ascolta [secondi]      parla a VOCE una volta: registra dal microfono e risponde
    /conversa [secondi]     modalità voce a MANI LIBERE: parli e lui risponde, a giro
    /streaming on|off|stato pipeline voce: streaming (parla a frasi) o a blocco unico
    /censura on|off|stato   controllo amministratore della supervisione
    /mod <testo>            analizza un testo col supervisore (debug)
    /reset                  azzera la memoria della conversazione
    /aiuto                  mostra questo aiuto
    /esci                   esci
"""

from __future__ import annotations

import sys

from .actuators import MOVES
from .agent import EmilioAgent
from .config import EmilioConfig
from .moderation import default_moderator
from .occhi import ESPRESSIONI


AIUTO = __doc__


def _rispondi(agent: EmilioAgent, testo: str) -> None:
    """Fa rispondere Emilio con la pipeline attiva (streaming o blocco) e
    stampa il riepilogo di emozione/latenza/censura. Un errore del cervello
    (Ollama spento, modello non scaricato, rete) non deve far cadere la sessione."""
    try:
        ris = agent.rispondi(testo)
    except Exception as e:
        print(f"⚠️  {e}")
        return
    voce = f" | {ris.voce}" if ris.voce else ""
    etichetta = "TTFT" if agent.streaming else "latenza LLM"
    print(f"   [emozione: {ris.emozione} | {etichetta}: {ris.latenza_llm*1000:.0f}ms{voce}]")
    if ris.censura_applicata:
        print(f"   [supervisore: {ris.report.summary()} | bip: {len(ris.span_censura)}]")


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
        if not args:
            print(f"Voce attiva: {agent.voce_attiva}. Uso: /voce <nome> | /voce test [testo]")
        elif args[0] == "test":
            frase = " ".join(args[1:]) or "Buongiorno, sono Emilio. Come va oggi?"
            m = agent.di(frase)
            print(f"   [{m}]")
        else:
            try:
                p = agent.set_voce(args[0])
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

    backend = config.llm_backend or ("claude" if config.use_real_llm else "mock")
    if backend == "local":
        cervello = f"local ({config.local_llm_model})"
    elif backend == "claude":
        cervello = f"claude ({config.model})"
    else:
        cervello = backend
    print("=== Emilio è in linea ===")
    print(f"Cervello: {cervello} | Voce: {agent.voce_attiva} | "
          f"Occhi: {config.eyes_backend} | Ascolto: {config.stt_backend} | "
          f"Pipeline: {'streaming' if agent.streaming else 'blocco'} | "
          f"Supervisione (BIP): {'ON' if agent.moderazione_attiva else 'OFF'}")
    print("Digita /aiuto per i comandi, /ascolta per parlare a voce, /esci per uscire.\n")

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
