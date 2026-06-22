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


# Espressione -> (colore LED, descrizione).
ESPRESSIONI: dict[str, tuple[str, str]] = {
    "neutro":     ("#7CFC00", "occhi calmi"),
    "felice":     ("#00E5FF", "occhi sorridenti"),
    "arrabbiato": ("#FF3B30", "furia: gli occhi diventano forche del diavolo"),
    "sorpreso":   ("#FFD60A", "occhi spalancati"),
    "triste":     ("#4D7CFF", "occhi bassi"),
    "pensa":      ("#B388FF", "viola, sta pensando"),
    "parla":      ("#00FF87", "occhi vivaci mentre parla"),
    "ascolta":    ("#FFFFFF", "occhi attenti, sta ascoltando"),
    "spento":     ("#222222", "LED spenti"),
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
 html,body{margin:0;height:100%;background:#0b0b0f;overflow:hidden}
 #faccia{display:block;margin:auto}
 #et{position:fixed;bottom:14px;left:0;right:0;text-align:center;
     color:#888;font:600 18px system-ui,sans-serif;letter-spacing:.04em}
</style></head><body>
<canvas id="faccia" width="640" height="400"></canvas>
<div id="et">…</div>
<script>
const W=640,H=400,c=document.getElementById('faccia'),x=c.getContext('2d'),et=document.getElementById('et');
const OFF={centro:[0,0],sinistra:[-14,0],destra:[14,0],su:[0,-10],giu:[0,10]};
let S={espressione:'neutro',colore:'#7CFC00',aperti:true,direzione:'centro'};

// Testa di Emiglio: calotta bianca, pannelli colorati in alto, visiera nera
function testa(){
  x.save();
  x.fillStyle='#e9ecef';
  x.beginPath();x.roundRect(150,55,340,310,[150,150,90,90]);x.fill();
  x.fillStyle='#3b3f8f';x.beginPath();x.roundRect(238,80,52,34,8);x.fill();
  x.fillStyle='#f2c200';x.beginPath();x.roundRect(296,74,58,34,8);x.fill();
  x.fillStyle='#d23b2e';x.beginPath();x.roundRect(360,80,52,34,8);x.fill();
  x.fillStyle='#0c0c11';
  x.beginPath();x.roundRect(206,130,228,120,[30,30,52,52]);x.fill();
  x.restore();
}

// Occhio tondo luminoso (come i LED del vero Emiglio; il colore segue lo stato)
function occhio(cx,cy,col,aperti,dir){
  x.save();x.translate(cx,cy);x.shadowBlur=26;x.shadowColor=col;
  const o=OFF[dir]||[0,0];
  if(aperti){
    x.fillStyle=col;x.beginPath();x.arc(o[0],o[1],23,0,7);x.fill();
    x.fillStyle='rgba(255,255,255,.55)';x.beginPath();x.arc(o[0]-7,o[1]-7,6,0,7);x.fill();
  }else{x.strokeStyle=col;x.lineWidth=6;x.beginPath();x.moveTo(-21,0);x.lineTo(21,0);x.stroke();}
  x.restore();
}

// Bocca: sorriso di Emiglio; ANIMATA (si apre/chiude) quando parla; broncio se arrabbiato
function bocca(t,parla,arr){
  x.save();x.translate(320,300);x.lineCap='round';
  x.strokeStyle='#2a2a2e';x.fillStyle='#2a2a2e';x.lineWidth=6;
  if(arr){x.beginPath();x.arc(0,34,48,1.18*Math.PI,1.82*Math.PI);x.stroke();}
  else if(parla){const ap=6+12*Math.abs(Math.sin(t*9));
    x.beginPath();x.ellipse(0,-6,30,ap,0,0,7);x.fill();}
  else{x.beginPath();x.arc(0,-22,48,0.16*Math.PI,0.84*Math.PI);x.stroke();}
  x.restore();
}

// Forca del diavolo (tridente) animata: al posto degli occhi quando è arrabbiato
function forca(cx,cy,col,t,s){
  x.save();x.translate(cx,cy);x.scale(s,s);x.rotate(Math.sin(t*5+cx)*0.06);
  x.shadowColor=col;x.shadowBlur=26+16*Math.abs(Math.sin(t*7));
  x.strokeStyle=col;x.fillStyle=col;x.lineWidth=10;x.lineCap='round';x.lineJoin='round';
  x.beginPath();x.moveTo(0,-36);x.lineTo(0,82);x.stroke();
  x.beginPath();x.moveTo(-32,-36);x.lineTo(32,-36);x.stroke();
  x.beginPath();x.moveTo(0,-36);x.lineTo(0,-86);x.stroke();
  x.beginPath();x.moveTo(-32,-36);x.quadraticCurveTo(-42,-72,-22,-86);x.stroke();
  x.beginPath();x.moveTo(32,-36);x.quadraticCurveTo(42,-72,22,-86);x.stroke();
  const tip=(px,py)=>{x.beginPath();x.moveTo(px-8,py+4);x.lineTo(px+8,py+4);x.lineTo(px,py-16);x.closePath();x.fill();};
  tip(0,-86);tip(-22,-86);tip(22,-86);
  x.restore();
}

let t0=performance.now();
function frame(now){
  const t=(now-t0)/1000;
  x.clearRect(0,0,W,H);testa();
  const arr=S.espressione==='arrabbiato';
  if(arr){forca(266,188,S.colore,t,0.62);forca(374,188,S.colore,t+0.4,0.62);}
  else{occhio(266,180,S.colore,S.aperti,S.direzione);occhio(374,180,S.colore,S.aperti,S.direzione);}
  bocca(t,S.espressione==='parla',arr);
  et.textContent=(arr?'ARRABBIATO 😈':S.espressione.toUpperCase()+'  •  '+S.colore);
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
