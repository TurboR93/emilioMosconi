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
            ris = agent.parla(testo)
            voce = f" | {ris.voce}" if ris.voce else ""
            print(f"   [emozione: {ris.emozione} | latenza LLM: {ris.latenza_llm*1000:.0f}ms{voce}]")
            if ris.censura_applicata:
                print(f"   [supervisore: {ris.report.summary()} | bip: {len(ris.span_censura)}]")
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
                ris = agent.parla(testo)
                voce = f" | {ris.voce}" if ris.voce else ""
                print(f"   [emozione: {ris.emozione} | latenza LLM: {ris.latenza_llm*1000:.0f}ms{voce}]")
                if ris.censura_applicata:
                    print(f"   [supervisore: {ris.report.summary()} | bip: {len(ris.span_censura)}]")
        except KeyboardInterrupt:
            print("\n(uscito dalla modalità voce)")
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

    cervello = config.llm_backend or ("claude" if config.use_real_llm else "mock")
    print("=== Emilio è in linea ===")
    print(f"Cervello: {cervello} | Voce: {agent.voce_attiva} | "
          f"Occhi: {config.eyes_backend} | Ascolto: {config.stt_backend} | "
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
            ris = agent.parla(linea)
            voce = f" | {ris.voce}" if ris.voce else ""
            print(f"   [emozione: {ris.emozione} | latenza LLM: {ris.latenza_llm*1000:.0f}ms{voce}]")
            if ris.censura_applicata:
                print(f"   [supervisore: {ris.report.summary()} | "
                      f"bip applicati: {len(ris.span_censura)}]")

    print("Alla prossima!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
