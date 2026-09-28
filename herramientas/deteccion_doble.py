"""Interfaz de calibración, detección y tablero compartido de dos cámaras."""
import hashlib
import json
import multiprocessing as mp
import time
import unicodedata

import cv2
import numpy as np

from herramientas.probar_dos_camaras import CamaraSupervisada, panel, texto, vigente
from chess_simulator.captura_vivo import ultimo, leer_ultimo
from chess_simulator.detector_doble import inferir_par
from chess_simulator.fusion_camaras import observar_vista, fusionar, par_valido
from chess_simulator.rutas import CONFIG
from chess_simulator.seguimiento import SeguimientoPorCasilla, nombre
from chess_simulator.vision_vivo import FiltroEscena, homografia


VENTANA = "Dos camaras - deteccion y tablero compartido"
VERTICES = ("a8", "h8", "h1", "a1")


def ruta_calibracion(source):
    identidad = hashlib.sha256(str(source).encode()).hexdigest()[:16]
    return CONFIG / f"calibracion_doble_{identidad}.json"


def guardar(source, resolucion, esquinas):
    homografia(esquinas)
    ruta = ruta_calibracion(source)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps({"resolucion": list(resolucion), "esquinas": esquinas}), encoding="utf-8")


def cargar(source, resolucion):
    datos = json.loads(ruta_calibracion(source).read_text(encoding="utf-8"))
    if datos["resolucion"] != list(resolucion):
        raise ValueError("La resolucion cambio; calibre nuevamente")
    homografia(datos["esquinas"])
    return datos["esquinas"]


def punto_original(x, y, indice, forma):
    """Invierte exactamente el encuadre con bandas usado por panel()."""
    alto, ancho = forma[:2]
    escala = min(640 / ancho, 360 / alto)
    w, h = max(1, round(ancho * escala)), max(1, round(alto * escala))
    izq, arriba = indice*640 + (640-w)//2, 120 + (360-h)//2
    if not (izq <= x < izq+w and arriba <= y < arriba+h):
        return None
    return ((x-izq)*ancho/w, (y-arriba)*alto/h)


class SesionDoble:
    def __init__(self, camaras, args):
        self.camaras, self.args = camaras, args
        self.esquinas = [[], []]
        self.resoluciones = [None, None]
        self.generaciones = [c.reinicios for c in camaras]
        self.filtros = [FiltroEscena(), FiltroEscena()]
        self.seguimiento = SeguimientoPorCasilla(espera_vacio=2.)
        self.revision = self.secuencia = 0
        self.seleccion = None
        self.congelada = None
        self.ultimas = [None, None]
        self.procedencias = {}
        self.observacion = None
        self.mensaje = "Pulse 1 y calibre la camara 1; despues pulse 2 para la camara 2"
        self.movimiento = "Sin movimientos confirmados"
        self.inferencia = 0.

    def invalidar(self):
        self.revision += 1
        self.ultimas = [None, None]
        self.procedencias = {}
        self.filtros = [FiltroEscena(), FiltroEscena()]
        self.seguimiento.invalidar("Esperando nuevas vistas estables")

    def comprobar_camaras(self):
        for i, camara in enumerate(self.camaras):
            frame = camara.estado.get("frame")
            resolucion = (frame.shape[1], frame.shape[0]) if frame is not None else self.resoluciones[i]
            if camara.reinicios != self.generaciones[i] or resolucion != self.resoluciones[i]:
                self.generaciones[i] = camara.reinicios
                self.resoluciones[i] = resolucion
                self.esquinas[i] = []
                if self.seleccion == i:
                    self.seleccion = self.congelada = None
                self.invalidar()
                self.mensaje = "Calibre con 1/2 o pulse L si las camaras no cambiaron de posicion"

    def comenzar_calibracion(self, indice):
        if not vigente(self.camaras[indice].estado, time.monotonic()):
            self.mensaje = "No hay imagen reciente en esa camara"
            return
        self.seleccion = indice
        self.congelada = self.camaras[indice].estado["frame"].copy()
        self.esquinas[indice] = []
        self.invalidar()
        self.mensaje = f"Camara {indice+1}: haga clic en el vertice exterior a8"

    def clic(self, evento, x, y, flags, parametro):
        if evento != cv2.EVENT_LBUTTONDOWN or self.seleccion is None:
            return
        i = self.seleccion
        punto = punto_original(x, y, i, self.congelada.shape)
        if punto is None:
            return
        self.esquinas[i].append(punto)
        n = len(self.esquinas[i])
        if n < 4:
            self.mensaje = f"Camara {i+1}: haga clic en el vertice exterior {VERTICES[n]}"
            return
        try:
            homografia(self.esquinas[i])
        except ValueError:
            self.esquinas[i] = []
            self.mensaje = "Vertices invalidos; repita desde a8, h8, h1, a1"
            return
        self.seleccion = self.congelada = None
        self.invalidar()
        try:
            guardar(self.camaras[i].source, self.resoluciones[i], self.esquinas[i])
            self.mensaje = f"Camara {i+1} calibrada y guardada"
        except OSError:
            self.mensaje = f"Camara {i+1} calibrada; no se pudo guardar en disco"

    def cargar(self):
        try:
            esquinas = [cargar(c.source, r) for c, r in zip(self.camaras, self.resoluciones)]
        except (OSError, ValueError, KeyError, TypeError):
            self.mensaje = "No se pudo cargar ambas calibraciones; marque con 1 y 2"
            return
        self.esquinas = esquinas
        self.seleccion = self.congelada = None
        self.invalidar()
        self.mensaje = "Calibraciones cargadas; esperando vistas estables"

    def recibir(self, resultado, ahora):
        if resultado["revision"] != self.revision or self.seleccion is not None:
            return False
        vistas = resultado["vistas"]
        actuales = [c.estado for c in self.camaras]
        if not par_valido(vistas, ahora, self.args.max_desfase_ms/1000) or not all(vigente(p, ahora) for p in actuales):
            self.procedencias = {}
            self.seguimiento.invalidar("Resultados antiguos; posicion conservada")
            self.mensaje = "Resultado antiguo descartado; espere imagenes recientes"
            return False
        self.ultimas = vistas
        self.inferencia = resultado["inferencia"]
        quietas = [f.estable(v["frame"], e) for f, v, e in zip(self.filtros, vistas, self.esquinas)]
        if not all(quietas):
            self.procedencias = {}
            self.seguimiento.invalidar("Movimiento; esperando estabilidad", conservar_movimiento=True, ahora=ahora)
            self.mensaje = "Movimiento o cambio visual: esperando estabilidad en ambas vistas"
            return False
        self.secuencia += 1
        observaciones = [observar_vista(v["detecciones"], e, self.secuencia)
                         for v, e in zip(vistas, self.esquinas)]
        self.observacion, self.procedencias = fusionar(observaciones, self.secuencia)
        movimiento = self.seguimiento.recibir(self.observacion, ahora)
        if movimiento:
            self.movimiento = movimiento.texto()
            print(self.movimiento, flush=True)
        self.mensaje = self.seguimiento.estado
        return True

    def dibujar(self, ahora):
        paneles = []
        for i, camara in enumerate(self.camaras):
            estado = camara.estado
            resultado = self.ultimas[i]
            if resultado and vigente(resultado, ahora) and vigente(estado, ahora):
                estado = {**resultado, "fps": camara.estado.get("fps", 0)}
            if self.seleccion == i:
                estado = {"frame": self.congelada, "instante": ahora}
                resultado = None
            frame = estado.get("frame")
            if frame is not None:
                imagen = frame.copy()
                if resultado and vigente(resultado, ahora):
                    for d in resultado["detecciones"]:
                        color = {"BLANCA": (80, 230, 80), "NEGRA": (255, 170, 50)}.get(d["color"], (0, 190, 255))
                        cv2.polylines(imagen, [d["poligono"]], True, color, 2)
                        x, y = map(int, d["punto"])
                        cv2.circle(imagen, (x, y), 4, color, -1)
                        texto(imagen, f'{d["pieza"]} {d["color"]} {d["conf"]:.2f}', (x, max(15, y-10)), color=color)
                for n, p in enumerate(self.esquinas[i]):
                    xy = tuple(map(int, p))
                    cv2.circle(imagen, xy, 5, (100, 255, 100), -1)
                    texto(imagen, VERTICES[n], xy, color=(100, 255, 100))
                if len(self.esquinas[i]) == 4:
                    inversa = np.linalg.inv(homografia(self.esquinas[i]))
                    for n in range(9):
                        for extremos in ([[n, 0], [n, 8]], [[0, n], [8, n]]):
                            pts = cv2.perspectiveTransform(np.float32(extremos).reshape(-1, 1, 2), inversa)
                            cv2.line(imagen, tuple(np.rint(pts[0, 0]).astype(int)),
                                     tuple(np.rint(pts[1, 0]).astype(int)), (70, 160, 140), 1)
                estado = {**estado, "frame": imagen}
            vista = panel(estado, i+1, camara.source, ahora, camara.reinicios)
            texto(vista, "CALIBRANDO (imagen fija)" if self.seleccion == i else
                  ("Calibrada" if len(self.esquinas[i]) == 4 else f"Pulse {i+1} para calibrar"), (12, 110))
            paneles.append(vista)
        abajo = np.full((450, 1280, 3), 25, np.uint8)
        posicion = self.seguimiento.posicion
        for f in range(8):
            for c in range(8):
                x, y = 30+c*48, 25+f*48
                color = (180, 210, 235) if (f+c)%2 == 0 else (90, 130, 160)
                cv2.rectangle(abajo, (x, y), (x+47, y+47), color, -1)
                pieza = posicion[f][c] if posicion else ""
                if pieza:
                    cv2.circle(abajo, (x+24, y+23), 17, (240, 240, 240) if pieza.isupper() else (30, 30, 30), -1)
                    texto(abajo, pieza.upper(), (x+15, y+30), .7,
                          (20, 20, 20) if pieza.isupper() else (245, 245, 245))
                if (f, c) in self.seguimiento.dudosas:
                    cv2.rectangle(abajo, (x+1, y+1), (x+46, y+46), (0, 140, 255), 3)
                if self.observacion and pieza and pieza == self.observacion.tablero[f][c]:
                    origen = self.procedencias.get(nombre(f, c), "")
                    texto(abajo, origen, (x+2, y+45), .3, (70, 40, 20))
        for n in range(8):
            texto(abajo, str(8-n), (8, 56+n*48))
            texto(abajo, "abcdefgh"[n], (48+n*48, 430))
        lineas = ["TABLERO COMBINADO - piezas confirmadas",
                  "1 / 2: calibrar cada camara (imagen fija)",
                  "Clics: a8 > h8 > h1 > a1, mismas esquinas fisicas",
                  "L: cargar calibraciones SOLO si no movio las camaras",
                  "R: reconectar | S: nueva posicion | Q/Esc: salir",
                  "T torre | C caballo | A alfil | D dama | R rey | P peon",
                  "Borde naranja: duda; conserva el estado anterior",
                  "Origen 1, 2 o 1+2 debajo de la pieza",
                  f"Inferencia de ambas vistas: {self.inferencia*1000:.0f} ms",
                  self.mensaje[:98], self.movimiento[:98],
                  "La coincidencia de lecturas no garantiza sincronizacion real"]
        for n, linea in enumerate(lineas):
            # OpenCV no incluye glifos acentuados en esta fuente.
            linea = unicodedata.normalize("NFKD", linea).encode("ascii", "ignore").decode()
            texto(abajo, linea, (445, 28+n*35), .5)
        return np.vstack([np.hstack(paneles), abajo])


def ejecutar(args):
    ctx = mp.get_context("spawn")
    camaras = [CamaraSupervisada(ctx, *config, timeout=args.timeout) for config in args.configuraciones]
    sesion = SesionDoble(camaras, args)
    entrada, salida, parar = ctx.Queue(1), ctx.Queue(1), ctx.Event()
    proceso = ctx.Process(target=inferir_par, args=(args.modelo, entrada, salida, parar, args.confianza), daemon=True)
    listo, ocupado, enviado, desde = False, False, None, time.monotonic()
    fallo = None
    try:
        for camara in camaras:
            camara.iniciar()
        proceso.start()
        cv2.namedWindow(VENTANA, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(VENTANA, 1152, 837)
        cv2.setMouseCallback(VENTANA, sesion.clic)
        while True:
            ahora = time.monotonic()
            for camara in camaras:
                camara.actualizar(ahora)
            sesion.comprobar_camaras()
            resultado = leer_ultimo(salida)
            if resultado:
                if "error" in resultado:
                    fallo = resultado["error"]
                elif "listo" in resultado:
                    listo = True
                else:
                    ocupado = False
                    sesion.recibir(resultado, time.monotonic())
            if not proceso.is_alive() and fallo is None:
                fallo = "Detector detenido. Cierre y vuelva a iniciar la prueba."
            if ocupado and ahora-desde > 45:
                fallo = "Detector sin respuesta. Cierre y vuelva a iniciar la prueba."
            paquetes = [c.estado for c in camaras]
            habilitado = (sesion.seleccion is None and all(len(e) == 4 for e in sesion.esquinas))
            valido = par_valido(paquetes, time.monotonic(), args.max_desfase_ms/1000)
            firma = (sesion.revision, tuple(p.get("instante") for p in paquetes))
            nuevos = enviado is None or firma[0] != enviado[0] or all(a != b for a, b in zip(firma[1], enviado[1]))
            if listo and not fallo and not ocupado and habilitado and valido and nuevos:
                ultimo(entrada, {"revision": sesion.revision, "paquetes": paquetes})
                enviado, ocupado, desde = firma, True, ahora
            if fallo:
                sesion.mensaje = fallo
                sesion.procedencias = {}
                sesion.seguimiento.invalidar(fallo)
            elif not listo and sesion.seleccion is None:
                sesion.mensaje = "Cargando modelo; puede calibrar con 1 y 2"
            elif habilitado and not valido:
                sesion.mensaje = "Faltan dos imagenes recientes o el desfase supera el umbral"
                sesion.seguimiento.invalidar(sesion.mensaje)
                sesion.procedencias = {}
            sesion.seguimiento.comprobar_conexion(ahora)
            cv2.imshow(VENTANA, sesion.dibujar(time.monotonic()))
            tecla = cv2.waitKey(15) & 0xFF
            if tecla in (27, ord("q"), ord("Q")):
                break
            if tecla in (ord("1"), ord("2")):
                sesion.comenzar_calibracion(tecla-ord("1"))
            elif tecla in (ord("l"), ord("L")):
                sesion.cargar()
            elif tecla in (ord("r"), ord("R")):
                for camara in camaras:
                    camara.reiniciar(time.monotonic())
            elif tecla in (ord("s"), ord("S")):
                sesion.seguimiento = SeguimientoPorCasilla(espera_vacio=2.)
                sesion.movimiento = "Sin movimientos confirmados"
                sesion.invalidar()
            if cv2.getWindowProperty(VENTANA, cv2.WND_PROP_VISIBLE) < 1:
                break
    except KeyboardInterrupt:
        pass
    finally:
        parar.set()
        for camara in camaras:
            camara.cerrar()
        if proceso.pid is not None:
            proceso.join(timeout=.5)
            if proceso.is_alive():
                proceso.terminate()
                proceso.join(timeout=2)
            if proceso.is_alive():
                proceso.kill()
                proceso.join(timeout=2)
            proceso.close()
        for cola in (entrada, salida):
            cola.cancel_join_thread()
            cola.close()
        cv2.destroyAllWindows()
