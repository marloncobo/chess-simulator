import unittest

from chess_simulator.coordenadas_tablero import TableroFisico
from chess_simulator.vision_vivo import construir_observacion
from chess_simulator.fusion_camaras import observar_vista, fusionar
from herramientas.verificar_calibracion import evaluar
from tests.test_fusion_camaras import deteccion, ESQUINAS


class PruebasCoordenadas(unittest.TestCase):
    def test_escala_orientacion_y_centros(self):
        tablero = TableroFisico("rectangular", .4, .48)
        for punto, esperado in [((0, 0), (0, 0)), ((8, 0), (.4, 0)),
                                ((8, 8), (.4, .48)), ((0, 8), (0, .48)), ((4, 4), (.2, .24))]:
            self.assertEqual(tablero.a_metros(*punto), esperado)
        self.assertEqual(tablero.centro("a8"), (.025, .03))
        self.assertAlmostEqual(tablero.centro("h1")[0], .375)
        self.assertAlmostEqual(tablero.centro("h1")[1], .45)
        self.assertAlmostEqual(TableroFisico("cuadrado", .4, .4).a_metros(4.3, 3.6)[0], .215)

    def test_rechaza_dimensiones_limites_y_casillas_invalidas(self):
        for valor in (0, -1, float("nan"), float("inf"), True, "0.4"):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                TableroFisico("tablero", valor, .4)
        tablero = TableroFisico("tablero", .4, .4)
        for punto in ((-0.1, 4), (8.1, 0), (0, float("nan"))):
            with self.assertRaises(ValueError):
                tablero.a_metros(*punto)
        for casilla in ("a0", "i8", "e44", None):
            with self.assertRaises(ValueError):
                tablero.centro(casilla)

    def test_apoyo_continuo_corresponde_al_candidato_aceptado(self):
        apoyos = {"viejo": 1}
        ds = [deteccion(430, 360), {**deteccion(435, 365), "conf": .3}]
        construir_observacion(ds, ESQUINAS, 1, apoyos)
        self.assertEqual(set(apoyos), {(3, 4)})
        self.assertAlmostEqual(apoyos[3, 4][0], 4.3, places=5)
        self.assertAlmostEqual(apoyos[3, 4][1], 3.6, places=5)
        # Dos apoyos distintos en una casilla no publican coordenadas.
        construir_observacion([deteccion(410, 310), deteccion(490, 390)], ESQUINAS, 2, apoyos)
        self.assertEqual(apoyos, {})

    def test_descartados_por_limite_no_publican_apoyos(self):
        apoyos = {}
        ds = [{**deteccion(50+c*100, 50), "conf": .95-c*.05} for c in range(6)]
        construir_observacion(ds, ESQUINAS, 1, apoyos)
        self.assertEqual(set(apoyos), {(0, c) for c in range(4)})

    def test_fusion_conserva_procedencia_y_discrepancia(self):
        vistas = [observar_vista([deteccion(x, 350)], ESQUINAS, 1) for x in (430, 450)]
        tablero = TableroFisico("tablero", .4, .4)
        obs, _ = fusionar(vistas, 1, tablero=tablero, max_discrepancia_m=.005)
        medida = obs.posiciones_fisicas[3, 4]
        self.assertAlmostEqual(medida["xy_m"][0], .22, places=6)
        self.assertAlmostEqual(medida["discrepancia_m"], .01, places=6)
        self.assertEqual([m["vista"] for m in medida["muestras"]], [1, 2])
        self.assertFalse(medida["dentro_tolerancia"])
        # La discrepancia física no inventa una discrepancia de tipo/casilla.
        self.assertEqual(obs.tablero[3][4], "T")

    def test_movimiento_o_conflicto_no_aporta_posicion_fisica(self):
        vista = observar_vista([deteccion(450, 350)], ESQUINAS, 1, movimiento={(3, 4)})
        self.assertNotIn((3, 4), vista.apoyos)
        otra = observar_vista([deteccion(450, 350, pieza="P")], ESQUINAS, 1)
        buena = observar_vista([deteccion(450, 350)], ESQUINAS, 1)
        obs, _ = fusionar([otra, buena], 1, tablero=TableroFisico("t", .4, .4))
        self.assertNotIn((3, 4), obs.posiciones_fisicas)

    def test_informe_error_conocido_y_repetibilidad(self):
        muestras = [{"id": "centro", "pixel": [400, 400], "xy_m": [.2, .2]},
                    {"id": "centro", "pixel": [406, 408], "xy_m": [.2, .2]}]
        informe = evaluar(ESQUINAS, TableroFisico("t", .4, .4), muestras, 4)
        self.assertAlmostEqual(informe["error_medio_mm"], 2.5, places=4)
        self.assertAlmostEqual(informe["error_max_mm"], 5, places=4)
        self.assertAlmostEqual(informe["repetibilidad"]["centro"]["dispersion_max_mm"], 5, places=4)
        self.assertFalse(informe["dentro_tolerancia"])
        for datos in ([], [{"id": "esquina", "pixel": [0, 0], "xy_m": [0, 0]}]):
            with self.assertRaises(ValueError):
                evaluar(ESQUINAS, TableroFisico("t", .4, .4), datos)
