import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from chess_simulator.calibracion import (cargar_calibracion, guardar_calibracion,
                                        cargar_tablero, guardar_tablero, cargar_camara)
from chess_simulator.coordenadas_tablero import TableroFisico
from tests.test_vivo import ESQUINAS


class PruebasCalibracion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ruta = Path(self.tmp.name) / "perfil.json"
        self.tablero = TableroFisico("principal", .4, .4)

    def test_perfil_fisico_y_contexto(self):
        guardar_tablero(self.ruta, self.tablero)
        self.assertEqual(cargar_tablero(self.ruta), self.tablero)
        guardar_calibracion(self.ruta, 1, (800, 800), ESQUINAS, self.tablero, "montaje-v1")
        self.assertEqual(len(cargar_calibracion(self.ruta, 1, (800, 800), self.tablero, "montaje-v1")), 4)
        datos = json.loads(self.ruta.read_text(encoding="utf-8"))
        self.assertEqual(datos["version"], 1)
        self.assertTrue(datos["fecha"])
        for source, resolucion, tablero, contexto in [
                (0, (800, 800), self.tablero, "montaje-v1"),
                (1, (1280, 720), self.tablero, "montaje-v1"),
                (1, (800, 800), TableroFisico("principal", .41, .4), "montaje-v1"),
                (1, (800, 800), self.tablero, "zoom-nuevo")]:
            with self.assertRaises(ValueError):
                cargar_calibracion(self.ruta, source, resolucion, tablero, contexto)

    def test_legados_solo_casillas_y_migracion_con_recalibracion(self):
        for doble in (False, True):
            datos = {"resolucion": [800, 800], "esquinas": ESQUINAS}
            if not doble:
                datos["source"] = 1
            self.ruta.write_text(json.dumps(datos), encoding="utf-8")
            self.assertEqual(len(cargar_calibracion(self.ruta, 1, (800, 800), legado_doble=doble)), 4)
            with self.assertRaises(ValueError):
                cargar_calibracion(self.ruta, 1, (800, 800), self.tablero, legado_doble=doble)
        guardar_calibracion(self.ruta, 1, (800, 800), ESQUINAS, self.tablero)
        self.assertEqual(len(cargar_calibracion(self.ruta, 1, (800, 800), self.tablero)), 4)

    def test_formato_comun_entre_interfaces_y_fallback_antiguo(self):
        from herramientas.deteccion_doble import guardar, cargar
        with patch("herramientas.deteccion_doble.CONFIG", Path(self.tmp.name)):
            guardar(1, (800, 800), ESQUINAS, self.tablero)
            self.assertEqual(len(cargar_camara(1, (800, 800), self.tablero, directorio=self.tmp.name)), 4)
            self.assertEqual(len(cargar(1, (800, 800), self.tablero)), 4)
        legado = Path(self.tmp.name) / "calibracion_camara_2.json"
        legado.write_text(json.dumps({"source": 2, "resolucion": [800, 800], "esquinas": ESQUINAS}))
        self.assertEqual(len(cargar_camara(2, (800, 800), directorio=self.tmp.name)), 4)
        huella = hashlib.sha256(str(3).encode()).hexdigest()[:16]
        legado = Path(self.tmp.name) / f"calibracion_doble_{huella}.json"
        legado.write_text(json.dumps({"resolucion": [800, 800], "esquinas": ESQUINAS}))
        self.assertEqual(len(cargar_camara(3, (800, 800), modo="doble", directorio=self.tmp.name)), 4)

    def test_informe_cli_con_medidas_sinteticas(self):
        from herramientas.verificar_calibracion import main
        tablero = Path(self.tmp.name) / "tablero.json"
        medidas = Path(self.tmp.name) / "medidas.json"
        salida = Path(self.tmp.name) / "informe.json"
        guardar_tablero(tablero, self.tablero)
        guardar_calibracion(self.ruta, 1, (800, 800), ESQUINAS, self.tablero)
        medidas.write_text(json.dumps({"source": 1, "resolucion": [800, 800],
            "muestras": [{"id": "centro", "pixel": [400, 400], "xy_m": [.2, .2]}]}))
        informe = main(["--tablero", str(tablero), "--calibracion", str(self.ruta),
                        "--medidas", str(medidas), "--salida", str(salida)])
        self.assertEqual(informe["error_max_mm"], 0)
        self.assertEqual(json.loads(salida.read_text(encoding="utf-8"))["cantidad"], 1)
        self.assertIsNone(informe["dentro_tolerancia"])

    def test_rechaza_version_ejes_y_geometria_invalidos(self):
        guardar_calibracion(self.ruta, 1, (800, 800), ESQUINAS, self.tablero)
        base = json.loads(self.ruta.read_text(encoding="utf-8"))
        for cambios in ({"version": 9}, {"esquinas": []}, {"resolucion": [0, 800]},
                        {"esquinas": [[0, 0], [900, 0], [800, 800], [0, 800]]}):
            self.ruta.write_text(json.dumps({**base, **cambios}), encoding="utf-8")
            with self.assertRaises(ValueError):
                cargar_calibracion(self.ruta, 1, (800, 800), self.tablero)
        datos = self.tablero.a_dict()
        datos["ejes"]["origen"] = "a1"
        self.ruta.write_text(json.dumps(datos), encoding="utf-8")
        with self.assertRaises(ValueError):
            cargar_tablero(self.ruta)
