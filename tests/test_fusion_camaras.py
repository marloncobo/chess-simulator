import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from chess_simulator.fusion_camaras import fusionar, observar_vista, par_valido
from chess_simulator.seguimiento import Observacion, SeguimientoPorCasilla
from herramientas.deteccion_doble import SesionDoble, guardar, cargar, punto_original


ESQUINAS = [(0, 0), (800, 0), (800, 800), (0, 800)]


def obs(piezas=None, dudas=None, secuencia=1):
    piezas, dudas = piezas or {}, dudas or []
    return Observacion.desde_dict({"secuencia": secuencia, "confianza": .9,
        "completa": not dudas, "desconocidas": dudas,
        "piezas": [{"casilla": c, "pieza": p} for c, p in piezas.items()]})


def deteccion(x, y, pieza="T", color="BLANCA"):
    return {"pieza": pieza, "color": color, "conf": .9, "punto": (x, y),
            "poligono": np.int32([[x-20, y-30], [x+20, y-30], [x+20, y+20], [x-20, y+20]])}


class PruebasFusion(unittest.TestCase):
    def test_complementa_sin_duplicar(self):
        resultado, fuentes = fusionar([obs({"a1": "T"}), obs({"a1": "T", "h8": "r"})], 9)
        self.assertEqual(resultado.tablero[7][0], "T")
        self.assertEqual(resultado.tablero[0][7], "r")
        self.assertEqual(fuentes, {"a1": "1+2", "h8": "2"})
        self.assertEqual(sum(bool(p) for f in resultado.tablero for p in f), 2)
        self.assertEqual(resultado.confianzas[7][0], .9)

    def test_conflicto_de_tipo_y_color_no_elige_ganador(self):
        for pieza in ("A", "t"):
            resultado, _ = fusionar([obs({"a1": "T"}), obs({"a1": pieza})], 2)
            self.assertIn((7, 0), resultado.desconocidas)
            self.assertFalse(resultado.tablero[7][0])

    def test_una_vista_dudosa_no_anula_pieza_visible(self):
        resultado, fuentes = fusionar([obs(dudas=["a1"]), obs({"a1": "T"})], 2)
        self.assertEqual(resultado.tablero[7][0], "T")
        self.assertEqual(fuentes["a1"], "2")

    def test_vacio_requiere_dos_ausencias_fiables(self):
        resultado, _ = fusionar([obs(), obs(dudas=["a1"])], 2)
        self.assertIn((7, 0), resultado.desconocidas)
        resultado, _ = fusionar([obs(), obs()], 3)
        self.assertTrue(resultado.completa)

    def test_vistas_opuestas_proyectan_a_misma_casilla(self):
        a = observar_vista([deteccion(50, 750)], ESQUINAS, 1)
        b = observar_vista([deteccion(750, 50)], [(800, 800), (0, 800), (0, 0), (800, 0)], 1)
        resultado, fuentes = fusionar([a, b], 1)
        self.assertEqual(resultado.tablero[7][0], "T")
        self.assertEqual(fuentes["a1"], "1+2")

    def test_silueta_impide_borrar_casilla_tapada(self):
        d = deteccion(50, 150)
        d["poligono"] = np.int32([[10, 10], [90, 10], [90, 170], [10, 170]])
        vista = observar_vista([d], ESQUINAS, 1)
        self.assertEqual(vista.tablero[1][0], "T")
        self.assertIn((0, 0), vista.desconocidas)
        self.assertNotIn((0, 1), vista.desconocidas)

    def test_conflicto_y_oclusion_persistentes_conservan_estado(self):
        motor = SeguimientoPorCasilla()
        for i in range(4):
            resultado, _ = fusionar([obs({"a1": "T"}), obs({"a1": "T"})], i)
            motor.recibir(resultado, i*.3)
        self.assertEqual(motor.posicion[7][0], "T")
        for i in range(4, 20):
            vistas = [obs({"a1": "T"}), obs({"a1": "A"})] if i < 10 else [obs(), obs(dudas=["a1"])]
            resultado, _ = fusionar(vistas, i)
            motor.recibir(resultado, i*.3)
        self.assertEqual(motor.posicion[7][0], "T")

    def test_movimiento_se_confirma_con_dos_vistas(self):
        motor = SeguimientoPorCasilla()
        for i in range(14):
            piezas = {"a1": "T"} if i < 4 else {"a2": "T"}
            resultado, _ = fusionar([obs(piezas), obs(piezas)], i)
            motor.recibir(resultado, i*.3)
        self.assertEqual(motor.posicion[6][0], "T")
        self.assertFalse(motor.posicion[7][0])
        self.assertEqual(len(motor.historial), 1)
        self.assertEqual(motor.historial[0].origen, "a1")
        self.assertEqual(motor.historial[0].destino, "a2")

    def test_rechaza_par_antiguo_desfasado_o_incompleto(self):
        frame = np.zeros((10, 10, 3), np.uint8)
        a, b = {"frame": frame, "instante": 10}, {"frame": frame, "instante": 10.1}
        self.assertTrue(par_valido([a, b], 10.2))
        self.assertFalse(par_valido([a, b], 13))
        self.assertFalse(par_valido([a, {**b, "instante": 10.4}], 10.5))
        self.assertFalse(par_valido([a, None], 10.2))


class PruebasSesion(unittest.TestCase):
    def sesion(self):
        ahora = time.monotonic()
        frame = np.zeros((800, 800, 3), np.uint8)
        camaras = [SimpleNamespace(source=i, reinicios=0, estado={"frame": frame, "instante": ahora}) for i in (0, 1)]
        sesion = SesionDoble(camaras, SimpleNamespace(max_desfase_ms=250))
        sesion.comprobar_camaras()
        sesion.esquinas = [list(ESQUINAS), list(ESQUINAS)]
        return sesion

    def test_clic_respeta_bandas_y_segunda_camara(self):
        self.assertIsNone(punto_original(650, 130, 1, (800, 800, 3)))
        self.assertEqual(punto_original(640+320, 300, 1, (800, 800, 3)), (400, 400))

    def test_calibracion_separa_fuentes_y_resoluciones(self):
        with tempfile.TemporaryDirectory() as tmp, patch("herramientas.deteccion_doble.CONFIG", Path(tmp)):
            guardar("http://localhost/a", (800, 800), ESQUINAS)
            self.assertEqual(cargar("http://localhost/a", (800, 800)), [list(p) for p in ESQUINAS])
            with self.assertRaises(ValueError):
                cargar("http://localhost/a", (640, 480))
            with self.assertRaises(OSError):
                cargar("http://localhost/b", (800, 800))

    def test_reinicio_invalida_solo_calibracion_afectada(self):
        sesion = self.sesion()
        sesion.camaras[0].reinicios += 1
        revision = sesion.revision
        sesion.comprobar_camaras()
        self.assertGreater(sesion.revision, revision)
        self.assertEqual(sesion.esquinas[0], [])
        self.assertEqual(len(sesion.esquinas[1]), 4)

    def test_resultados_anteriores_a_recalibracion_se_descartan(self):
        sesion = self.sesion()
        self.assertFalse(sesion.recibir({"revision": sesion.revision-1}, time.monotonic()))
        self.assertEqual(sesion.secuencia, 0)

    def test_deteccion_estable_actualiza_tablero_y_dibuja(self):
        sesion = self.sesion()
        for i in range(5):
            ahora = time.monotonic() + i*.3
            vistas = [{**c.estado, "instante": ahora, "detecciones": [deteccion(50, 750)]}
                      for c in sesion.camaras]
            for c in sesion.camaras:
                c.estado["instante"] = ahora
            sesion.recibir({"revision": sesion.revision, "vistas": vistas, "inferencia": .05}, ahora)
        self.assertEqual(sesion.seguimiento.posicion[7][0], "T")
        self.assertEqual(sesion.dibujar(ahora).shape, (930, 1280, 3))


if __name__ == "__main__":
    unittest.main()
