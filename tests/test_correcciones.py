"""Pruebas de las cinco correcciones del documento de contexto (problemas 1 a 5).

El problema 5 (calibración y reinicios) está en test_fusion_camaras.PruebasSesion.
"""
from types import SimpleNamespace
import unittest

import cv2
import numpy as np

from chess_simulator.detector_doble import inferir_par
from chess_simulator.fusion_camaras import fusionar, observar_vista
from chess_simulator.reglas_deteccion import CONFIANZA_DETECTOR, LIMITES, UMBRAL_DUDA, excedentes
from chess_simulator.seguimiento import Observacion, SeguimientoPorCasilla
from chess_simulator.vision_vivo import apoyo_tablero, construir_observacion, extraer, homografia
from herramientas.probar_dos_camaras import argumentos

ESQUINAS = [(0, 0), (800, 0), (800, 800), (0, 800)]


def deteccion(pieza="C", x=50, y=50, conf=.9, color="BLANCA"):
    poligono = np.array([[x-20, y-60], [x+20, y-60], [x+20, y], [x-20, y]], np.int32)
    return {"pieza": pieza, "punto": (x, y), "conf": conf, "color": color, "poligono": poligono}


def en(casilla, **kw):
    """Detección apoyada en el centro de la casilla, con ESQUINAS de 100 px."""
    c, f = ord(casilla[0]) - 97, 8 - int(casilla[1])
    return deteccion(x=c*100+50, y=f*100+50, **kw)


class PruebasLimitesPorClase(unittest.TestCase):
    """Problema 1: antes solo existía MAX_TORRES."""

    def test_tabla_cubre_las_seis_clases(self):
        self.assertEqual(LIMITES, {"R": 2, "D": 2, "T": 4, "A": 4, "C": 4, "P": 16})

    def test_cinco_caballos_quedan_cuatro(self):
        ds = [en(c, conf=.9-i*.05) for i, c in enumerate(("a3", "b3", "c3", "d3", "e3"))]
        obs, _, _, razones = construir_observacion(ds, ESQUINAS, 1)
        self.assertEqual(sum(p == "C" for f in obs.tablero for p in f), 4)
        self.assertEqual(obs.desconocidas, frozenset({(5, 4)}))  # e3, la menos fiable
        self.assertTrue(any(r.startswith("Límite de 4 caballos") for r in razones))

    def test_tres_reyes_quedan_dos_y_uno_por_color(self):
        ds = [en("a1", pieza="R", conf=.95), en("b1", pieza="R", conf=.9),
              en("c8", pieza="R", conf=.85, color="NEGRA")]
        obs, _, _, razones = construir_observacion(ds, ESQUINAS, 1)
        self.assertEqual(obs.tablero[7][0], "R")
        self.assertEqual(obs.tablero[7][1], "")       # segundo rey blanco
        self.assertEqual(obs.tablero[0][2], "r")      # el negro se conserva
        self.assertIn((7, 1), obs.desconocidas)
        self.assertTrue(any("por color" in r for r in razones))

    def test_reyes_sin_color_resuelto_solo_cuentan_para_el_total(self):
        sobran = excedentes([("x", "?R"), ("y", "?R"), ("z", "?R")], lambda k: k)
        self.assertEqual(set(sobran), {"z"})

    def test_seguimiento_no_acumula_caballos_retenidos(self):
        motor = SeguimientoPorCasilla()
        for i in range(20):
            fila = "3" if i < 5 else "4"
            ds = [en(c+fila) for c in "abcd"]
            if i >= 5:  # los de la fila 3 desaparecen de la vista pero siguen retenidos
                ds += [en(c+"3", conf=.6) for c in "efgh"]
            obs, _, _, _ = construir_observacion(ds, ESQUINAS, i)
            motor.recibir(obs, i*.25)
            if motor.posicion is not None:
                self.assertLessEqual(sum(p == "C" for f in motor.posicion for p in f), 4)


class PruebasRedesDeSeguridad(unittest.TestCase):
    """Problema 2: con dos cámaras el umbral de duda y el del seguimiento estaban inertes."""

    def test_el_detector_filtra_por_debajo_del_umbral_de_duda(self):
        self.assertLess(CONFIANZA_DETECTOR, UMBRAL_DUDA)
        self.assertEqual(inferir_par.__defaults__[-1], CONFIANZA_DETECTOR)

    def test_argumentos_aceptan_confianza_baja(self):
        self.assertEqual(argumentos(["--sources", "0", "1"]).confianza, CONFIANZA_DETECTOR)
        self.assertEqual(argumentos(["--sources", "0", "1", "--confianza", ".25"]).confianza, .25)
        for valor in (".01", "1.5", "nan"):
            with self.assertRaises(SystemExit):
                argumentos(["--sources", "0", "1", "--confianza", valor])

    def test_deteccion_debil_deja_la_casilla_en_duda_no_vacia(self):
        vista = observar_vista([en("d4", conf=.3)], ESQUINAS, 1)
        self.assertIn((4, 3), vista.desconocidas)
        self.assertEqual(vista.motivos[4, 3], "Baja confianza")

    def test_lectura_debil_de_la_misma_silueta_no_anula_la_firme(self):
        ds = [en("e5", pieza="R", conf=.96), {**en("e5", pieza="R", conf=.38), "punto": (474, 352)}]
        obs, _, _, razones = construir_observacion(ds, ESQUINAS, 1)
        self.assertEqual(obs.tablero[3][4], "R")
        self.assertEqual(razones, [])

    def test_dos_lecturas_firmes_distintas_siguen_en_conflicto(self):
        ds = [en("e5", pieza="R", conf=.9), {**en("e5", pieza="D", conf=.85), "punto": (474, 352)}]
        obs, _, _, razones = construir_observacion(ds, ESQUINAS, 1)
        self.assertIn((3, 4), obs.desconocidas)
        self.assertIn("Detecciones en conflicto", razones[0])

    def test_otra_camara_confirma_la_pieza_medio_tapada(self):
        debil = observar_vista([en("d4", conf=.3)], ESQUINAS, 1)
        firme = observar_vista([en("d4", conf=.92)], ESQUINAS, 1)
        fusion, procedencias = fusionar([debil, firme], 1)
        self.assertEqual(fusion.tablero[4][3], "C")
        self.assertEqual(procedencias["d4"], "2")

    def test_fusion_informa_confianza_real(self):
        a = observar_vista([en("a1", conf=.8), en("h8", conf=.95)], ESQUINAS, 1)
        fusion, _ = fusionar([a, a], 1)
        self.assertAlmostEqual(fusion.confianza, .8)
        self.assertAlmostEqual(fusion.confianzas[7][0], .8)

    def test_seguimiento_corta_por_casilla_sin_bloquear_el_resto(self):
        motor = SeguimientoPorCasilla()
        for i in range(12):
            obs = Observacion.desde_dict({"secuencia": i, "completa": True, "confianza": 1.,
                                          "piezas": [{"casilla": "a1", "pieza": "T"},
                                                     {"casilla": "b1", "pieza": "C"}],
                                          "confianzas": {"a1": .95, "b1": .3}})
            motor.recibir(obs, i*.3)
        self.assertEqual(motor.posicion[7][0], "T")
        self.assertEqual(motor.posicion[7][1], "")
        self.assertIn((7, 1), motor.dudosas)


class PruebasMotivos(unittest.TestCase):
    """Problema 3: razon se sobrescribía y se perdía 'Color dudoso'."""

    def test_color_dudoso_y_baja_confianza_se_conservan(self):
        d = en("c4", conf=.3, color="DUDOSA")
        _, _, _, razones = construir_observacion([d], ESQUINAS, 1)
        self.assertEqual(razones, ["Color dudoso + Baja confianza en c4"])
        vista = observar_vista([d], ESQUINAS, 1)
        self.assertEqual(vista.motivos[4, 2], "Color dudoso + Baja confianza")

    def test_motivo_llega_hasta_la_fusion(self):
        a = observar_vista([en("c4", conf=.3, color="DUDOSA")], ESQUINAS, 1)
        fusion, _ = fusionar([a, a], 1)
        self.assertIn("Color dudoso + Baja confianza", fusion.motivos[4, 2])

    def test_conflicto_entre_vistas_queda_explicado(self):
        a = observar_vista([en("g6", pieza="T", color="NEGRA")], ESQUINAS, 1)
        b = observar_vista([en("g6", pieza="P", color="NEGRA")], ESQUINAS, 1)
        fusion, _ = fusionar([a, b], 1)
        self.assertEqual(fusion.motivos[2, 6], "Las vistas discrepan: t / p")


class PruebasVaciasConDosCamaras(unittest.TestCase):
    """Una casilla tapada en una cámara y vista vacía en la otra es vacía, no incierta."""

    def vistas(self, motivo_1):
        from chess_simulator.fusion_camaras import con_dudas
        base = observar_vista([], ESQUINAS, 1)
        return [con_dudas(base, {(4, 4): motivo_1}), base]

    def test_oclusion_en_una_y_vacia_en_otra_es_vacia(self):
        from chess_simulator.diagnostico import diagnosticar, VACIA
        vistas = self.vistas("Oclusion por silueta")
        fusion, _ = fusionar(vistas, 1)
        self.assertNotIn((4, 4), fusion.desconocidas)
        self.assertEqual(fusion.tablero[4][4], "")
        self.assertEqual(diagnosticar(vistas, fusion)[4, 4]["estado"], VACIA)

    def test_indicios_de_pieza_mantienen_la_duda(self):
        for motivo in ("Fondo no verificable", "Baja confianza", "Movimiento local",
                       "Oclusion por silueta + Baja confianza", "Apoyo cerca del borde"):
            with self.subTest(motivo=motivo):
                fusion, _ = fusionar(self.vistas(motivo), 1)
                self.assertIn((4, 4), fusion.desconocidas)

    def test_tapada_en_las_dos_sigue_en_duda(self):
        from chess_simulator.fusion_camaras import con_dudas
        base = observar_vista([], ESQUINAS, 1)
        tapada = con_dudas(base, {(4, 4): "Oclusion por silueta"})
        fusion, _ = fusionar([tapada, tapada], 1)
        self.assertIn((4, 4), fusion.desconocidas)


def _camara(elevacion, distancia=11., focal=900., ancho=1280, alto=720):
    e = np.radians(elevacion)
    centro = np.array([4, 4 + distancia*np.cos(e), distancia*np.sin(e)])
    z = np.array([4., 4., 0.]) - centro
    z /= np.linalg.norm(z)
    x = np.cross(z, [0, 0, 1.])
    x /= np.linalg.norm(x)
    R = np.stack([x, np.cross(z, x), z])
    K = np.array([[focal, 0, ancho/2], [0, focal, alto/2], [0, 0, 1]])

    def proyectar(P):
        q = (K @ (R @ (np.asarray(P, float).T - centro[:, None]))).T
        return q[:, :2] / q[:, 2:]
    return proyectar


def _silueta(proyectar, cx, cy, altura, forma=(720, 1280)):
    """Pieza de revolución: base ancha, cuerpo estrecho, cabeza."""
    mascara = np.zeros(forma, np.uint8)
    angulos = np.linspace(0, 2*np.pi, 48)
    for z in np.linspace(0, altura, 50):
        r = .36 if z < .1*altura else .2 if z < .85*altura else .17
        P = np.stack([cx + r*np.cos(angulos), cy + r*np.sin(angulos), np.full_like(angulos, z)], 1)
        cv2.fillPoly(mascara, [np.rint(proyectar(P)).astype(np.int32)], 255)
    return mascara


class PruebasPuntoDeApoyo(unittest.TestCase):
    """Problema 4: el cuantil 0.8 deja el apoyo delante del centro real, no detrás.

    Subir a 0.9 empeoraba (medido: +0.13 casillas en fotos reales frente a
    +0.07 con 0.8). El apoyo se estima ahora en el plano: frente de la base
    menos medio ancho de base.
    """

    def test_estimador_geometrico_cerca_del_centro_real(self):
        rng = np.random.default_rng(1)
        for elevacion in (25, 45, 65):
            proyectar = _camara(elevacion)
            esquinas = proyectar([[0, 0, 0], [8, 0, 0], [8, 8, 0], [0, 8, 0]])
            matriz = homografia(esquinas)
            for altura in (.9, 2.):
                cx, cy = rng.uniform(1, 7, 2)
                mascara = _silueta(proyectar, cx, cy, altura)
                contorno = max(cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0],
                               key=cv2.contourArea).reshape(-1, 2)
                resultado = SimpleNamespace(masks=SimpleNamespace(xy=[contorno]), names={0: "PAWN"},
                                            boxes=SimpleNamespace(cls=[0], conf=[.9]))
                d = extraer(resultado, np.zeros((720, 1280, 3), np.uint8))[0]
                with self.subTest(elevacion=elevacion, altura=altura):
                    self.assertIsNotNone(d["base"])
                    x, y = apoyo_tablero(d, matriz)
                    error = np.hypot(x-cx, y-cy)
                    vx, vy = apoyo_tablero({"punto": d["punto"]}, matriz)
                    self.assertLess(error, .17)
                    self.assertLess(error, np.hypot(vx-cx, vy-cy) + .02)

    def test_sin_base_usa_el_punto(self):
        self.assertEqual(apoyo_tablero({"punto": (150, 250)}, homografia(ESQUINAS)), (1.5, 2.5))

    def test_silueta_cortada_por_abajo_no_inventa_base(self):
        poligono = np.array([[40, 10], [60, 10], [60, 99], [40, 99]], np.int32)
        resultado = SimpleNamespace(masks=SimpleNamespace(xy=[poligono]), names={0: "PAWN"},
                                    boxes=SimpleNamespace(cls=[0], conf=[.9]))
        self.assertIsNone(extraer(resultado, np.zeros((100, 100, 3), np.uint8))[0]["base"])


if __name__ == "__main__":
    unittest.main()
