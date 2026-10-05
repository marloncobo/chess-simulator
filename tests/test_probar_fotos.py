import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chess_simulator.seguimiento import Observacion
import herramientas.probar_fotos as pf


class PruebasFotos(unittest.TestCase):
    def test_esquinas_se_guardan_por_foto_y_resolucion(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(pf, "CONFIG", Path(tmp)):
            pf.guardar_esquinas("a.jpg", (720, 1280, 3), [(0, 0), (8, 0), (8, 8), (0, 8)])
            guardadas = pf.leer_guardadas()
            self.assertIn(pf.clave("a.jpg", (720, 1280, 3)), guardadas)
            self.assertNotIn(pf.clave("a.jpg", (480, 640, 3)), guardadas)

    def test_tablero_texto_marca_dudas_y_vacias(self):
        obs = Observacion.desde_dict({"secuencia": 1, "completa": False, "desconocidas": ["b1"],
                                      "piezas": [{"casilla": "a1", "pieza": "T"}]})
        filas = pf.tablero_texto(obs)
        self.assertEqual(filas[7], "1  T  ?  ·  ·  ·  ·  ·  ·")

    def test_guardar_par_sirve_para_evaluar_pares(self):
        from herramientas.evaluar_pares import cargar_pares
        obs = Observacion.desde_dict({"secuencia": 1, "completa": True,
                                      "piezas": [{"casilla": "a1", "pieza": "T"}, {"casilla": "b2", "pieza": "?P"}]})
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "v" / "pares.json"
            esquinas = [[(0, 0), (8, 0), (8, 8), (0, 8)]] * 2
            pf.anadir_par(destino, [Path(tmp) / "x.jpg", Path(tmp) / "y.jpg"], esquinas, obs)
            par = cargar_pares(destino)[0]
            self.assertEqual(par["posicion"], {"a1": "T"})  # el color dudoso no se anota
            self.assertEqual(par["a"].resolve(), (Path(tmp) / "x.jpg").resolve())


if __name__ == "__main__":
    unittest.main()
