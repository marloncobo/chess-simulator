from pathlib import Path
from queue import Queue, Empty
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from captura_vivo import capturar, leer_ultimo, ultimo
from seguimiento import Seguimiento, SeguimientoPorCasilla, Observacion
from tiempo_real import guardar_calibracion, cargar_calibracion
from vision_vivo import FiltroEscena, construir_observacion, extraer

ESQUINAS = [(0, 0), (800, 0), (800, 800), (0, 800)]


def deteccion(pieza="T", x=150, y=250, conf=.9):
    return {"pieza": pieza, "punto": (x, y), "conf": conf}


class PruebasVivo(unittest.TestCase):
    def test_tipos_neutros_sin_color(self):
        ds = [deteccion(p, 50+i*100, 250) for i, p in enumerate("TCARDP")]
        obs, vista, puntos, razones = construir_observacion(ds, ESQUINAS, 1)
        self.assertTrue(obs.completa)
        self.assertEqual(razones, [])
        self.assertEqual(list(obs.tablero[2][:6]), ["?"+p for p in "TCARDP"])

    def test_bordes_colisiones_confianza_baja(self):
        for ds in ([deteccion(), deteccion(pieza="P", x=155)], [deteccion(conf=.3)]):
            obs, _, _, razones = construir_observacion(ds, ESQUINAS, 1)
            self.assertFalse(obs.completa)
            self.assertTrue(razones)

    def test_38_detecciones_reflejan_32_piezas_sin_bloqueo_global(self):
        ds = [deteccion("P" if f in (1,6) else "TCADRACT"[c], c*100+50, f*100+50, .55)
              for f in (0,1,6,7) for c in range(8)]
        ds += [{**d, "conf": .3} for d in ds[:6]]
        motor = SeguimientoPorCasilla()
        for i in range(5):
            obs, _, _, _ = construir_observacion(ds, ESQUINAS, i)
            motor.recibir(obs, i*.25)
        self.assertEqual(len(ds), 38)
        self.assertEqual(sum(bool(p) for f in motor.posicion for p in f), 32)
        self.assertEqual(len(motor.dudosas), 0)

    def test_solo_conserva_las_cuatro_torres_mas_fiables(self):
        ds = [deteccion("T",50+c*100,50,.95-c*.05) for c in range(6)]
        ds.append(deteccion("P",650,250,.9))
        obs, vista, _, razones = construir_observacion(list(reversed(ds)), ESQUINAS, 1)
        self.assertEqual(obs.tablero[0], ("?T", "?T", "?T", "?T", "", "", "", ""))
        self.assertEqual(obs.tablero[2][6], "?P")
        self.assertEqual(obs.desconocidas, frozenset({(0,4),(0,5)}))
        self.assertEqual(sum(p=="?T" for f in vista for p in f), 4)
        self.assertTrue(any("Límite de 4" in r for r in razones))

    def test_duplicados_y_torres_exteriores_no_consumen_plazas(self):
        ds = [deteccion("T",50+c*100,50,.9) for c in range(4)]
        ds += [deteccion("T",51,50,.7), deteccion("T",-50,50,.99)]
        obs, _, _, _ = construir_observacion(ds, ESQUINAS, 1)
        self.assertEqual(sum(p=="?T" for f in obs.tablero for p in f),4)
        self.assertTrue(obs.completa)

    def test_no_acumula_torres_retenidas_entre_fotogramas(self):
        motor = SeguimientoPorCasilla()
        for i in range(20):
            fila = 0 if i<5 else 1
            ds = [deteccion("T",50+c*100,fila*100+50,.9) for c in range(4)]
            if i>=5:
                ds += [deteccion("T",50+c*100,50,.6) for c in range(4)]
            obs, _, _, _ = construir_observacion(ds, ESQUINAS, i)
            motor.recibir(obs,i*.25)
            if motor.posicion is not None:
                self.assertLessEqual(sum(p=="?T" for f in motor.posicion for p in f),4)
        self.assertEqual(motor.posicion[1][:4], ("?T",)*4)
        self.assertFalse(any(motor.posicion[0]))

    def test_filtro_temporal_impone_limite_incluso_sin_filtro_previo(self):
        motor = SeguimientoPorCasilla()
        for i in range(5):
            datos = {"secuencia": i, "completa": True,
                     "piezas": [{"casilla": chr(97+c)+"8", "pieza":"?T"} for c in range(6)],
                     "confianzas": {chr(97+c)+"8": .6+c*.05 for c in range(6)}}
            motor.recibir(Observacion.desde_dict(datos),i*.25)
        self.assertEqual(motor.posicion[0], ("","","?T","?T","?T","?T","",""))

    def test_conflicto_persistente_solo_afecta_una_casilla(self):
        motor = SeguimientoPorCasilla()
        for i in range(5):
            ds = [deteccion("T", 50,50), deteccion("P",55,50), deteccion("A",150,50,.55)]
            obs, _, _, _ = construir_observacion(ds, ESQUINAS, i)
            motor.recibir(obs, i*.25)
        self.assertEqual(motor.posicion[0][0], "")
        self.assertEqual(motor.posicion[0][1], "?A")
        self.assertEqual(motor.dudosas, frozenset({(0,0)}))

    def test_fluctuacion_de_una_pieza_no_reinicia_el_resto(self):
        motor = SeguimientoPorCasilla()
        for i in range(5):
            ds = [deteccion("T" if i%2 else "P",50,50), deteccion("A",150,50)]
            obs, _, _, _ = construir_observacion(ds, ESQUINAS, i)
            motor.recibir(obs, i*.25)
        self.assertEqual(motor.posicion[0][0], "")
        self.assertEqual(motor.posicion[0][1], "?A")

    def test_incertidumbre_conserva_pieza_previa_sin_borrar(self):
        motor = SeguimientoPorCasilla()
        for i in range(5):
            obs, _, _, _ = construir_observacion([deteccion("T",50,50)], ESQUINAS, i)
            motor.recibir(obs, i*.25)
        for i in range(5,20):
            ds = [deteccion("T",50,50), deteccion("P",55,50), deteccion("A",150,50)]
            obs, _, _, _ = construir_observacion(ds, ESQUINAS, i)
            motor.recibir(obs, i*.25)
        self.assertEqual(motor.posicion[0][:2], ("?T", "?A"))

    def test_no_desplaza_colisiones_a_otras_casillas(self):
        ds = [deteccion("T", 110,210), deteccion("T",190,290)]
        obs, _, _, _ = construir_observacion(ds, ESQUINAS, 1)
        self.assertEqual(obs.desconocidas, frozenset({(2,1)}))
        self.assertFalse(any(p for f in obs.tablero for p in f))

    def test_movimiento_por_casilla_no_duplica_ni_pierde_historial(self):
        motor = SeguimientoPorCasilla()
        for i in range(5):
            obs, _, _, _ = construir_observacion([deteccion("T",50,50)], ESQUINAS, i)
            motor.recibir(obs, i*.25)
        for i in range(5,15):
            obs, _, _, _ = construir_observacion([deteccion("T",50,250)], ESQUINAS, i)
            motor.recibir(obs, i*.25)
            self.assertEqual(sum(bool(p) for f in motor.posicion for p in f), 1)
        self.assertEqual(len(motor.historial), 1)
        self.assertEqual((motor.historial[0].origen,motor.historial[0].destino), ("a8","a6"))

    def test_oclusion_general_y_relecturas_no_confirman(self):
        motor = SeguimientoPorCasilla()
        obs, _, _, _ = construir_observacion([deteccion()], ESQUINAS, 1)
        for t in (0,.25,.5,1):
            motor.recibir(obs,t)
        self.assertIsNone(motor.posicion)
        motor.invalidar("Movimiento")
        for i in range(2,6):
            motor.recibir(Observacion.desde_dict({"secuencia":i,"completa":False,"piezas":[]}), i*.25)
        self.assertIsNone(motor.posicion)

    def test_pieza_cerca_del_borde_no_descarta_toda_la_escena(self):
        obs, _, _, razones = construir_observacion([deteccion(x=101)], ESQUINAS, 1)
        self.assertTrue(obs.completa)
        self.assertEqual(razones, [])

    def test_fuera_del_tablero_no_inventa_casillas(self):
        obs, _, puntos, _ = construir_observacion([deteccion(x=-20)], ESQUINAS, 1)
        self.assertEqual(puntos, [])
        self.assertFalse(any(p for f in obs.tablero for p in f))

    def test_movimiento_neutro(self):
        motor = Seguimiento(reflejar_observaciones=True)
        for i in range(6):
            obs, _, _, _ = construir_observacion([deteccion(y=250 if i<3 else 450)], ESQUINAS, i)
            motor.recibir(obs, i*.3)
        self.assertEqual(motor.historial[-1].origen, "b6")
        self.assertEqual(motor.historial[-1].destino, "b4")

    def test_estabilidad_visual(self):
        filtro = FiltroEscena()
        frame = np.zeros((800, 800, 3), np.uint8)
        self.assertFalse(filtro.estable(frame, ESQUINAS))
        self.assertTrue(filtro.estable(frame, ESQUINAS))
        self.assertFalse(filtro.estable(frame+255, ESQUINAS))

    def test_base_mas_baja_que_centro(self):
        resultado = SimpleNamespace(masks=SimpleNamespace(xy=[np.array([[10,10],[40,10],[40,90],[10,90]])]),
                                    names={0:"TOWER"}, boxes=SimpleNamespace(cls=[0], conf=[.9]))
        frame = np.zeros((100, 100, 3), np.uint8)
        base, centro = extraer(resultado, frame, "base")[0], extraer(resultado, frame, "centro")[0]
        self.assertGreater(base["punto"][1], centro["punto"][1]+20)
        self.assertEqual(base["pieza"], "T")

    def test_calibracion_no_se_reutiliza_en_otra_resolucion(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta)/"calibracion.json"
            guardar_calibracion(ruta, 1, (800,800), ESQUINAS)
            self.assertEqual(len(cargar_calibracion(ruta,1,(800,800))), 4)
            with self.assertRaises(ValueError):
                cargar_calibracion(ruta,0,(800,800))
            with self.assertRaises(ValueError):
                cargar_calibracion(ruta,1,(1280,720))

    def test_solo_conserva_el_ultimo_fotograma(self):
        cola = Queue(1)
        ultimo(cola, 1)
        ultimo(cola, 2)
        self.assertEqual(leer_ultimo(cola), 2)
        self.assertIsNone(leer_ultimo(cola))

    def test_captura_abre_solo_source_uno_y_libera(self):
        class Cola(Queue):
            def cancel_join_thread(self): pass
        class Parar:
            stopped = False
            def is_set(self): return self.stopped
            def wait(self, tiempo): self.stopped = True
        class Camara:
            cerrada = False
            def isOpened(self): return False
            def release(self): self.cerrada = True
        camara, parar = Camara(), Parar()
        with patch("cv2.VideoCapture", return_value=camara) as abrir:
            capturar(1,"auto",Cola(1),parar)
            self.assertEqual(abrir.call_args.args[0], 1)
            self.assertEqual(abrir.call_count, 1)
        self.assertTrue(camara.cerrada)


if __name__ == "__main__":
    unittest.main()
