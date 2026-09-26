import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from entrada import EntradaArchivo, publicar
from seguimiento import Observacion, Seguimiento, detectar_movimiento, indices


def observacion(secuencia, piezas, completa=True, confianza=1):
    return Observacion.desde_dict({
        "secuencia": secuencia, "completa": completa, "confianza": confianza,
        "piezas": [{"casilla": c, "pieza": p} for c, p in piezas.items()],
    })


def tablero(piezas):
    return observacion(0, piezas).tablero


class PruebasSeguimiento(unittest.TestCase):
    def setUp(self):
        self.motor = Seguimiento()
        self.seq = 0
        self.t = 0

    def enviar(self, piezas, completa=True, confianza=1, intervalo=0.21):
        self.seq += 1
        self.t += intervalo
        return self.motor.recibir(observacion(self.seq, piezas, completa, confianza), self.t)

    def estabilizar(self, piezas):
        resultado = None
        for _ in range(3):
            resultado = self.enviar(piezas)
        return resultado

    def test_sincroniza_posicion_arbitraria(self):
        self.enviar({"b4": "T"})
        self.assertIsNone(self.motor.posicion)
        self.enviar({"b4": "T"})
        self.enviar({"b4": "T"})
        self.assertEqual(self.motor.posicion, tablero({"b4": "T"}))
        self.assertEqual(self.motor.historial, [])

    def test_reflejo_construye_y_redistribuye_solo_piezas_detectadas(self):
        self.motor = Seguimiento(reflejar_observaciones=True)
        self.assertIsNone(self.motor.posicion)
        self.estabilizar({"b4": "T", "e6": "p"})
        self.assertEqual(self.motor.posicion, tablero({"b4": "T", "e6": "p"}))
        self.estabilizar({"c7": "D", "h2": "t", "f5": "A"})
        self.assertEqual(self.motor.posicion, tablero({"c7": "D", "h2": "t", "f5": "A"}))
        self.assertEqual(self.motor.historial, [])

    def test_reflejo_distingue_tablero_vacio_de_deteccion_incompleta(self):
        self.motor = Seguimiento(reflejar_observaciones=True)
        self.estabilizar({"b4": "T"})
        for _ in range(4):
            self.enviar({}, completa=False)
        self.assertEqual(self.motor.posicion, tablero({"b4": "T"}))
        self.estabilizar({})
        self.assertEqual(self.motor.posicion, tablero({}))

    def test_reflejo_olvida_ultimo_movimiento_tras_redistribucion(self):
        self.motor = Seguimiento(reflejar_observaciones=True)
        self.estabilizar({"a1": "T"})
        self.estabilizar({"a3": "T"})
        self.assertIsNotNone(self.motor.ultimo_movimiento)
        self.estabilizar({"c5": "d", "f4": "C"})
        self.assertIsNone(self.motor.ultimo_movimiento)
        self.assertEqual(len(self.motor.historial), 1)

    def test_movimiento_se_confirma_una_vez(self):
        self.estabilizar({"a1": "T", "h8": "t"})
        movimiento = self.estabilizar({"a3": "T", "h8": "t"})
        self.assertEqual((movimiento.origen, movimiento.destino), ("a1", "a3"))
        self.estabilizar({"a3": "T", "h8": "t"})
        self.assertEqual(len(self.motor.historial), 1)

    def test_levantar_y_devolver_no_mueve(self):
        self.estabilizar({"a1": "T"})
        self.estabilizar({})
        self.assertEqual(self.motor.posicion, tablero({"a1": "T"}))
        self.estabilizar({"a1": "T"})
        self.assertEqual(self.motor.historial, [])

    def test_incompleta_y_confianza_baja_cortan_estabilidad(self):
        self.estabilizar({"a1": "T"})
        for completa, confianza in ((False, 1), (True, 0.2)):
            self.enviar({"a3": "T"})
            self.enviar({"a3": "T"}, completa, confianza)
            self.enviar({"a3": "T"})
            self.assertEqual(self.motor.posicion, tablero({"a1": "T"}))
            self.enviar({"a1": "T"})

    def test_no_confirma_relecturas_ni_secuencias_antiguas(self):
        obs = observacion(10, {"a1": "T"})
        for tiempo in (0, 0.3, 0.6, 1):
            self.motor.recibir(obs, tiempo)
        self.assertIsNone(self.motor.posicion)
        self.motor.recibir(observacion(9, {"a1": "T"}), 1.1)
        self.assertEqual(self.motor.muestras, 1)

    def test_desconexion_rompe_estabilidad_y_conserva_posicion(self):
        self.estabilizar({"a1": "T"})
        self.enviar({"a3": "T"})
        self.enviar({"a3": "T"}, intervalo=2)
        self.assertEqual(self.motor.posicion, tablero({"a1": "T"}))
        self.assertEqual(self.motor.muestras, 1)
        self.motor.comprobar_conexion(self.t + 2)
        self.assertIn("Sin datos", self.motor.estado)

    def test_fluctuacion_no_confirma(self):
        self.estabilizar({"a1": "T"})
        for _ in range(5):
            self.enviar({"a3": "T"})
            self.enviar({"b3": "T"})
        self.assertEqual(self.motor.historial, [])

    def test_captura(self):
        self.estabilizar({"a1": "T", "a3": "p"})
        movimiento = self.estabilizar({"a3": "T"})
        self.assertEqual((movimiento.tipo, movimiento.capturada), ("captura", "p"))

    def test_rechaza_captura_propia_y_cambios_multiples(self):
        self.estabilizar({"a1": "T", "b1": "C"})
        self.assertIsNone(self.estabilizar({"b1": "T"}))
        self.assertIsNone(self.estabilizar({"a3": "T", "b3": "C"}))
        self.assertEqual(self.motor.posicion, tablero({"a1": "T", "b1": "C"}))

    def test_promocion(self):
        movimiento = detectar_movimiento(tablero({"a7": "P"}), tablero({"a8": "D"}))
        self.assertEqual(movimiento.tipo, "promoción")
        self.assertIsNone(detectar_movimiento(tablero({"a6": "P"}), tablero({"a8": "D"})))

    def test_enroques(self):
        for fila, rey, torre in (("1", "R", "T"), ("8", "r", "t")):
            for inicio, fin_rey, fin_torre in (("h", "g", "f"), ("a", "c", "d")):
                movimiento = detectar_movimiento(
                    tablero({"e" + fila: rey, inicio + fila: torre}),
                    tablero({fin_rey + fila: rey, fin_torre + fila: torre}),
                )
                self.assertEqual(movimiento.tipo, "enroque")

    def test_captura_al_paso_requiere_avance_previo(self):
        self.estabilizar({"e5": "P", "d7": "p"})
        self.estabilizar({"e5": "P", "d5": "p"})
        movimiento = self.estabilizar({"d6": "P"})
        self.assertEqual(movimiento.tipo, "captura al paso")
        self.assertIsNone(detectar_movimiento(tablero({"e5": "P", "d5": "p"}), tablero({"d6": "P"})))

    def test_validacion(self):
        self.assertEqual(indices("a8"), (0, 0))
        self.assertEqual(indices("h1"), (7, 7))
        for datos in (
            {}, [], {"secuencia": True, "completa": True, "piezas": []},
            {"secuencia": 1, "completa": "true", "piezas": []},
            {"secuencia": 1, "completa": True, "piezas": [], "confianza": float("nan")},
            {"secuencia": 1, "completa": True, "piezas": [{"casilla": "a9", "pieza": "T"}]},
            {"secuencia": 1, "completa": True, "piezas": [{"casilla": "a1", "pieza": "TOWER"}]},
            {"secuencia": 1, "completa": True, "piezas": [{"casilla": "a1", "pieza": "T"}] * 2},
        ):
            with self.subTest(datos=datos), self.assertRaises(ValueError):
                Observacion.desde_dict(datos)

    def test_archivo_publicacion_y_error_sin_borrar_estado(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "observacion.json"
            datos = {"secuencia": 3, "completa": True, "piezas": [{"casilla": "a1", "pieza": "T"}]}
            publicar(ruta, datos)
            self.assertEqual(EntradaArchivo(ruta).leer().tablero, tablero({"a1": "T"}))
            ruta.write_text("{", encoding="utf-8")
            with self.assertRaises(ValueError):
                EntradaArchivo(ruta).leer()
            self.estabilizar({"a1": "T"})
            self.motor.invalidar("Error de entrada")
            self.assertEqual(self.motor.posicion, tablero({"a1": "T"}))

    def test_publicacion_reintenta_bloqueo_temporal_windows(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "observacion.json"
            datos = {"secuencia": 1, "completa": True, "piezas": []}
            reemplazar = os.replace
            intentos = []

            def bloqueado(origen, destino):
                intentos.append(1)
                if len(intentos) < 3:
                    raise PermissionError("Archivo abierto por el lector")
                reemplazar(origen, destino)

            with patch("entrada.os.replace", side_effect=bloqueado):
                publicar(ruta, datos)
            self.assertEqual(len(intentos), 3)
            self.assertEqual(EntradaArchivo(ruta).leer().secuencia, 1)
            self.assertEqual(len(list(Path(carpeta).iterdir())), 1)


if __name__ == "__main__":
    unittest.main()
