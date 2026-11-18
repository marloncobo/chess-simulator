import unittest

from chess_simulator.regla_de_tres import calibrar, centimetros_a_metros


class ReglaDeTresTest(unittest.TestCase):
    def test_proyecciones_y_origen(self):
        escala = calibrar([(20,10), (420,12), (428,210), (8,212)], 41, 20)
        self.assertEqual(escala.lados, (400,420,202,198))
        self.assertEqual(escala.px_por_cm, (10,10))
        self.assertEqual(escala.cm_por_px, (.1,.1))
        self.assertEqual(escala.pixeles_a_cm(225,110), (20.5,10))
        self.assertEqual(centimetros_a_metros(20.5,10), (.205,.1))

    def test_centros_y_bordes(self):
        escala = calibrar([(30,20), (830,20), (830,820), (30,820)])
        for letra in "abcdefgh":
            for fila in "12345678":
                casilla = letra + fila
                self.assertEqual(escala.casilla(*escala.centro_cm(casilla)), casilla)
        self.assertEqual(escala.casilla(0,0), "a8")
        self.assertEqual(escala.casilla(40,40), "h1")
        self.assertEqual(escala.casilla(5,5), "b7")
        self.assertIsNone(escala.casilla(-.01,1))

    def test_orden_invalido(self):
        with self.assertRaises(ValueError):
            calibrar([(0,0),(0,100),(100,100),(100,0)])
