"""Experimento interactivo sobre una foto o un único fotograma."""
import argparse
import csv
import math
import multiprocessing as mp
from pathlib import Path
from queue import Empty

import cv2
import numpy as np

from chess_simulator.captura_vivo import capturar
from chess_simulator.regla_de_tres import calibrar, centimetros_a_metros

VENTANA = "Regla de tres"
ORDEN = ("a8", "h8", "h1", "a1")


def fotograma(source):
    ctx = mp.get_context("spawn")
    cola, parar = ctx.Queue(1), ctx.Event()
    proceso = ctx.Process(target=capturar, args=(source, "auto", cola, parar), daemon=True)
    proceso.start()
    try:
        try:
            muestra = cola.get(timeout=15)
        except Empty:
            raise ValueError("La cámara no entregó una imagen en 15 segundos.") from None
        if "error" in muestra:
            raise ValueError(muestra["error"].split(";")[0])
        return muestra["frame"]
    finally:
        parar.set()
        proceso.join(1)
        if proceso.is_alive():
            proceso.terminate()
            proceso.join()
        cola.close()


def validar(pixel, estimada, errores, salida):
    try:
        real = tuple(map(float, input("X Y medidos en cm (separados por espacio): ").split()))
        if len(real) != 2 or not all(map(math.isfinite, real)):
            raise ValueError
    except (ValueError, EOFError):
        print("Medición descartada. Introduzca dos números finitos.")
        return
    error = math.dist(estimada, real)
    if salida:
        with salida.open("a", newline="", encoding="utf-8") as archivo:
            tabla = csv.writer(archivo)
            if archivo.tell() == 0:
                tabla.writerow(("x_px","y_px","x_est_cm","y_est_cm","x_real_cm","y_real_cm","error_cm"))
            tabla.writerow((*pixel, *estimada, *real, error))
    errores.append(error)
    for nombre, valor in (("Error", error), ("Media", sum(errores)/len(errores)), ("Máximo", max(errores))):
        print(f"{nombre}: {valor:.3f} cm ({valor*10:.2f} mm)")


def explorar(imagen, ancho, alto, salida):
    h, w = imagen.shape[:2]
    print(f"Resolución: {w} × {h} px. Seleccione el área jugable: a8, h8, h1, a1.")
    esquinas, errores = [], []
    escala = pixel = None
    etiqueta = ""
    vista = imagen.copy()

    def dibujar():
        nonlocal vista
        vista = imagen.copy()
        for i, punto in enumerate(esquinas):
            cv2.circle(vista, punto, 5, (0,255,255), -1)
            cv2.line(vista, esquinas[max(0,i-1)], punto, (0,255,255), 2)
        if escala:
            cv2.line(vista, esquinas[-1], esquinas[0], (0,255,255), 2)
        if pixel:
            cv2.circle(vista, pixel, 6, (255,0,255), -1)
        texto = etiqueta or (f"Seleccione {ORDEN[len(esquinas)]}" if not escala else "Seleccione un punto")
        cv2.putText(vista, texto, (8,26), cv2.FONT_HERSHEY_SIMPLEX, .6, (0,0,0), 4)
        cv2.putText(vista, texto, (8,26), cv2.FONT_HERSHEY_SIMPLEX, .6, (255,255,255), 1)

    def clic(evento, x, y, flags, param):
        nonlocal escala, pixel, etiqueta
        if evento != cv2.EVENT_LBUTTONDOWN:
            return
        if escala is None:
            esquinas.append((x,y))
            if len(esquinas) == 4:
                try:
                    escala = calibrar(esquinas, ancho, alto)
                except ValueError as exc:
                    print(exc)
                    esquinas.clear()
                else:
                    print(f"Área: {ancho} × {alto} cm. Lados superior, inferior, izquierdo, derecho (px): {escala.lados}")
                    for eje, directa, inversa in zip("XY", escala.px_por_cm, escala.cm_por_px):
                        print(f"Escala {eje}: {directa:.4f} px/cm, {inversa:.6f} cm/px")
        else:
            pixel = (x,y)
            cx, cy = escala.pixeles_a_cm(x,y)
            mx, my = centimetros_a_metros(cx,cy)
            dentro = cv2.pointPolygonTest(np.array(esquinas, dtype=np.int32), pixel, False) >= 0
            casilla = escala.casilla(cx,cy) if dentro else None
            etiqueta = f"({x},{y}) px  ({cx:.2f},{cy:.2f}) cm  {casilla or 'sin casilla'}"
            print(f"{etiqueta}  ({mx:.4f},{my:.4f}) m")
            if casilla:
                print(f"Centro de {casilla} en cm: {escala.centro_cm(casilla)}")
        dibujar()

    cv2.namedWindow(VENTANA, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(VENTANA, min(w, 1000), max(1, int(h * min(w,1000)/w)))
    cv2.setMouseCallback(VENTANA, clic)
    dibujar()
    print("V registra una referencia en la terminal. R reinicia. Esc sale.")
    try:
        while True:
            cv2.imshow(VENTANA, vista)
            tecla = cv2.waitKey(30) & 255
            if tecla == 27 or cv2.getWindowProperty(VENTANA, cv2.WND_PROP_VISIBLE) < 1:
                break
            if tecla in (ord("v"), ord("V")) and pixel:
                validar(pixel, escala.pixeles_a_cm(*pixel), errores, salida)
            if tecla in (ord("r"), ord("R")):
                esquinas.clear()
                errores.clear()
                escala = pixel = None
                etiqueta = ""
                dibujar()
    finally:
        cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    fuente = parser.add_mutually_exclusive_group(required=True)
    fuente.add_argument("--imagen", type=Path)
    fuente.add_argument("--source", help="Índice de cámara o URL de vídeo")
    parser.add_argument("--ancho-cm", type=float, default=40)
    parser.add_argument("--alto-cm", type=float, default=40)
    parser.add_argument("--salida", type=Path, help="Añadir referencias medidas a este CSV")
    args = parser.parse_args()
    if not all(math.isfinite(v) and v > 0 for v in (args.ancho_cm,args.alto_cm)):
        parser.error("Las dimensiones deben ser positivas y finitas.")
    try:
        if args.imagen:
            imagen = cv2.imread(str(args.imagen))
            if imagen is None:
                raise ValueError(f"No se pudo leer {args.imagen}")
        else:
            imagen = fotograma(int(args.source) if args.source.isdecimal() else args.source)
        explorar(imagen, args.ancho_cm, args.alto_cm, args.salida)
    except (ValueError, OSError, cv2.error) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
