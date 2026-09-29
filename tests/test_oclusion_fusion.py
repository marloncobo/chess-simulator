"""Regresiones de visibilidad, confirmación unilateral y geometría."""
import unittest
import numpy as np

from chess_simulator.fusion_camaras import FiltroCasillas, observar_vista, fusionar
from chess_simulator.diagnostico import diagnosticar, SOLO_2, RESCATE_2
from chess_simulator.seguimiento import SeguimientoPorCasilla
from tests.test_fusion_camaras import ESQUINAS, deteccion, obs
from tests import test_fusion_camaras as casos


def tablero():
    imagen = np.zeros((800, 800, 3), np.uint8)
    for f in range(8):
        for c in range(8):
            imagen[f*100:(f+1)*100, c*100:(c+1)*100] = (50, 120, 40) if (f+c)%2 else (230, 230, 230)
    return imagen


class PruebasVisibilidad(unittest.TestCase):
    def test_duda_de_color_no_se_cuenta_como_oclusion(self):
        vista = observar_vista([deteccion(50, 750, color="DUDOSA")], ESQUINAS, 1)
        self.assertEqual(vista.motivos[7, 0], "Color dudoso")
        combinado, _ = fusionar([vista, obs({"a1": "T"})], 1)
        info = diagnosticar([vista, obs({"a1": "T"})], combinado)[7, 0]
        self.assertEqual(info["estado"], SOLO_2)
        self.assertFalse(info["tapada1"])
        self.assertIn("Color dudoso", info["detalle"])

    def test_silueta_si_se_cuenta_como_rescate(self):
        d = deteccion(50, 150)
        d["poligono"] = np.int32([[10, 10], [90, 10], [90, 170], [10, 170]])
        vista = observar_vista([d], ESQUINAS, 1)
        otra = obs({"a8": "P"})
        combinado, _ = fusionar([vista, otra], 1)
        self.assertEqual(diagnosticar([vista, otra], combinado)[0, 0]["estado"], RESCATE_2)

    def test_movimiento_es_local_y_se_estabiliza(self):
        filtro = FiltroCasillas()
        imagen = tablero()
        self.assertEqual(len(filtro.evaluar(imagen, ESQUINAS, 0)), 64)
        self.assertFalse(filtro.evaluar(imagen, ESQUINAS, 1))
        imagen[200:300, 200:300] = (0, 0, 255)
        movimiento = filtro.evaluar(imagen, ESQUINAS, 1.1)
        self.assertIn((2, 2), movimiento)
        self.assertNotIn((7, 7), movimiento)
        self.assertFalse(filtro.evaluar(imagen, ESQUINAS, 2))

    def test_objeto_inmovil_no_se_confunde_con_fondo_vacio(self):
        filtro = FiltroCasillas()
        imagen = tablero()
        filtro.evaluar(imagen, ESQUINAS, 0)
        movimiento = filtro.evaluar(imagen, ESQUINAS, 1)
        vista = filtro.verificar_vacios(observar_vista([], ESQUINAS, 1, movimiento))
        self.assertTrue(vista.completa)
        imagen[200:300, 200:300] = (10, 10, 220)
        filtro.evaluar(imagen, ESQUINAS, 2)
        movimiento = filtro.evaluar(imagen, ESQUINAS, 4)
        self.assertFalse(movimiento)
        vista = filtro.verificar_vacios(observar_vista([], ESQUINAS, 2, movimiento))
        self.assertEqual(vista.motivos[2, 2], "Fondo no verificable")
        self.assertNotIn((7, 7), vista.desconocidas)

    def test_fondo_sin_referencias_suficientes_queda_dudoso(self):
        filtro = FiltroCasillas()
        filtro.evaluar(tablero(), ESQUINAS, 0)
        ds = [deteccion(c*100+50, f*100+50, pieza="P")
              for f in range(8) for c in range(8) if (f, c) != (3, 3)]
        vista = filtro.verificar_vacios(observar_vista(ds, ESQUINAS, 1))
        self.assertEqual(vista.motivos[3, 3], "Fondo no verificable")

    def test_camara_visible_rescata_otra_con_movimiento(self):
        sesion = casos.PruebasSesion().sesion()
        imagen = tablero()
        for i in range(12):
            ahora = 100 + i*.3
            tapada = imagen.copy()
            tapada[700:800, 0:100] = (0, 0, 255 if i%2 else 0)
            vistas = [{"frame": tapada, "instante": ahora, "detecciones": []},
                      {"frame": imagen, "instante": ahora, "detecciones": [deteccion(50, 750)]}]
            for c, v in zip(sesion.camaras, vistas):
                c.estado = v
            sesion.recibir({"revision": sesion.revision, "vistas": vistas, "inferencia": .05}, ahora)
        self.assertEqual(sesion.seguimiento.posicion[7][0], "T")
        self.assertEqual(sesion.procedencias["a1"], "2")

    def test_ocultacion_persistente_no_borra_pieza_confirmada(self):
        sesion = casos.PruebasSesion().sesion()
        imagen = tablero()
        for i in range(22):
            ahora = 100 + i*.3
            frame = imagen.copy()
            ds = [deteccion(50, 750)] if i < 6 else []
            if i >= 6:
                frame[700:800, :100] = (10, 10, 220)
            vistas = [{"frame": frame, "instante": ahora, "detecciones": ds} for _ in range(2)]
            for c, v in zip(sesion.camaras, vistas):
                c.estado = v
            sesion.recibir({"revision": sesion.revision, "vistas": vistas, "inferencia": .05}, ahora)
        self.assertEqual(sesion.seguimiento.posicion[7][0], "T")
        self.assertIn((7, 0), sesion.seguimiento.dudosas)

    def test_movimiento_real_sigue_pudiendo_vaciar_origen(self):
        sesion = casos.PruebasSesion().sesion()
        imagen = tablero()
        for i in range(23):
            ahora = 100 + i*.3
            ds = [deteccion(50, 750 if i < 6 else 650)]
            vistas = [{"frame": imagen, "instante": ahora, "detecciones": ds} for _ in range(2)]
            for c, v in zip(sesion.camaras, vistas):
                c.estado = v
            sesion.recibir({"revision": sesion.revision, "vistas": vistas, "inferencia": .05}, ahora)
        self.assertFalse(sesion.seguimiento.posicion[7][0])
        self.assertEqual(sesion.seguimiento.posicion[6][0], "T")
        self.assertEqual(len(sesion.seguimiento.historial), 1)


class PruebasConfirmacion(unittest.TestCase):
    def test_unilateral_debil_queda_pendiente(self):
        vista = observar_vista([{**deteccion(50, 750), "conf": .6}], ESQUINAS, 1)
        resultado, fuentes = fusionar([vista, obs()], 1)
        self.assertIn((7, 0), resultado.desconocidas)
        self.assertNotIn("a1", fuentes)

    def test_unilateral_requiere_mas_tiempo_que_coincidencia(self):
        motores = [SeguimientoPorCasilla(), SeguimientoPorCasilla()]
        for i in range(4):
            for indice, vistas in enumerate(([obs({"a1": "T"}), obs()], [obs({"a1": "T"}), obs({"a1": "T"})])):
                resultado, fuentes = fusionar(vistas, i)
                motores[indice].recibir(resultado, i*.3, fuentes)
        self.assertFalse(motores[0].posicion[7][0])
        self.assertEqual(motores[1].posicion[7][0], "T")
        for i in range(4, 7):
            resultado, fuentes = fusionar([obs({"a1": "T"}), obs()], i)
            motores[0].recibir(resultado, i*.3, fuentes)
        self.assertEqual(motores[0].posicion[7][0], "T")

    def test_repetir_secuencia_no_acumula_confirmaciones(self):
        motor = SeguimientoPorCasilla()
        resultado, fuentes = fusionar([obs({"a1": "T"}), obs()], 1)
        for i in range(20):
            motor.recibir(resultado, i*.3, fuentes)
        self.assertIsNone(motor.posicion)


class PruebasGeometria(unittest.TestCase):
    def test_apoyo_fronterizo_protege_ambas_casillas(self):
        vista = observar_vista([deteccion(99, 750)], ESQUINAS, 1)
        self.assertIn((7, 0), vista.desconocidas)
        self.assertIn((7, 1), vista.desconocidas)
        self.assertFalse(vista.tablero[7][0])
        otra = observar_vista([deteccion(50, 750)], ESQUINAS, 1)
        resultado, fuentes = fusionar([vista, otra], 1)
        self.assertEqual(resultado.tablero[7][0], "T")
        self.assertEqual(fuentes["a1"], "2")

    def test_apoyos_proximos_no_crean_dos_piezas(self):
        a = observar_vista([deteccion(85, 750)], ESQUINAS, 1)
        b = observar_vista([deteccion(115, 750)], ESQUINAS, 1)
        resultado, _ = fusionar([a, b], 1)
        self.assertIn((7, 0), resultado.desconocidas)
        self.assertIn((7, 1), resultado.desconocidas)
        self.assertFalse(resultado.tablero[7][0])
        self.assertFalse(resultado.tablero[7][1])

    def test_dos_piezas_vecinas_centradas_se_conservan(self):
        a = observar_vista([deteccion(50, 750)], ESQUINAS, 1)
        b = observar_vista([deteccion(150, 750)], ESQUINAS, 1)
        resultado, _ = fusionar([a, b], 1)
        self.assertEqual(resultado.tablero[7][:2], ("T", "T"))


if __name__ == "__main__":
    unittest.main()
