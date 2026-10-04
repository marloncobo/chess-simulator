"""
Puente iPhone -> PC sin instalar ninguna app en el celular.

COMO FUNCIONA
-------------
1. Este programa levanta DOS servidores en tu PC:

     https://TU-IP:5001      pagina para el iPhone
     http://127.0.0.1:5002/stream   video para el modelo

   Son dos porque Safari solo entrega la camara en paginas seguras
   (https), mientras que OpenCV no sabe leer un https con certificado
   autofirmado. Cada uno recibe lo que necesita.

2. Abres la pagina en Safari del iPhone. Safari pide permiso para la
   camara y empieza a enviar cuadros al PC.

3. El servidor reexpone esos cuadros como un stream MJPEG normal, que
   YOLO o torres_vivo.py leen como si fuera una webcam.

USO
---
  Terminal 1:
      pip install flask pyopenssl
      python3 puente_iphone.py

  En el iPhone (misma red WiFi):
      abre en Safari la direccion https que imprime el servidor
      acepta la advertencia del certificado
      da permiso a la camara

  Terminal 2, cualquiera de las dos:
      yolo predict model=modelos/bestnano.pt source="http://127.0.0.1:5002/stream" show=True imgsz=320
      python3 torres_vivo.py http://127.0.0.1:5002/stream
"""

import socket
import threading
import time

from flask import Flask, Response, request, render_template_string

# ----- CONFIGURACION -----
PUERTO_IPHONE = 5001     # https, para Safari
PUERTO_STREAM = 5002     # http, para OpenCV / YOLO
CALIDAD = 0.85           # conserva más detalle para distinguir las piezas
ANCHO = 1280            # resolución preferida; Safari negocia la disponible
ALTO = 720
# -------------------------

# Ultimo cuadro recibido del iPhone
_ultimo = {"jpeg": None, "hora": 0.0}
_lock = threading.Lock()


PAGINA = """
<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Camara -> PC</title>
  <style>
    body { margin:0; background:#111; color:#eee;
           font-family:-apple-system,sans-serif; text-align:center; }
    video { width:100%; max-height:70vh; object-fit:contain; }
    .controles { padding:12px; display:flex; gap:12px; justify-content:center; flex-wrap:wrap; }
    select, button { padding:10px; font-size:16px; border-radius:8px; }
    .nota { padding:0 16px; color:#bbb; font-size:14px; }
    #estado { padding:10px; font-size:15px; }
    .ok { color:#6ed86e; }
    .error { color:#ff7b6e; }
  </style>
</head>
<body>
  <div class="controles">
    <label>Resolución
      <select id="resolucion">
        <option value="1280x720" selected>HD · 720p</option>
        <option value="1920x1080">Full HD · 1080p</option>
        <option value="640x480">480p · menor consumo</option>
      </select>
    </label>
    <button id="reconectar" type="button">Reconectar cámara</button>
  </div>
  <p class="nota">Coloca el iPhone horizontal para aprovechar el ancho de la vista en el PC.
    Después de cambiar resolución u orientación, vuelve a calibrar esa cámara.</p>
  <p id="estado">Iniciando camara...</p>
  <p id="detalle" class="nota"></p>
  <video id="cam" autoplay playsinline muted></video>
  <canvas id="lienzo" style="display:none"></canvas>

<script>
const video  = document.getElementById('cam');
const lienzo = document.getElementById('lienzo');
const estado = document.getElementById('estado');
const detalle = document.getElementById('detalle');
const resolucion = document.getElementById('resolucion');
const ctx = lienzo.getContext('2d');
let enviados = 0;
let pista = null;
let ajustes = Promise.resolve();
let aviso = '';
let bloqueoPantalla = null;
let solicitandoBloqueo = false;
resolucion.value = '{{ ancho }}x{{ alto }}';
if (!resolucion.value) resolucion.value = '1280x720';

function restricciones() {
  const [ancho, alto] = resolucion.value.split('x').map(Number);
  const vertical = window.matchMedia('(orientation: portrait)').matches;
  return {
    facingMode: { ideal: 'environment' },
    width: { ideal: vertical ? alto : ancho },
    height: { ideal: vertical ? ancho : alto },
    frameRate: { ideal: 30, max: 30 }
  };
}

function ajustarLienzo() {
  // Safari puede cambiar las dimensiones al girar o aplicar restricciones.
  // Usar siempre la imagen real evita estirar, recortar o ampliar píxeles.
  const ancho = video.videoWidth, alto = video.videoHeight;
  if (!ancho || !alto) return false;
  if (lienzo.width !== ancho || lienzo.height !== alto) {
    lienzo.width = ancho;
    lienzo.height = alto;
  }
  detalle.textContent = `Enviando ${ancho} × ${alto} · ${ancho >= alto ? 'horizontal' : 'vertical'}${aviso}`;
  return true;
}

function aplicarResolucion() {
  // Serializar los cambios evita que una rotación sobrescriba un ajuste nuevo.
  ajustes = ajustes.then(async () => {
    if (!pista) return;
    try {
      await conLimite(pista.applyConstraints(restricciones()), 3000, 'Ajuste de resolución detenido');
      aviso = '';
    } catch (error) {
      aviso = ' · No se pudo aplicar el cambio; se conserva la resolución disponible';
    }
    ajustarLienzo();
  });
  return ajustes;
}

resolucion.addEventListener('change', aplicarResolucion);
video.addEventListener('resize', ajustarLienzo);
let giro;
window.addEventListener('orientationchange', () => {
  clearTimeout(giro);
  giro = setTimeout(aplicarResolucion, 400);
});

const esperar = ms => new Promise(resolve => setTimeout(resolve, ms));

async function conLimite(promesa, ms, mensaje) {
  let temporizador;
  try {
    return await Promise.race([promesa, new Promise((_, reject) => {
      temporizador = setTimeout(() => reject(new Error(mensaje)), ms);
    })]);
  } finally {
    clearTimeout(temporizador);
  }
}

function detenerCamara() {
  if (video.srcObject) video.srcObject.getTracks().forEach(track => track.stop());
  pista = null;
  video.srcObject = null;
}

async function mantenerPantalla() {
  if (document.hidden || !('wakeLock' in navigator) || bloqueoPantalla || solicitandoBloqueo) return;
  solicitandoBloqueo = true;
  try {
    const bloqueo = await navigator.wakeLock.request('screen');
    bloqueoPantalla = bloqueo;
    bloqueo.addEventListener('release', () => {
      if (bloqueoPantalla === bloqueo) bloqueoPantalla = null;
    });
  } catch (error) {
    // Safari puede denegarlo, por ejemplo con ahorro de batería.
  } finally {
    solicitandoBloqueo = false;
  }
}

document.getElementById('reconectar').addEventListener('click', detenerCamara);
document.addEventListener('visibilitychange', () => {
  if (document.hidden) detenerCamara();
  else mantenerPantalla();
});
window.addEventListener('pagehide', detenerCamara);
window.addEventListener('pageshow', mantenerPantalla);

async function enviar() {
  let tiempoVideo = -1;
  let ultimoAvance = performance.now();
  while (pista && pista.readyState === 'live' && !document.hidden) {
    // readyState puede seguir siendo live aunque Safari deje de producir vídeo.
    if (video.readyState >= 2 && video.currentTime !== tiempoVideo) {
      tiempoVideo = video.currentTime;
      ultimoAvance = performance.now();
    } else if (performance.now() - ultimoAvance > 6000) {
      throw new Error('El vídeo dejó de avanzar');
    }
    if (video.readyState < 2 || !ajustarLienzo()) {
      await esperar(100);
      continue;
    }
    ctx.drawImage(video, 0, 0, lienzo.width, lienzo.height);
    // toBlob también puede quedarse pendiente; antes paralizaba todo el bucle.
    const blob = await conLimite(new Promise(resolve => lienzo.toBlob(resolve, 'image/jpeg', {{ calidad }})),
                                3000, 'La captura de imagen no responde');
    if (!blob) throw new Error('No se pudo capturar el cuadro');
    if (!pista || document.hidden) break;
    const controlador = new AbortController();
    try {
      const respuesta = await conLimite(fetch('/subir', { method: 'POST', body: blob, signal: controlador.signal }),
                                        8000, 'El envío no responde');
      if (!respuesta.ok) throw new Error('El PC no pudo recibir el cuadro');
      enviados++;
      estado.textContent = `Transmitiendo al PC · ${enviados} cuadros`;
      estado.className = 'ok';
      // Un solo envío pendiente: la red marca el ritmo sin acumular cuadros.
      await esperar(33);
    } catch (error) {
      estado.textContent = 'Se perdió la conexión. Reintentando...';
      estado.className = 'error';
      await esperar(1000);
    } finally {
      controlador.abort();
    }
  }
}

async function iniciar() {
  // Un único supervisor: nunca iniciar bucles paralelos al volver a Safari.
  while (true) {
    if (document.hidden) {
      await esperar(500);
      continue;
    }
    let vigente = true;
    try {
      mantenerPantalla();
      estado.textContent = 'Conectando cámara...';
      const apertura = navigator.mediaDevices.getUserMedia({ video: restricciones(), audio: false });
      apertura.then(stream => {
        if (!vigente || document.hidden) stream.getTracks().forEach(track => track.stop());
      }, () => {});
      const stream = await conLimite(apertura, 30000, 'La cámara no responde');
      if (document.hidden) continue;
      pista = stream.getVideoTracks()[0];
      video.srcObject = stream;
      await conLimite(video.play(), 8000, 'El vídeo no inicia');
      await aplicarResolucion();
      await enviar();
    } catch (error) {
      estado.textContent = 'Recuperando cámara: ' + error.message;
      estado.className = 'error';
    } finally {
      vigente = false;
      detenerCamara();
    }
    await esperar(1000);
  }
}
iniciar();
</script>
</body>
</html>
"""


def generar_mjpeg():
    """Entrega los cuadros en formato MJPEG, que es lo que lee OpenCV."""
    ultimo_enviado = 0.0
    inicio = time.monotonic()
    while True:
        with _lock:
            jpeg = _ultimo["jpeg"]
            hora = _ultimo["hora"]

        ahora = time.monotonic()
        if ahora - max(inicio, hora) > 8:
            # Cierra la lectura bloqueada y permite que OpenCV reconecte.
            return
        if jpeg and ahora - hora < 8 and hora != ultimo_enviado:
            ultimo_enviado = hora
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\nContent-Length: "
                   + str(len(jpeg)).encode("ascii") + b"\r\n\r\n" + jpeg + b"\r\n")
        else:
            time.sleep(0.01)


# ----- Servidor 1: https, para el iPhone -----
app_iphone = Flask("iphone")


@app_iphone.route("/")
def inicio():
    return render_template_string(PAGINA, ancho=ANCHO, alto=ALTO,
                                  calidad=CALIDAD)


@app_iphone.route("/subir", methods=["POST"])
def subir():
    datos = request.get_data()
    if datos:
        with _lock:
            _ultimo["jpeg"] = datos
            _ultimo["hora"] = time.monotonic()
    return "", 204


# ----- Servidor 2: http, para el modelo -----
app_stream = Flask("stream")


@app_stream.route("/stream")
def stream():
    return Response(generar_mjpeg(),
                    mimetype="multipart/x-mixed-replace; boundary=frame",
                    headers={"Cache-Control": "no-store"})


def ip_local():
    """IP de este PC en la red WiFi."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def argumentos(argv=None):
    import argparse
    parser = argparse.ArgumentParser(
        description="Puente celular -> PC. Para dos celulares, corre dos copias con puertos distintos.")
    parser.add_argument("--puerto-celular", type=int, default=PUERTO_IPHONE,
                        help=f"Puerto https que se abre en el navegador del celular (por defecto {PUERTO_IPHONE})")
    parser.add_argument("--puerto-stream", type=int, default=PUERTO_STREAM,
                        help=f"Puerto http que lee OpenCV (por defecto {PUERTO_STREAM})")
    args = parser.parse_args(argv)
    puertos = (args.puerto_celular, args.puerto_stream)
    if len(set(puertos)) != 2 or not all(1024 <= p <= 65535 for p in puertos):
        parser.error("Use dos puertos distintos entre 1024 y 65535")
    return args


def main(argv=None):
    args = argumentos(argv)
    ip = ip_local()

    print("\n" + "=" * 62)
    print("  1. En el navegador del celular (Safari en iPhone, Chrome en Android) abre:")
    print(f"        https://{ip}:{args.puerto_celular}")
    print("     Acepta la advertencia del certificado y da permiso")
    print("     a la camara. Debes ver la imagen en el celular.")
    print()
    print("  2. La deteccion lee este celular en:")
    print(f"        http://127.0.0.1:{args.puerto_stream}/stream")
    print()
    print("     Ojo: https para el celular, http para el modelo.")
    print("=" * 62 + "\n")

    # El stream corre en un hilo aparte
    hilo = threading.Thread(
        target=lambda: app_stream.run(
            host="0.0.0.0", port=args.puerto_stream,
            threaded=True, debug=False, use_reloader=False),
        daemon=True,
    )
    hilo.start()

    app_iphone.run(host="0.0.0.0", port=args.puerto_celular,
                   ssl_context="adhoc", threaded=True,
                   debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
