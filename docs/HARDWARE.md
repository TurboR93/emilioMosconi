# Emilio — Componenti da comprare (lista della spesa)

Guida pratica all'hardware per montare Emilio su Raspberry Pi. Prezzi indicativi
in € (mercato hobbistico, possono variare). Pensata per due livelli: **Base**
(Emilio ascolta e parla) e **Completo** (anche movimento e occhi).

> Strategia **mente + corpo**: la **mente** (orchestratore + LLM + supervisore +
> voce + STT) gira sul **Mac**; il **Raspberry è il corpo** (motori dei cingoli,
> microfono e altoparlante a bordo) collegato in Wi-Fi. In sviluppo il lavoro
> pesante sta sul Mac; onboard, non reggendo l'inferenza locale, il Pi userà le
> **API cloud** (Claude + ElevenLabs). Per questo il Pi non deve essere potente.
> **`ffmpeg` è richiesto** (BIP di censura + registrazione del microfono).

---

## 1. Cervello / computer

| Componente | Esempio | Perché | Prezzo |
|------------|---------|--------|--------|
| **Raspberry Pi 4 o 5** (2–4 GB) | Pi 5 4GB / Pi 4 2GB | È il **corpo**: audio (mic + altoparlante a bordo), motori dei cingoli, Wi-Fi con la mente (Mac). Onboard può fare da orchestratore con LLM/voce via cloud | 50–80 € |
| **MicroSD** 32 GB classe A1/A2 | SanDisk Ultra/Extreme | Sistema operativo | 8–12 € |
| **Alimentatore ufficiale** | Pi 5: USB-C 5V/5A · Pi 4: 5V/3A | Stabilità (l'audio/servo soffrono i cali) | 12–15 € |
| **Case** (opzionale) | con accesso GPIO | Per montarlo nel pupazzo | 8–15 € |

> Anche un **Pi Zero 2 W** funziona per la sola voce, ma per audio + servo +
> margine consiglio Pi 4/5.

---

## 2. Microfono (ascolto) 🎤

Tre fasce, dalla più semplice alla più "seria":

| Opzione | Esempio | Perché | Prezzo |
|---------|---------|--------|--------|
| **USB mic economico** | SunFounder USB mini mic | Plug&play, nessun driver; ok per iniziare/test | 5–10 € |
| **ReSpeaker 2-Mic Pi HAT** ⭐ | Seeed ReSpeaker 2-Mic HAT | 2 microfoni + cattura "far-field", pensato per assistenti vocali; si monta sul Pi | 12–20 € |
| **ReSpeaker XVF3800 USB 4-Mic Array** | Seeed XVF3800 | Array a 4 mic, riduce rumore/eco, qualità top in stanze reali | 60–80 € |

**Consiglio:** parti con il **ReSpeaker 2-Mic Pi HAT** — buon compromesso
qualità/prezzo e fatto apposta per la voce. Per ambienti rumorosi, l'array USB a
4 mic è di un altro livello.

> Requisito software: **`ffmpeg`** è richiesto sia per registrare dal microfono
> (STT) sia per il BIP di censura. In **sviluppo** lo STT (faster-whisper) usa il
> **microfono del Mac** (ffmpeg avfoundation); il mic a bordo del Pi entra in
> gioco nello scenario corpo/onboard. Su Raspberry headless: ALSA puro (`afplay`
> è solo macOS); riproduzione con `mpg123`/`ffplay`.

---

## 3. Altoparlante + amplificatore (voce) 🔊

⚠️ Importante: il Raspberry **Pi 5 e lo Zero non hanno uscita audio analogica**;
serve un DAC/ampli (I2S o USB). Opzioni:

| Opzione | Esempio | Perché | Prezzo |
|---------|---------|--------|--------|
| **HAT audio all-in-one** ⭐ | Pimoroni Speaker pHAT / Adafruit Speaker Bonnet | DAC + amplificatore + (mini speaker) in un pezzo solo, poco cablaggio | 10–20 € |
| **DAC+ampli I2S + speaker** | MAX98357A (I2S) + speaker 3–8 Ω 2–3 W | Più volume/qualità, modulare | 6 € (ampli) + 3–8 € (speaker) |
| **Ampli analogico + speaker** | PAM8302 / HXJ8002 + speaker | Economico (richiede però sorgente audio: USB DAC o HAT) | ~5 € + speaker |
| **Speakerphone USB** | qualsiasi USB mic+speaker | Soluzione "tutto in uno" rapida (mic + altoparlante) | 20–40 € |

**Consiglio:** **MAX98357A (I2S) + un piccolo speaker 4 Ω 3 W**, oppure un
**Pimoroni Speaker pHAT** se vuoi meno saldature. Lo speaker scegli il diametro
in base allo spazio nel pupazzo (4–5 cm vanno benissimo).

> Alternativa "tutto-in-uno" microfono+altoparlante: una **Codec Zero**
> (Raspberry) o un dispositivo ReSpeaker integra ingresso e uscita audio.

---

## 4. Movimento 🤖

**Oggi l'unica motorizzazione attiva sono i CINGOLI** (`avanti`/`indietro`/
`sinistra`/`destra` in `actuators.MOVES`): servono **2 motori DC + un driver**
(es. **L298N** o **TB6612FNG**, ~3–8 €) oppure servo a rotazione continua. Testa,
braccia, bocca e occhi sono già nel vocabolario `MOVES` ma **rinviati al futuro**
(non cablati); per quelli valgono i **servo** qui sotto.

Per i servo (espansione futura), due architetture:

**A) Pi → PCA9685 → servo (CONSIGLIATA, meno pezzi)**

| Componente | Esempio | Perché | Prezzo |
|------------|---------|--------|--------|
| **Driver servo PCA9685** ⭐ | Adafruit/clone 16 canali I2C | Pilota fino a 16 servo con 2 pin (I2C), liscio e preciso | 5–12 € |
| **Servo SG90** (mini) | torre/feetech SG90 | Movimenti leggeri (bocca, occhi, testa) | ~2 €/cad |
| **Servo MG90S** (metallo) | MG90S | Più coppia per testa/braccio | ~3–4 €/cad |
| **Alimentatore servo 5V 2–3 A** | separato dal Pi | I servo "succhiano" corrente: NON alimentarli dal Pi | 8–12 € |
| **Condensatore 1000 µF** | elettrolitico | Stabilizza i picchi dei servo | <1 € |

**B) Pi → USB seriale → Arduino → motori**
Coerente col backend `SerialMover` già nel codice (protocollo `MOVE <azione>
<valore>`). Aggiunge un Arduino (~5–15 €) ma isola la parte motori. Utile se usi
motori DC/ruote oltre ai servo.

> Nota codice: oggi `actuators.py` ha il backend **seriale** (opzione B). Se
> scegli il **PCA9685** (opzione A) aggiungo un backend `Pca9685Mover`:
> l'architettura è già predisposta.

Quanti servo (espansione **futura**, non l'assetto base)? testa su/giù (1) + testa
dx/sx (1) + bocca (1) + braccio (1) = ~4 servo; occhi mobili +2. Per i **cingoli**
di oggi bastano invece **2 motori DC + driver** (L298N/TB6612).

---

## 5. Occhi / LED ✨ (opzionale ma scenografico)

| Componente | Esempio | Perché | Prezzo |
|------------|---------|--------|--------|
| **LED + resistenze** | 2 LED 5 mm + 220 Ω | Occhi che si accendono (`occhi_on/off`) | <1 € |
| **NeoPixel / WS2812** ⭐ | anello o singoli | Occhi colorati/animati (servono per le espressioni) | 3–8 € |

> Nel codice (`occhi.py`) gli occhi hanno già un set di **ESPRESSIONI** con colore
> (neutro verde, **arrabbiato** rosso a forma di **forca del diavolo**, ascolta
> bianco, pensa viola, ...) e un'**anteprima web** (`EMILIO_OCCHI=preview`). Sul
> corpo serviranno **LED RGB indirizzabili** (NeoPixel/WS2812) per rendere il
> colore dell'espressione, non semplici LED on/off; è previsto un futuro backend
> `OcchiLed` sul Pi. (`occhi_on/off` in `actuators` sono LED on/off separati.)

---

## 6. Alimentazione e cablaggio

| Componente | Esempio | Perché | Prezzo |
|------------|---------|--------|--------|
| **Alimentatore Pi** | (vedi §1) | — | — |
| **Alimentatore servo 5V** | 5V 3A separato | I motori a parte dal Pi | 8–12 € |
| **Breadboard + jumper** | kit Dupont M-M/M-F | Prototipazione | 8–12 € |
| **(Opz.) Power bank/batteria** | 5V USB-C ad alto amperaggio | Se Emilio è mobile | 15–30 € |

⚠️ Massa comune: collega insieme i **GND** di Pi, PCA9685 e alimentatore servo.

---

## 7. Connettività

In **sviluppo** il Pi è collegato in **Wi-Fi alla mente (Mac)**, che fa LLM, STT e
voce. Nello scenario **onboard** finale serve **internet sul Pi** per le API cloud
(Claude + ElevenLabs). Senza rete, Emilio gira in modalità ridotta: cervello mock
(o **LLM locale Ollama sul Mac**) + voce offline `pyttsx3` + STT offline
faster-whisper.

---

## 8. Riepilogo per budget

**Kit Base (ascolta + parla), ~90–130 €**
- Raspberry Pi 4/5 + microSD + alimentatore
- ReSpeaker 2-Mic Pi HAT (microfono)
- MAX98357A + speaker (o Pimoroni Speaker pHAT)

**Kit Completo (+ movimento + occhi), ~140–200 €**
- Tutto il Base
- PCA9685 + 4–6 servo (SG90/MG90S) + alimentatore servo 5V + condensatore
- LED/NeoPixel per gli occhi
- breadboard + jumper

> ⚠️ Attenzione alla **compatibilità di montaggio** tra HAT: un ReSpeaker HAT e un
> Speaker pHAT occupano entrambi il connettore GPIO. Soluzioni: usare versioni
> **USB** per il microfono, oppure un **GPIO stacking header** per impilare gli
> HAT, oppure tenere audio out su DAC I2S e microfono su USB.

---

## 9. Prossimo passo

Quando hai scelto i pezzi (soprattutto **come muovi i motori**: PCA9685 vs
Arduino seriale), aggiorno `actuators.py` con il backend giusto e ti preparo lo
schema dei collegamenti e il codice di test dei servo.

---

> I prezzi sono indicativi e vanno verificati sul rivenditore (Amazon, Kubii,
> Melopero, RobotShop, AliExpress, ecc.). Le scelte sono pensate per qualità
> audio decente e semplicità di montaggio.
