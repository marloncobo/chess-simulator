"""Pruebas sin cámaras físicas: argumentos y dos fuentes MJPEG locales."""
import contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import multiprocessing as mp
import threading
import time
import unittest

import cv2
import numpy as np

from herramientas.probar_dos_camaras import (
    CamaraSupervisada, argumentos, desfase_ms, panel,
)


class PruebasConfiguracion(unittest.TestCase):
    def test_webcam_y_iphone_con_backend_local(self):
        url = "http://127.0.0.1:5002/stream"
        args = argumentos(["--sources", "0", url, "--backend", "dshow",
                           "--resolucion-1", "1280", "720"])
        self.assertEqual(args.configuraciones, [(0, "dshow", (1280, 720)), (url, "auto", None)])

    def test_ajustes_independientes_y_compatibilidad(self):
        self.assertEqual(argumentos([]).configuraciones,
                         [(0, "auto", (640, 480)), (1, "auto", (640, 480))])
        args = argumentos(["--backend-1", "dshow", "--backend-2", "msmf",
                           "--resolucion-2", "1920", "1080"])
        self.assertEqual(args.configuraciones,
                         [(0, "dshow", (640, 480)), (1, "msmf", (1920, 1080))])

    def test_rechaza_argumentos_invalidos(self):
        casos = [["--sources", "0", "0"], ["--sources", "-1", "1"],
                 ["--sources", "0", "http://"], ["--timeout", "nan"],
                 ["--timeout", "1"], ["--max-desfase-ms", "inf"],
                 ["--resolucion-2", "0", "480"],
                 ["--sources", "0", "http://localhost/stream", "--backend-2", "dshow"]]
        for caso in casos:
            with self.subTest(caso=caso), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    argumentos(caso)

    def test_desfase_no_usa_imagen_antigua_o_desconectada(self):
        frame = np.zeros((40, 60, 3), np.uint8)
        estados = [{"frame": frame, "instante": 10}, {"frame": frame, "instante": 10.1}]
        self.assertAlmostEqual(desfase_ms(estados, 10.2), 100)
        self.assertIsNone(desfase_ms(estados, 12.2))
        self.assertIsNone(desfase_ms([estados[0], {"error": "desconectada"}], 10.2))

    def test_imagen_antigua_se_oscurece(self):
        frame = np.full((360, 640, 3), 200, np.uint8)
        estado = {"frame": frame, "instante": 10}
        vivo = panel(estado, 1, 0, 10.1)
        antiguo = panel(estado, 1, 0, 13)
        self.assertEqual(vivo.shape, (480, 640, 3))
        self.assertTrue(np.all(vivo[150, 10] == 200))
        self.assertTrue(np.all(antiguo[150, 10] == 60))


class PruebaCapturaRed(unittest.TestCase):
    def test_dos_streams_bloqueo_y_recuperacion_independiente(self):
        detener = threading.Event()
        pausa = threading.Event()
        imagenes = {}
        for ruta, color in (("/a", (0, 0, 240)), ("/b", (240, 0, 0))):
            frame = np.full((120, 160, 3), color, np.uint8)
            ok, jpeg = cv2.imencode(".jpg", frame)
            self.assertTrue(ok)
            imagenes[ruta] = jpeg.tobytes()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.end_headers()
                try:
                    while not detener.is_set():
                        if self.path != "/a" or not pausa.is_set():
                            jpeg = imagenes[self.path]
                            self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                             + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")
                            self.wfile.flush()
                        detener.wait(.05)
                except (ConnectionError, OSError):
                    pass

        servidor = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
        hilo.start()
        ctx = mp.get_context("spawn")
        base = f"http://127.0.0.1:{servidor.server_port}"
        camaras = [CamaraSupervisada(ctx, base + ruta, "auto", None, timeout=8)
                   for ruta in ("/a", "/b")]

        def esperar(condicion, limite=15):
            fin = time.monotonic() + limite
            while time.monotonic() < fin:
                for camara in camaras:
                    camara.actualizar(time.monotonic())
                if condicion():
                    return
                time.sleep(.02)
            self.fail(f"No se cumplio la condicion; estados: {[c.estado.get('error') for c in camaras]}")

        try:
            for camara in camaras:
                camara.iniciar()
            esperar(lambda: all("frame" in c.estado for c in camaras))
            self.assertGreater(camaras[0].estado["frame"][:, :, 2].mean(), 230)
            self.assertGreater(camaras[1].estado["frame"][:, :, 0].mean(), 230)
            a, b = camaras
            pid_a, pid_b, cola_a = a.proceso.pid, b.proceso.pid, a.cola
            secuencia_b = b.estado["secuencia"]
            a.timeout = 2
            pausa.set()  # Conexión abierta que deja de enviar: read puede bloquearse.
            esperar(lambda: a.reinicios >= 1 and a.retirando is None and a.proceso.pid != pid_a)
            self.assertIsNot(a.cola, cola_a)
            self.assertEqual(b.proceso.pid, pid_b)
            self.assertGreater(b.estado["secuencia"], secuencia_b)
            pausa.clear()
            a.timeout = 8
            esperar(lambda: "frame" in a.estado)
            self.assertGreater(a.estado["frame"][:, :, 2].mean(), 230)
            # Un proceso muerto también se recupera sin reiniciar la otra fuente.
            pid_a = a.proceso.pid
            a.proceso.terminate()
            a.proceso.join(timeout=2)
            esperar(lambda: a.proceso.pid != pid_a and "frame" in a.estado)
            self.assertEqual(b.proceso.pid, pid_b)
        finally:
            for camara in camaras:
                camara.cerrar()
            detener.set()
            servidor.shutdown()
            servidor.server_close()
            hilo.join(timeout=2)
        self.assertTrue(all(c.proceso is None for c in camaras))


if __name__ == "__main__":
    unittest.main()
