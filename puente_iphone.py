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
CALIDAD = 0.6            # calidad del JPEG que envia el iPhone (0 a 1)
ANCHO = 640
ALTO = 480
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
    video { width:100%; max-width:640px; }
    #estado { padding:10px; font-size:15px; }
    .ok { color:#6ed86e; }
    .error { color:#ff7b6e; }
  </style>
</head>
<body>
  <p id="estado">Iniciando camara...</p>
  <video id="cam" autoplay playsinline muted></video>
  <canvas id="lienzo" style="display:none"></canvas>

<script>
const video  = document.getElementById('cam');
const lienzo = document.getElementById('lienzo');
const estado = document.getElementById('estado');
const ctx = lienzo.getContext('2d');
let enviados = 0;

// facingMode environment = camara trasera
navigator.mediaDevices.getUserMedia({
  video: { facingMode: { ideal: 'environment' },
           width: {{ ancho }}, height: {{ alto }} },
  audio: false
}).then(stream => {
  video.srcObject = stream;
  video.onloadedmetadata = () => {
    lienzo.width  = video.videoWidth;
    lienzo.height = video.videoHeight;
    estado.textContent = 'Transmitiendo al PC...';
    estado.className = 'ok';
    enviar();
  };
}).catch(e => {
  estado.textContent = 'Error de camara: ' + e.message;
  estado.className = 'error';
});

function enviar() {
  ctx.drawImage(video, 0, 0, lienzo.width, lienzo.height);
  lienzo.toBlob(blob => {
    fetch('/subir', { method: 'POST', body: blob })
      .then(() => {
        enviados++;
        if (enviados % 15 === 0) {
          estado.textContent = 'Transmitiendo  (' + enviados + ' cuadros)';
        }
        enviar();
      })
      .catch(() => {
        estado.textContent = 'Se perdio la conexion. Reintentando...';
        estado.className = 'error';
        setTimeout(enviar, 1000);
      });
  }, 'image/jpeg', {{ calidad }});
}

// Evitar que la pantalla se apague y corte la camara
if ('wakeLock' in navigator) {
  navigator.wakeLock.request('screen').catch(() => {});
}
</script>
</body>
</html>
"""


def generar_mjpeg():
    """Entrega los cuadros en formato MJPEG, que es lo que lee OpenCV."""
    ultimo_enviado = 0.0
    while True:
        with _lock:
            jpeg = _ultimo["jpeg"]
            hora = _ultimo["hora"]

        if jpeg and hora != ultimo_enviado:
            ultimo_enviado = hora
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")
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
            _ultimo["hora"] = time.time()
    return "", 204


# ----- Servidor 2: http, para el modelo -----
app_stream = Flask("stream")


@app_stream.route("/stream")
def stream():
    return Response(generar_mjpeg(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")


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


def main():
    ip = ip_local()

    print("\n" + "=" * 62)
    print("  1. En Safari del iPhone abre:")
    print(f"        https://{ip}:{PUERTO_IPHONE}")
    print("     Acepta la advertencia del certificado y da permiso")
    print("     a la camara. Debes ver la imagen en el celular.")
    print()
    print("  2. En otra terminal del PC, una de estas dos:")
    print(f'        yolo predict model=bestnano.pt source="http://127.0.0.1:{PUERTO_STREAM}/stream" show=True imgsz=320')
    print(f"        python3 torres_vivo.py http://127.0.0.1:{PUERTO_STREAM}/stream")
    print()
    print("     Ojo: https para el celular, http para el modelo.")
    print("=" * 62 + "\n")

    # El stream corre en un hilo aparte
    hilo = threading.Thread(
        target=lambda: app_stream.run(
            host="0.0.0.0", port=PUERTO_STREAM,
            threaded=True, debug=False, use_reloader=False),
        daemon=True,
    )
    hilo.start()

    app_iphone.run(host="0.0.0.0", port=PUERTO_IPHONE,
                   ssl_context="adhoc", threaded=True,
                   debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
