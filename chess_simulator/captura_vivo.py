"""Captura e inferencia en procesos separados, con colas de último fotograma."""
import multiprocessing as mp
from queue import Empty, Full
import time


def ultimo(cola, valor):
    try:
        cola.put_nowait(valor)
        return
    except Full:
        pass
    try:
        cola.get_nowait()
    except Empty:
        pass
    try:
        cola.put_nowait(valor)
    except Full:
        pass


def leer_ultimo(cola):
    valor = None
    while True:
        try:
            valor = cola.get_nowait()
        except Empty:
            return valor


def capturar(source, backend, salida, parar, resolucion=None):
    import cv2
    salida.cancel_join_thread()
    api = {"auto": cv2.CAP_ANY, "msmf": cv2.CAP_MSMF, "dshow": cv2.CAP_DSHOW}[backend]
    secuencia = 0
    while not parar.is_set():
        cap = cv2.VideoCapture(source, api)
        try:
            if not cap.isOpened():
                ultimo(salida, {"error": f"No se pudo abrir source={source}. Acepte la notificación; reintentando."})
                parar.wait(2)
                continue
            if resolucion is not None:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, resolucion[0])
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, resolucion[1])
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            while not parar.is_set():
                ok, frame = cap.read()
                if not ok or frame is None or not frame.size:
                    ultimo(salida, {"error": "Cámara desconectada; reintentando la misma fuente"})
                    break
                secuencia += 1
                ultimo(salida, {"frame": frame, "secuencia": secuencia, "instante": time.monotonic()})
        finally:
            cap.release()
        parar.wait(1)


def inferir(modelo, punto, entrada, salida, parar, confianza=.25, parametros_hsv=None):
    salida.cancel_join_thread()
    try:
        from ultralytics import YOLO
        from chess_simulator.vision_vivo import extraer
        red = YOLO(modelo)
        while not parar.is_set():
            try:
                paquete = entrada.get(timeout=.2)
            except Empty:
                continue
            reciente = leer_ultimo(entrada)
            if reciente is not None:
                paquete = reciente
            frame = paquete["frame"]
            inicio = time.monotonic()
            # Un tablero tiene como máximo 32 piezas; 64 deja margen sin
            # descartar detecciones por una cota artificialmente pequeña.
            resultado = red(frame, conf=confianza, max_det=64, verbose=False)[0]
            detecciones = extraer(resultado, frame, punto, parametros_hsv)
            ultimo(salida, {**paquete, "detecciones": detecciones, "inferencia": time.monotonic()-inicio})
    except Exception as error:
        ultimo(salida, {"error": f"Error de inferencia: {error}"})


class FlujoVivo:
    def __init__(self, modelo, source=1, backend="auto", punto="base", confianza=.25, resolucion=None, parametros_hsv=None):
        self.ctx = mp.get_context("spawn")
        self.parar = self.ctx.Event()
        self.frames = self.ctx.Queue(1)
        self.pendientes = self.ctx.Queue(1)
        self.resultados = self.ctx.Queue(1)
        self.procesos = [
            self.ctx.Process(target=capturar, args=(source, backend, self.frames, self.parar, resolucion), daemon=True),
            self.ctx.Process(target=inferir, args=(str(modelo), punto, self.pendientes, self.resultados, self.parar, confianza, parametros_hsv), daemon=True),
        ]

    def iniciar(self):
        for proceso in self.procesos:
            proceso.start()

    def cerrar(self):
        self.parar.set()
        for proceso in self.procesos:
            if proceso.pid:
                proceso.join(timeout=1)
                if proceso.is_alive():
                    proceso.terminate()
                    proceso.join(timeout=2)
        for cola in (self.frames, self.pendientes, self.resultados):
            cola.cancel_join_thread()
            cola.close()
