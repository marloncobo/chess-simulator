import unittest
from unittest.mock import patch

from main import main, proyectar


class PruebasMain(unittest.TestCase):
    def test_proyecta_sin_posiciones_prefijadas(self):
        posicion, asignadas, fuera = proyectar(
            [{"centro": (150, 250)}, {"centro": (750, 650)}],
            [(0, 0), (800, 0), (800, 800), (0, 800)],
        )
        self.assertEqual(asignadas, [(1, "b6"), (2, "h2")])
        self.assertEqual(posicion[2][1], "?")
        self.assertEqual(sum(bool(p) for f in posicion for p in f), 2)
        self.assertEqual(fuera, [])

    def test_corrige_perspectiva(self):
        # Transformación x=100+80u/(1+0.1v), y=50+80v/(1+0.1v).
        def punto(u, v):
            return (100 + 80*u/(1+0.1*v), 50 + 80*v/(1+0.1*v))
        esquinas = [punto(0, 0), punto(8, 0), punto(8, 8), punto(0, 8)]
        _, asignadas, _ = proyectar([{"centro": punto(2.5, 4.5)}], esquinas)
        self.assertEqual(asignadas, [(1, "c4")])

    def test_no_fuerza_detecciones_exteriores_dentro_del_tablero(self):
        posicion, asignadas, fuera = proyectar(
            [{"centro": (-1, 20)}, {"centro": (800, 20)}],
            [(0, 0), (800, 0), (800, 800), (0, 800)],
        )
        self.assertEqual(asignadas, [])
        self.assertEqual(fuera, [1, 2])
        self.assertFalse(any(p for f in posicion for p in f))

    def test_rechaza_calibracion_invalida_y_colisiones(self):
        for esquinas in ([], [(0, 0)] * 4, [(0, 0), (800, 800), (800, 0), (0, 800)]):
            with self.subTest(esquinas=esquinas), self.assertRaises(ValueError):
                proyectar([], esquinas)
        with self.assertRaises(ValueError):
            proyectar([{"centro": (10, 10)}, {"centro": (20, 20)}],
                      [(0, 0), (800, 0), (800, 800), (0, 800)])

    def test_delega_entrada_al_seguimiento_existente(self):
        with patch("tablero_pygame.main") as ejecutar:
            main(["--entrada", "observacion.json"])
            ejecutar.assert_called_once_with(["--entrada", "observacion.json"])


if __name__ == "__main__":
    unittest.main()
