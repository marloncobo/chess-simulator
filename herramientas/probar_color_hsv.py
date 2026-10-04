"""Prueba visual de color por pieza, con cámara y umbrales HSV ajustables."""
import argparse
from pathlib import Path
import time

import cv2
import numpy as np

from chess_simulator.rutas import MODELO
from chess_simulator.captura_vivo import FlujoVivo, leer_ultimo, ultimo


VENTANA = "Prueba HSV - piezas claras y negras"
CONTROLES = {"V negra max": 85, "V blanca min": 125, "S blanca max": 110,
             "Erosion px": 3}
COLORES = {"BLANCA": (80, 230, 80), "NEGRA": (255, 170, 50),
           "DUDOSA": (0, 180, 255)}


from chess_simulator.color_hsv import clasificar


def dibujar(frame, detecciones, parametros, modo="original"):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    fuentes = [frame] if modo == "original" else [cv2.cvtColor(hsv[:, :, 2], cv2.COLOR_GRAY2BGR)]
    if modo == "comparacion":
        fuentes.insert(0, frame)
    ancho = 1280 // len(fuentes)
    alto = max(1, round(frame.shape[0] * ancho / frame.shape[1]))
    escala = ancho / frame.shape[1]
    paneles = [cv2.resize(p, (ancho, alto), interpolation=
               cv2.INTER_AREA if escala < 1 else cv2.INTER_CUBIC) for p in fuentes]
    resultados = []
    for d in detecciones:
        medida = clasificar(hsv, d["poligono"], **parametros)
        resultados.append({"pieza": d["pieza"], **medida})
        color = COLORES[medida["color"]]
        poligono = np.rint(np.asarray(d["poligono"]) * escala).astype(np.int32)
        x, y, _, _ = cv2.boundingRect(poligono)
        etiqueta = f'{d["pieza"]} {medida["color"]}'
        if medida["v"] is not None:
            etiqueta += f' S:{medida["s"]:.0f} V:{medida["v"]:.0f}'
        (tw, th), base = cv2.getTextSize(etiqueta, cv2.FONT_HERSHEY_SIMPLEX, .65, 2)
        tx = max(4, min(x, ancho - tw - 8))
        ty = max(th + 8, min(y - 10, alto - base - 5))
        for panel in paneles:
            cv2.polylines(panel, [poligono], True, color, 2, cv2.LINE_AA)
            cv2.rectangle(panel, (tx - 4, ty - th - 5),
                          (tx + tw + 4, ty + base + 3), (20, 20, 20), -1)
            cv2.putText(panel, etiqueta, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX,
                        .65, color, 2, cv2.LINE_AA)
    cabecera = np.zeros((95, 1280, 3), np.uint8)
    for i, texto in enumerate((f'Vista: {modo} | Camara/imagen: {frame.shape[1]} x {frame.shape[0]} px',
                               "Verde: BLANCA | Azul: NEGRA | Naranja: DUDOSA",
                               "V: cambiar vista | Espacio: pausa | R: restablecer | Esc/Q: salir")):
        cv2.putText(cabecera, texto, (12, 24 + i * 29),
                    cv2.FONT_HERSHEY_SIMPLEX, .65, (240, 240, 240), 1, cv2.LINE_AA)
    pie = np.zeros((40, 1280, 3), np.uint8)
    return np.vstack([cabecera, np.hstack(paneles), pie]), resultados


def controles():
    valores = {k: cv2.getTrackbarPos(k, VENTANA) for k in CONTROLES}
    return dict(negra_max=valores["V negra max"], blanca_min=valores["V blanca min"],
                saturacion_max=valores["S blanca max"], erosion=valores["Erosion px"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=int, default=1, help="Índice de cámara (default: 1)")
    parser.add_argument("--backend", choices=("auto", "msmf", "dshow"), default="auto")
    parser.add_argument("--ancho", type=int, default=1920, help="Resolucion solicitada a la camara")
    parser.add_argument("--alto", type=int, default=1080)
    parser.add_argument("--modelo", type=Path,
                        default=MODELO)
    parser.add_argument("--imagen", type=Path, help="Probar una foto en vez de la cámara")
    parser.add_argument("--sin-ventana", action="store_true", help="Solo con --imagen")
    parser.add_argument("--salida", type=Path, help="Guardar comparación de --imagen")
    args = parser.parse_args()
    if (args.sin_ventana or args.salida) and not args.imagen:
        parser.error("--sin-ventana y --salida requieren --imagen")
    if args.ancho <= 0 or args.alto <= 0:
        parser.error("Ancho y alto deben ser positivos")
    if not args.modelo.is_file():
        parser.error(f"No existe el modelo: {args.modelo}")
    foto = None
    if args.imagen:
        from ultralytics import YOLO
        from chess_simulator.vision_vivo import extraer
        frame = cv2.imread(str(args.imagen))
        if frame is None:
            parser.error(f"No se pudo leer: {args.imagen}")
        resultado = YOLO(str(args.modelo))(frame, verbose=False, max_det=64)[0]
        foto = {"frame": frame, "detecciones": extraer(resultado, frame)}
        comparacion, medidas = dibujar(frame, foto["detecciones"],
                                       dict(negra_max=85, blanca_min=125,
                                            saturacion_max=110, erosion=3), modo="comparacion")
        for medida in medidas:
            print(medida)
        if args.salida and not cv2.imwrite(str(args.salida), comparacion):
            raise OSError(f"No se pudo guardar: {args.salida}")
        if args.sin_ventana:
            return
    flujo = None
    try:
        cv2.namedWindow(VENTANA, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(VENTANA, 1300, 850)
        for nombre, inicial in CONTROLES.items():
            cv2.createTrackbar(nombre, VENTANA, inicial,
                               15 if nombre == "Erosion px" else 255, lambda _: None)
        if foto is None:
            flujo = FlujoVivo(args.modelo, args.source, args.backend,
                              resolucion=(args.ancho, args.alto))
            flujo.iniciar()
            print(f"Abriendo camara {args.source}. Acepte la notificacion del celular.", flush=True)
        actual = foto
        pausa = False
        modo = "original"
        estado = "Esperando camara y modelo..."
        ultima_captura = time.monotonic()
        while True:
            if flujo:
                nuevo = leer_ultimo(flujo.frames)
                if nuevo:
                    if "error" in nuevo:
                        estado = nuevo["error"]
                        actual = None
                    else:
                        ultima_captura = time.monotonic()
                        if not pausa:
                            ultimo(flujo.pendientes, nuevo)
                resultado = leer_ultimo(flujo.resultados)
                if resultado:
                    if "error" in resultado:
                        raise RuntimeError(resultado["error"])
                    if not pausa:
                        actual = resultado
                if time.monotonic() - ultima_captura > 3:
                    actual = None
                    estado = "Sin imagen reciente de camara; esperando..."
            canvas = np.zeros((600, 1300, 3), np.uint8)
            if actual is not None:
                try:
                    canvas, _ = dibujar(actual["frame"], actual["detecciones"], controles(), modo)
                    estado = "PAUSA: puede ajustar umbrales" if pausa else f'{len(actual["detecciones"])} piezas detectadas'
                    if flujo and not pausa:
                        edad = time.monotonic() - actual["instante"]
                        estado += f" | Antiguedad: {edad:.1f}s"
                except ValueError as error:
                    estado = str(error)
            cv2.putText(canvas, estado, (10, canvas.shape[0] - 15),
                        cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 180, 255), 1, cv2.LINE_AA)
            cv2.imshow(VENTANA, canvas)
            tecla = cv2.waitKey(20) & 0xFF
            if tecla in (27, ord("q")) or cv2.getWindowProperty(VENTANA, cv2.WND_PROP_VISIBLE) < 1:
                break
            if tecla == ord(" "):
                pausa = not pausa
            if tecla == ord("v"):
                modos = ("original", "valor", "comparacion")
                modo = modos[(modos.index(modo) + 1) % len(modos)]
            if tecla == ord("r"):
                for nombre, inicial in CONTROLES.items():
                    cv2.setTrackbarPos(nombre, VENTANA, inicial)
    finally:
        if flujo:
            flujo.cerrar()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
