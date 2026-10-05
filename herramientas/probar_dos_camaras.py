"""Prueba dos cámaras locales o de red, con supervisión independiente."""
import argparse
import math
import multiprocessing as mp
import time
from pathlib import Path
from urllib.parse import urlsplit

import cv2
import numpy as np

from chess_simulator.captura_vivo import capturar, leer_ultimo


VENTANA = "Prueba de dos camaras | Q / Esc: salir | R: reconectar"
RECIENTE = 2.0


def fuente(valor):
    """Conserva índices como enteros y direcciones de vídeo como cadenas."""
    try:
        indice = int(valor)
    except ValueError:
        try:
            url = urlsplit(valor)
            valida = url.scheme.lower() in ("http", "https", "rtsp") and url.hostname
            url.port  # Valida también el puerto, si está presente.
        except ValueError:
            valida = False
        if valida:
            return valor
        raise argparse.ArgumentTypeError("Use un indice no negativo o una URL http(s)/rtsp valida")
    if indice < 0:
        raise argparse.ArgumentTypeError("El indice de camara no puede ser negativo")
    return indice


def argumentos(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", nargs=2, type=fuente, default=[0, 1],
                        metavar=("CAMARA_1", "CAMARA_2"), help="Indices o URLs (por defecto: 0 1)")
    backends = ("auto", "msmf", "dshow")
    parser.add_argument("--backend", choices=backends, default="auto",
                        help="Backend comun para camaras locales; las URLs usan auto")
    parser.add_argument("--ancho", type=int, default=640, help="Ancho solicitado a camaras locales")
    parser.add_argument("--alto", type=int, default=480)
    for numero in (1, 2):
        parser.add_argument(f"--backend-{numero}", choices=backends,
                            help=f"Backend especifico de la camara {numero}")
        parser.add_argument(f"--resolucion-{numero}", nargs=2, type=int, metavar=("ANCHO", "ALTO"),
                            help="Resolucion solicitada; en red se conserva la del emisor")
    parser.add_argument("--timeout", type=float, default=8,
                        help="Segundos sin cuadros antes de reiniciar la captura (minimo 2)")
    parser.add_argument("--max-desfase-ms", type=float, default=250,
                        help="Umbral de aviso entre tiempos de lectura en el PC")
    parser.add_argument("--detectar", action="store_true", help="Calibrar y combinar detecciones de piezas")
    from chess_simulator.rutas import MODELO
    parser.add_argument("--modelo", type=Path, default=MODELO)
    from chess_simulator.reglas_deteccion import CONFIANZA_DETECTOR, UMBRAL_DUDA
    parser.add_argument("--confianza", type=float, default=CONFIANZA_DETECTOR,
                        help=f"Filtro de YOLO (0.05 a 1, por defecto {CONFIANZA_DETECTOR}). Entre este valor "
                             f"y {UMBRAL_DUDA} la deteccion no afirma pieza: deja la casilla en duda")
    args = parser.parse_args(argv)
    if args.sources[0] == args.sources[1]:
        parser.error("Indique dos fuentes distintas")
    if args.ancho <= 0 or args.alto <= 0:
        parser.error("El ancho y el alto deben ser positivos")
    if not math.isfinite(args.timeout) or args.timeout < RECIENTE:
        parser.error("--timeout debe ser un numero finito mayor o igual a 2")
    if not math.isfinite(args.max_desfase_ms) or args.max_desfase_ms <= 0:
        parser.error("--max-desfase-ms debe ser un numero finito positivo")
    if not math.isfinite(args.confianza) or not .05 <= args.confianza <= 1:
        parser.error("--confianza debe estar entre 0.05 y 1")
    if args.detectar and not args.modelo.is_file():
        parser.error(f"No existe el modelo: {args.modelo}")
    args.configuraciones = []
    for i, source in enumerate(args.sources, 1):
        red = isinstance(source, str)
        especifico = getattr(args, f"backend_{i}")
        backend = especifico or ("auto" if red else args.backend)
        if red and backend != "auto":
            parser.error(f"La URL de la camara {i} necesita --backend-{i} auto")
        resolucion = getattr(args, f"resolucion_{i}") or [args.ancho, args.alto]
        if min(resolucion) <= 0:
            parser.error(f"Resolucion invalida para la camara {i}")
        args.configuraciones.append((source, backend, None if red else tuple(resolucion)))
    return args


def vigente(estado, ahora):
    return (estado.get("frame") is not None and not estado.get("error")
            and 0 <= ahora - estado["instante"] < RECIENTE)


def desfase_ms(estados, ahora):
    """Diferencia de lecturas locales, no de exposición ni latencia de red."""
    if not all(vigente(estado, ahora) for estado in estados):
        return None
    return abs(estados[0]["instante"] - estados[1]["instante"]) * 1000


class CamaraSupervisada:
    """Reinicia incluso si VideoCapture/read queda bloqueado en su proceso.

    Cada reinicio crea una cola nueva: una cola de un proceso terminado a la
    fuerza puede estar corrupta y nunca debe reutilizarse.
    """
    def __init__(self, ctx, source, backend, resolucion, timeout=8):
        self.ctx, self.source, self.backend = ctx, source, backend
        self.resolucion, self.timeout = resolucion, timeout
        self.proceso = self.cola = self.parar = None
        self.estado = {}
        self.muestra = None
        self.ultimo_frame = 0.
        self.reinicios = 0
        self.retirando = None

    def iniciar(self):
        self.parar = self.ctx.Event()
        self.cola = self.ctx.Queue(1)
        self.proceso = self.ctx.Process(target=capturar,
            args=(self.source, self.backend, self.cola, self.parar, self.resolucion), daemon=True)
        self.proceso.start()
        self.ultimo_frame = time.monotonic()
        self.muestra = None
        self.estado = {"error": "Conectando..."}
        self.retirando = None

    def reiniciar(self, ahora):
        if self.retirando is not None:
            return
        self.reinicios += 1
        self.estado = {"error": "Sin cuadros. Reiniciando conexion..."}
        self.parar.set()
        self.retirando = ahora

    def _liberar(self):
        self.proceso.join(timeout=0)
        self.proceso.close()
        self.cola.cancel_join_thread()
        self.cola.close()
        self.proceso = self.cola = self.parar = None

    def actualizar(self, ahora):
        if self.retirando is not None:
            if not self.proceso.is_alive():
                self._liberar()
                self.iniciar()
            elif ahora - self.retirando > 1:
                self.proceso.kill()
            elif ahora - self.retirando > .3:
                self.proceso.terminate()
            return
        paquete = leer_ultimo(self.cola)
        if paquete is not None:
            if "frame" in paquete:
                instante, secuencia = paquete["instante"], paquete["secuencia"]
                fps = self.estado.get("fps", 0.)
                if self.muestra is None:
                    self.muestra = (instante, secuencia)
                elif instante - self.muestra[0] >= 1:
                    fps = (secuencia - self.muestra[1]) / (instante - self.muestra[0])
                    self.muestra = (instante, secuencia)
                self.ultimo_frame = instante
                self.estado = {**paquete, "fps": fps}
            else:
                self.estado = {"error": "Sin conexion. Reintentando..."}
                self.muestra = None
        if not self.proceso.is_alive() or ahora - self.ultimo_frame >= self.timeout:
            self.reiniciar(ahora)

    def cerrar(self):
        if self.parar is not None:
            self.parar.set()
        if self.proceso is not None and self.proceso.pid is not None:
            self.proceso.join(timeout=.3)
            if self.proceso.is_alive():
                self.proceso.terminate()
                self.proceso.join(timeout=1)
            if self.proceso.is_alive():
                self.proceso.kill()
                self.proceso.join(timeout=1)
            self._liberar()
        elif self.cola is not None:
            self.cola.cancel_join_thread()
            self.cola.close()


def texto(imagen, valor, xy, escala=.55, color=(235, 235, 235)):
    cv2.putText(imagen, valor, xy, cv2.FONT_HERSHEY_SIMPLEX, escala, color, 1, cv2.LINE_AA)


def panel(estado, numero, source, ahora, reinicios=0):
    lienzo = np.zeros((480, 640, 3), dtype=np.uint8)
    frame = estado.get("frame")
    activo = vigente(estado, ahora)
    if frame is not None:
        alto, ancho = frame.shape[:2]
        escala = min(640 / ancho, 360 / alto)
        w, h = max(1, round(ancho * escala)), max(1, round(alto * escala))
        reducido = cv2.resize(frame, (w, h), interpolation=cv2.INTER_AREA)
        if not activo:
            reducido = (reducido * .3).astype(np.uint8)
        x, y = (640 - w) // 2, 120 + (360 - h) // 2
        lienzo[y:y + h, x:x + w] = reducido
    color = (100, 230, 100) if activo else (0, 190, 255)
    origen = f"indice {source}" if isinstance(source, int) else f"red: {urlsplit(source).hostname}"
    texto(lienzo, f"Camara {numero} | {origen}"[:65], (12, 26), .65, color)
    if activo:
        detalle = f'{frame.shape[1]}x{frame.shape[0]} | {estado.get("fps", 0):.1f} FPS de lectura'
    else:
        detalle = estado.get("error") or "IMAGEN ANTIGUA - no usar para detectar"
    texto(lienzo, detalle, (12, 55), color=color)
    edad = max(0., ahora - estado["instante"]) if frame is not None else None
    lectura = f"Ultima lectura: hace {edad:.2f} s" if edad is not None else "Esperando imagen"
    texto(lienzo, f"{lectura} | Reinicios: {reinicios}", (12, 84), color=color)
    if frame is not None and not activo:
        texto(lienzo, "SIN VIDEO RECIENTE", (150, 300), .9, color)
    return lienzo


def main(argv=None):
    args = argumentos(argv)
    if args.detectar:
        from herramientas.deteccion_doble import ejecutar
        return ejecutar(args)
    ctx = mp.get_context("spawn")
    camaras = [CamaraSupervisada(ctx, *config, timeout=args.timeout)
               for config in args.configuraciones]
    print("Abriendo dos fuentes independientes. Q / Esc: salir. R: reconectar ambas.")
    print("Para el iPhone, inicie puente_iphone.py y abra su pagina HTTPS en Safari.")
    print("El desfase compara lecturas en el PC; no mide sincronizacion real ni retraso de red.")
    try:
        for camara in camaras:
            camara.iniciar()
        cv2.namedWindow(VENTANA, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(VENTANA, 1280, 550)
        while True:
            ahora = time.monotonic()
            for camara in camaras:
                camara.actualizar(ahora)
            ahora = time.monotonic()
            estados = [camara.estado for camara in camaras]
            vista = np.hstack([panel(c.estado, i + 1, c.source, ahora, c.reinicios)
                               for i, c in enumerate(camaras)])
            pie = np.zeros((70, 1280, 3), np.uint8)
            diferencia = desfase_ms(estados, ahora)
            if diferencia is None:
                mensaje, color = "Desfase no disponible: faltan dos imagenes recientes", (0, 190, 255)
            else:
                aviso = "ALTO" if diferencia > args.max_desfase_ms else "dentro del umbral"
                mensaje = f"Desfase entre lecturas: {diferencia:.0f} ms | {aviso} ({args.max_desfase_ms:.0f} ms)"
                color = (0, 190, 255) if diferencia > args.max_desfase_ms else (100, 230, 100)
            texto(pie, mensaje, (12, 25), color=color)
            texto(pie, "No mide el retraso real del iPhone. Q/Esc: salir | R: reconectar | Prueba de video sin deteccion", (12, 55))
            cv2.imshow(VENTANA, np.vstack([vista, pie]))
            tecla = cv2.waitKey(15) & 0xFF
            if tecla in (27, ord("q"), ord("Q")):
                break
            if tecla in (ord("r"), ord("R")):
                for camara in camaras:
                    camara.reiniciar(time.monotonic())
            if cv2.getWindowProperty(VENTANA, cv2.WND_PROP_VISIBLE) < 1:
                break
    except KeyboardInterrupt:
        pass
    finally:
        for camara in camaras:
            camara.cerrar()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    mp.freeze_support()
    main()
