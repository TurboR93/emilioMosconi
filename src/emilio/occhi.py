"""Occhi di Emilio: gli occhi a LED, importantissimi per dargli espressione.

Stesso pattern degli altri componenti (ABC + factory + backend mock/reale):
  * OcchiMock    -> stampa lo stato (sviluppo/test, nessuna dipendenza)
  * OcchiPreview -> ANTEPRIMA locale: apre una paginetta nel browser che disegna
                    i due occhi e li aggiorna in tempo reale, così puoi vedere le
                    espressioni SENZA hardware. Usa solo la libreria standard
                    (http.server), coerente col "core senza dipendenze".
  * (futuro)     -> OcchiLed sul Raspberry, stesse chiamate via rete/GPIO.

Gli occhi hanno ESPRESSIONI (con un colore LED) e possono guardare in una
direzione o sbattere le palpebre. L'agente li pilota insieme a voce e movimento
(es. "parla" mentre parla, "ascolta" mentre ascolta).
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass


# Espressione -> (colore LED, descrizione). Palette DIABOLICA: toni rosso/fuoco.
ESPRESSIONI: dict[str, tuple[str, str]] = {
    "neutro":     ("#8B0000", "rosso cupo, calma minacciosa"),
    "felice":     ("#FF6A00", "ghigno diabolico"),
    "arrabbiato": ("#FF0000", "furia infernale"),
    "sorpreso":   ("#FF8C00", "occhi sbarrati, bagliore"),
    "triste":     ("#5A0010", "rosso spento"),
    "pensa":      ("#FF2A00", "fuoco che cova"),
    "parla":      ("#FF3B00", "bagliore mentre parla"),
    "ascolta":    ("#FF5555", "in agguato"),
    "spento":     ("#1A0000", "brace spenta"),
}

DIREZIONI = {"centro", "sinistra", "destra", "su", "giu"}


class OcchiError(ValueError):
    """Espressione o direzione non valida."""


def valida_espressione(nome: str) -> str:
    nome = nome.strip().lower()
    if nome not in ESPRESSIONI:
        raise OcchiError(
            f"Espressione '{nome}' sconosciuta. Disponibili: {', '.join(ESPRESSIONI)}"
        )
    return nome


@dataclass
class StatoOcchi:
    espressione: str = "neutro"
    colore: str = "#7CFC00"
    aperti: bool = True
    direzione: str = "centro"


class Occhi(ABC):
    """Base: tiene lo stato e offre i comandi; i backend implementano `_mostra`."""

    def __init__(self) -> None:
        self._stato = StatoOcchi()

    def imposta(self, espressione: str) -> StatoOcchi:
        espressione = valida_espressione(espressione)
        colore, _ = ESPRESSIONI[espressione]
        self._stato.espressione = espressione
        self._stato.colore = colore
        self._stato.aperti = espressione != "spento"
        self._mostra()
        return self._stato

    def guarda(self, direzione: str) -> None:
        direzione = direzione.strip().lower()
        if direzione not in DIREZIONI:
            raise OcchiError(
                f"Direzione '{direzione}' sconosciuta. Disponibili: {', '.join(DIREZIONI)}"
            )
        self._stato.direzione = direzione
        self._mostra()

    def lampeggia(self) -> None:
        """Un battito di palpebre."""
        self._stato.aperti = False
        self._mostra()
        time.sleep(0.12)
        self._stato.aperti = True
        self._mostra()

    def spegni(self) -> None:
        self.imposta("spento")

    @property
    def stato(self) -> StatoOcchi:
        return self._stato

    @abstractmethod
    def _mostra(self) -> None:
        ...


class OcchiMock(Occhi):
    """Stampa lo stato degli occhi (sviluppo/test)."""

    def _mostra(self) -> None:
        s = self._stato
        extra = "" if s.direzione == "centro" else f" →{s.direzione}"
        if not s.aperti and s.espressione != "spento":
            extra += " (chiusi)"
        print(f"👀 [occhi] {s.espressione} {s.colore}{extra}")


# ---------------------------------------------------------------------------
# Anteprima locale nel browser (solo stdlib: http.server)
# ---------------------------------------------------------------------------

_PAGINA = """<!doctype html><html lang="it"><head><meta charset="utf-8">
<title>Emilio — occhi</title>
<style>
 html,body{margin:0;height:100%;background:#070406;overflow:hidden}
 #faccia{display:block;margin:auto}
 #et{position:fixed;bottom:14px;left:0;right:0;text-align:center;
     color:#a33;font:600 18px system-ui,sans-serif;letter-spacing:.08em}
</style></head><body>
<canvas id="faccia" width="640" height="400"></canvas>
<div id="et">…</div>
<script>
const W=640,H=400,c=document.getElementById('faccia'),x=c.getContext('2d'),et=document.getElementById('et');
const OFF={centro:[0,0],sinistra:[-20,0],destra:[20,0],su:[0,-16],giu:[0,16]};
let S={espressione:'neutro',colore:'#8B0000',aperti:true,direzione:'centro'};

// Occhio diabolico: mandorla inclinata + pupilla a fessura + bagliore pulsante
function occhio(cx,cy,col,aperti,dir,rot,t){
  x.save();x.translate(cx,cy);x.rotate(rot);
  x.shadowColor=col;x.shadowBlur=45+18*Math.sin(t*3);
  const w=112,h=64;
  x.beginPath();x.moveTo(-w,0);x.quadraticCurveTo(0,-h,w,0);
  x.quadraticCurveTo(0,h*0.55,-w,0);x.closePath();
  x.fillStyle='#180003';x.fill();x.lineWidth=6;x.strokeStyle=col;x.stroke();
  if(aperti){const o=OFF[dir]||[0,0];x.shadowBlur=34;
    x.fillStyle=col;x.beginPath();x.ellipse(o[0],o[1],11,44,0,0,7);x.fill();
    x.fillStyle='#180003';x.beginPath();x.ellipse(o[0],o[1],3.5,30,0,0,7);x.fill();
  }else{x.lineWidth=7;x.beginPath();x.moveTo(-w,0);x.lineTo(w,0);x.stroke();}
  x.restore();
}

// Forca del diavolo (tridente) ANIMATA: al posto dell'occhio quando è arrabbiato
function forca(cx,cy,col,t){
  x.save();x.translate(cx,cy);x.rotate(Math.sin(t*5+cx)*0.06);  // tremolio
  x.shadowColor=col;x.shadowBlur=30+18*Math.abs(Math.sin(t*7));  // bagliore pulsante
  x.strokeStyle=col;x.fillStyle=col;x.lineWidth=9;x.lineCap='round';x.lineJoin='round';
  x.beginPath();x.moveTo(0,-40);x.lineTo(0,95);x.stroke();        // asta
  x.beginPath();x.moveTo(-34,-40);x.lineTo(34,-40);x.stroke();    // traversa
  x.beginPath();x.moveTo(0,-40);x.lineTo(0,-92);x.stroke();       // rebbio centrale
  x.beginPath();x.moveTo(-34,-40);x.quadraticCurveTo(-44,-78,-24,-92);x.stroke();
  x.beginPath();x.moveTo(34,-40);x.quadraticCurveTo(44,-78,24,-92);x.stroke();
  const tip=(px,py)=>{x.beginPath();x.moveTo(px-8,py+4);x.lineTo(px+8,py+4);x.lineTo(px,py-16);x.closePath();x.fill();};
  tip(0,-92);tip(-24,-92);tip(24,-92);                            // punte
  x.restore();
}

let t0=performance.now();
function frame(now){
  const t=(now-t0)/1000;
  x.clearRect(0,0,W,H);
  if(S.espressione==='arrabbiato'){
    forca(195,170,S.colore,t);forca(445,170,S.colore,t+0.4);
    et.textContent='ARRABBIATO  😈  '+S.colore;
  }else{
    occhio(195,185,S.colore,S.aperti,S.direzione,0.30,t);
    occhio(445,185,S.colore,S.aperti,S.direzione,-0.30,t);
    et.textContent=S.espressione.toUpperCase()+'  •  '+S.colore;
  }
  requestAnimationFrame(frame);
}
async function poll(){try{S=await(await fetch('/stato')).json();}catch(e){et.textContent='(in attesa di Emilio…)';}}
setInterval(poll,150);poll();requestAnimationFrame(frame);
</script></body></html>"""


class OcchiPreview(Occhi):
    """Anteprima locale: serve una pagina che disegna gli occhi e li aggiorna.

    Avvia un piccolo server http (solo stdlib) su 127.0.0.1:<porta>; la pagina
    interroga `/stato` e ridisegna. Se la porta è occupata, degrada a sola
    memoria (nessun crash) — gli altri componenti continuano a funzionare.
    """

    def __init__(self, port: int = 8473, apri_browser: bool = True) -> None:
        super().__init__()
        self.port = port
        self._server = None
        self._avvia(apri_browser)

    def _avvia(self, apri_browser: bool) -> None:
        import threading
        import webbrowser
        from functools import partial
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        stato_ref = self  # per la closure

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # silenzia il logging
                pass

            def _scrivi(self, body: bytes, ctype: str) -> None:
                self.send_response(200)
                self.send_header("content-type", ctype)
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except BrokenPipeError:
                    pass

            def do_GET(self):
                import json
                if self.path == "/" or self.path.startswith("/index"):
                    self._scrivi(_PAGINA.encode("utf-8"), "text/html; charset=utf-8")
                elif self.path.startswith("/stato"):
                    body = json.dumps(asdict(stato_ref._stato)).encode("utf-8")
                    self._scrivi(body, "application/json")
                else:
                    self.send_response(404)
                    self.end_headers()

        try:
            self._server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        except OSError as e:
            print(f"⚠️  Anteprima occhi non avviata (porta {self.port}: {e}); "
                  f"uso solo memoria.")
            return
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{self.port}/"
        print(f"👀 Anteprima occhi su {url}")
        if apri_browser:
            try:
                webbrowser.open(url)
            except Exception:
                pass

    def _mostra(self) -> None:
        # La pagina interroga /stato e legge direttamente self._stato: niente da fare.
        pass


def build_occhi(config) -> Occhi:
    """Factory: sceglie il backend degli occhi in base alla configurazione."""
    backend = getattr(config, "eyes_backend", "mock").lower()
    if backend == "preview":
        return OcchiPreview(port=getattr(config, "eyes_preview_port", 8473))
    return OcchiMock()
