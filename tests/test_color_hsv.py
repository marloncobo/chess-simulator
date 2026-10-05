import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np
import pygame

from chess_simulator.color_hsv import clasificar
from chess_simulator.main import main
from chess_simulator.seguimiento import SeguimientoPorCasilla
from chess_simulator.tablero_pygame import dibujar_piezas
from chess_simulator.vision_vivo import extraer, construir_observacion

ESQUINAS = [(0, 0), (800, 0), (800, 800), (0, 800)]
POLIGONO = np.array([[10, 10], [40, 10], [40, 90], [10, 90]])


def deteccion(color, x=50, pieza='P', conf=.9):
    return dict(pieza=pieza, punto=(x, 50), conf=conf, color=color)


class PruebasColor(unittest.TestCase):
    def test_colores_en_interior_sin_fondo_verde(self):
        for bgr, esperado in [((25, 25, 25), 'NEGRA'), ((170, 205, 220), 'BLANCA'),
                              ((115, 115, 115), 'DUDOSA'), ((0, 210, 0), 'DUDOSA')]:
            with self.subTest(color=esperado, bgr=bgr):
                frame = np.full((100, 100, 3), (0, 150, 0), np.uint8)
                cv2.fillPoly(frame, [POLIGONO], bgr)
                medida = clasificar(cv2.cvtColor(frame, cv2.COLOR_BGR2HSV), POLIGONO)
                self.assertEqual(medida['color'], esperado)
                self.assertGreater(medida['n'], 20)

    def test_mascara_pequena_o_exterior_no_inventa_color(self):
        hsv = np.zeros((100, 100, 3), np.uint8)
        for p in (np.array([[1,1],[3,1],[3,3],[1,3]]), POLIGONO+200):
            self.assertEqual(clasificar(hsv, p)['color'], 'DUDOSA')

    def test_umbral_ajustable_y_validacion(self):
        hsv = np.full((100, 100, 3), (0, 0, 100), np.uint8)
        self.assertEqual(clasificar(hsv, POLIGONO)['color'], 'DUDOSA')
        self.assertEqual(clasificar(hsv, POLIGONO, negra_max=110)['color'], 'NEGRA')
        for kwargs in [dict(negra_max=150), dict(erosion=-1), dict(saturacion_max=300)]:
            with self.assertRaises(ValueError):
                clasificar(hsv, POLIGONO, **kwargs)

    def test_modelo_a_codigo_de_tablero_para_seis_tipos_y_colores(self):
        for tipo, codigo in {'TOWER':'T','HORSE':'C','BISHOP':'A','QUEEN':'D','KING':'R','PAWN':'P'}.items():
            resultado = SimpleNamespace(masks=SimpleNamespace(xy=[POLIGONO]),
                names={0:tipo}, boxes=SimpleNamespace(cls=[0], conf=[.9]))
            for tono, esperado in [(25, codigo.lower()), (220, codigo)]:
                ds = extraer(resultado, np.full((100,100,3), tono, np.uint8))
                obs, _, _, _ = construir_observacion(ds, ESQUINAS, 1)
                self.assertEqual(obs.tablero[0][0], esperado)

    def test_duda_conserva_color_confirmado_y_actualiza_otras(self):
        motor = SeguimientoPorCasilla()
        for i in range(5):
            obs, *_ = construir_observacion([deteccion('BLANCA')], ESQUINAS, i)
            motor.recibir(obs, i*.25)
        for i in range(5, 12):
            ds = [deteccion('DUDOSA'), deteccion('NEGRA',150)]
            obs, *_ = construir_observacion(ds, ESQUINAS, i)
            motor.recibir(obs, i*.25)
        self.assertEqual(motor.posicion[0][:2], ('P','p'))
        self.assertIn((0,0), motor.dudosas)

    def test_flicker_de_color_no_cambia_estado_confirmado(self):
        motor = SeguimientoPorCasilla()
        for i in range(15):
            color = 'BLANCA' if i<5 or i%2 else 'NEGRA'
            obs, *_ = construir_observacion([deteccion(color)], ESQUINAS, i)
            motor.recibir(obs, i*.25)
        self.assertEqual(motor.posicion[0][0], 'P')
        self.assertEqual(motor.historial, [])

    def test_cuatro_torres_en_total_incluye_ambos_colores(self):
        ds = [deteccion('BLANCA' if c%2 else 'NEGRA',50+c*100,'T',.95-c*.04) for c in range(6)]
        motor = SeguimientoPorCasilla()
        for i in range(5):
            obs, *_ = construir_observacion(ds, ESQUINAS, i)
            motor.recibir(obs, i*.25)
        self.assertEqual(motor.posicion[0][:6], ('t','T','t','T','',''))

    def test_cli_envia_umbrales_a_camara(self):
        with patch('chess_simulator.tiempo_real.ejecutar') as ejecutar:
            main(['--camara','--hsv-negra-max','90','--hsv-erosion','2'])
        self.assertEqual(ejecutar.call_args.args[1], 1)
        self.assertEqual(ejecutar.call_args.kwargs['parametros_hsv'],
                         dict(negra_max=90, blanca_min=125, saturacion_max=110, erosion=2))

    def test_cli_acepta_url_del_celular(self):
        url = 'http://127.0.0.1:5002/stream'
        with patch('chess_simulator.tiempo_real.ejecutar') as ejecutar:
            main(['--camara', '--source', url])
        self.assertEqual(ejecutar.call_args.args[1], url)
        with self.assertRaises(SystemExit):
            main(['--camara', '--source', url, '--backend', 'dshow'])

    def test_pygame_dibuja_blancas_y_negras(self):
        pygame.font.init()
        try:
            pantalla = pygame.Surface((640,640))
            pantalla.fill((100,100,100))
            posicion = [['']*8 for _ in range(8)]
            posicion[0][:2] = ['P','p']
            dibujar_piezas(pantalla, pygame.font.SysFont('segoeuisymbol',56), posicion)
            pix = pygame.surfarray.array3d(pantalla)
            self.assertTrue(np.any(np.all(pix[:80,:80] == 255, axis=2)))
            self.assertTrue(np.any(np.all(pix[80:160,:80] == 20, axis=2)))
        finally:
            pygame.font.quit()


if __name__ == '__main__':
    unittest.main()
