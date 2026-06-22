"""Movimento di Emilio: controllo (anche manuale) del robottino.

Vocabolario di movimenti pensato per un robottino semplice anni '90 (motori,
servocomandi, LED). Due backend:
  * MockMover   -> stampa i comandi (sviluppo/test)
  * SerialMover -> invia comandi via porta seriale (es. Arduino/driver motori
                   collegati a un Raspberry). Se pyserial non c'è, ripiega su
                   stampa così il resto della pipeline continua a funzionare.

Il protocollo seriale è volutamente banale e testuale, una riga per comando:
    MOVE <azione> <valore>\n
Così puoi implementare il firmware lato microcontrollore come preferisci.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

# Vocabolario dei movimenti: azione -> descrizione
MOVES: dict[str, str] = {
    "avanti": "vai avanti",
    "indietro": "vai indietro",
    "sinistra": "gira a sinistra",
    "destra": "gira a destra",
    "testa_su": "alza la testa",
    "testa_giu": "abbassa la testa",
    "testa_sx": "gira la testa a sinistra",
    "testa_dx": "gira la testa a destra",
    "braccio_su": "alza il braccio",
    "braccio_giu": "abbassa il braccio",
    "bocca": "muovi la bocca (per parlare)",
    "occhi_on": "accendi i LED degli occhi",
    "occhi_off": "spegni i LED degli occhi",
    "stop": "fermati",
}


class MoveError(ValueError):
    """Azione di movimento non valida."""


def validate(action: str) -> str:
    action = action.strip().lower()
    if action not in MOVES:
        raise MoveError(
            f"Movimento '{action}' sconosciuto. Disponibili: {', '.join(MOVES)}"
        )
    return action


class Mover(ABC):
    @abstractmethod
    def move(self, action: str, value: float = 1.0) -> None:
        ...

    def stop(self) -> None:
        self.move("stop")


class MockMover(Mover):
    def move(self, action: str, value: float = 1.0) -> None:
        action = validate(action)
        print(f"🤖 [Emilio muove] {MOVES[action]} (x{value})")


class SerialMover(Mover):
    def __init__(self, port: str = "/dev/ttyUSB0", baud: int = 9600):
        self.port = port
        self.baud = baud
        self._serial = None
        try:
            import serial  # import pigro (pyserial)
            self._serial = serial.Serial(port, baud, timeout=1)
        except Exception as e:  # pragma: no cover - dipende dall'hardware
            print(f"⚠️  Seriale non disponibile ({e}); uso modalità simulata.")

    def move(self, action: str, value: float = 1.0) -> None:
        action = validate(action)
        cmd = f"MOVE {action} {value}\n"
        if self._serial is not None:
            self._serial.write(cmd.encode("utf-8"))
        else:
            print(f"🤖 [seriale simulata] {cmd.strip()}")


def build_mover(config) -> Mover:
    """Factory: sceglie l'attuatore in base alla configurazione."""
    if config.actuator_backend.lower() == "serial":
        return SerialMover(port=config.serial_port, baud=config.serial_baud)
    return MockMover()
