from pathlib import Path
import re
import shutil
import subprocess
import unittest
from unittest.mock import patch

import cv2
import numpy as np

import puente_iphone as puente


class PruebasPuenteIphone(unittest.TestCase):
    def test_stream_caduco_no_repite_imagen_y_termina(self):
        anterior = dict(puente._ultimo)
        try:
            puente._ultimo.update(jpeg=b"imagen-antigua", hora=1.)
            with patch.object(puente.time, "monotonic", side_effect=[20., 20., 29.]), \
                    patch.object(puente.time, "sleep"):
                self.assertEqual(list(puente.generar_mjpeg()), [])
        finally:
            puente._ultimo.update(anterior)

    def test_javascript_adapta_resolucion_y_orientacion(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node no disponible para ejecutar el cliente web simulado")
        respuesta = puente.app_iphone.test_client().get("/")
        self.assertEqual(respuesta.status_code, 200)
        html = respuesta.get_data(as_text=True)
        script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
        resultado = subprocess.run([node, str(Path(__file__).with_name("puente_iphone_browser.cjs"))],
                                   input=script, text=True, encoding="utf-8", capture_output=True, timeout=15)
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)

    def test_puente_conserva_jpeg_hd_y_cambios_de_orientacion(self):
        anterior = dict(puente._ultimo)
        generador = puente.generar_mjpeg()
        try:
            for alto, ancho in ((720, 1280), (1920, 1080), (1080, 1920)):
                _, jpeg = cv2.imencode(".jpg", np.zeros((alto, ancho, 3), np.uint8))
                datos = jpeg.tobytes()
                respuesta = puente.app_iphone.test_client().post("/subir", data=datos, content_type="image/jpeg")
                self.assertEqual(respuesta.status_code, 204)
                paquete = next(generador)
                recibido = paquete.split(b"\r\n\r\n", 1)[1][:-2]
                self.assertEqual(recibido, datos)
                frame = cv2.imdecode(np.frombuffer(recibido, np.uint8), cv2.IMREAD_COLOR)
                self.assertEqual(frame.shape[:2], (alto, ancho))
        finally:
            generador.close()
            with puente._lock:
                puente._ultimo.update(anterior)
