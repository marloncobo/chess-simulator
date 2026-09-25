"""
Deteccion de torres en fotos de tablero de ajedrez.

Para cada torre detectada calcula su CENTRO DE MASA a partir de la
mascara de segmentacion, usando momentos geometricos:

    cx = M10 / M00
    cy = M01 / M00

donde M00 es el area de la mascara. Devuelve las coordenadas en
pixeles de la imagen, sin suponer nada sobre donde esta cada torre.

Uso:
    python3 torres.py foto.jpg
    python3 torres.py fotos/
    python3 torres.py foto1.jpg foto2.jpg
    python3 torres.py                   -> usa prueba.jpeg
"""

import csv
import glob
import os
import sys

import cv2
import numpy as np
from ultralytics import YOLO

# ----- CONFIGURACION -----
MODELO = "bestnano.pt"
CLASE_TORRE = "TOWER"
CONFIANZA = 0.25
CSV_SALIDA = "torres_detectadas.csv"
EXTENSIONES = (".jpg", ".jpeg", ".png", ".bmp", ".webp")

# Colores en BGR (asi los maneja OpenCV)
COLOR_SILUETA = (0, 255, 255)     # amarillo
COLOR_PUNTO = (0, 0, 255)         # rojo
COLOR_ETIQUETA = (255, 255, 255)  # fondo blanco de la etiqueta
COLOR_TEXTO = (20, 20, 20)        # texto casi negro
# -------------------------


def centros_de_masa(resultado, model):
    """Centro de masa de la mascara de cada torre detectada."""
    torres = []
    if resultado.masks is None:
        return torres

    for i, poligono in enumerate(resultado.masks.xy):
        if model.names[int(resultado.boxes.cls[i])] != CLASE_TORRE:
            continue

        puntos = np.array(poligono, dtype=np.int32)
        M = cv2.moments(puntos)
        if M["m00"] == 0:
            continue

        torres.append({
            "centro": (M["m10"] / M["m00"], M["m01"] / M["m00"]),
            "area": M["m00"],
            "conf": float(resultado.boxes.conf[i]),
            "poligono": puntos,
        })

    # Orden estable: de arriba a abajo, de izquierda a derecha
    torres.sort(key=lambda t: (t["centro"][1], t["centro"][0]))
    return torres


def dibujar_etiqueta(imagen, texto, ancla, escala, grosor):
    """
    Etiqueta con fondo solido y una linea guia hasta el punto.
    El fondo es lo que la hace legible sobre cualquier casilla,
    clara u oscura.
    """
    alto_img, ancho_img = imagen.shape[:2]
    margen = int(8 * escala) + 4

    (ancho_txt, alto_txt), base = cv2.getTextSize(
        texto, cv2.FONT_HERSHEY_SIMPLEX, escala, grosor)

    caja_w = ancho_txt + margen * 2
    caja_h = alto_txt + base + margen * 2

    # Por defecto arriba a la derecha del punto
    desplaza = int(18 * escala) + 8
    x = ancla[0] + desplaza
    y = ancla[1] - desplaza - caja_h

    # Si se sale por la derecha, la pasamos al lado izquierdo
    if x + caja_w > ancho_img - 4:
        x = ancla[0] - desplaza - caja_w
    # Si se sale por arriba, la bajamos
    if y < 4:
        y = ancla[1] + desplaza
    # Ajuste final para no salirse por ningun borde
    x = max(4, min(x, ancho_img - caja_w - 4))
    y = max(4, min(y, alto_img - caja_h - 4))

    # Linea guia del punto a la esquina mas cercana de la caja
    destino_x = x if x > ancla[0] else x + caja_w
    destino_y = y + caja_h // 2
    cv2.line(imagen, ancla, (destino_x, destino_y), COLOR_PUNTO,
             max(1, grosor - 1), cv2.LINE_AA)

    # Caja: sombra, relleno y borde
    cv2.rectangle(imagen, (x + 2, y + 2), (x + caja_w + 2, y + caja_h + 2),
                  (0, 0, 0), -1)
    cv2.rectangle(imagen, (x, y), (x + caja_w, y + caja_h),
                  COLOR_ETIQUETA, -1)
    cv2.rectangle(imagen, (x, y), (x + caja_w, y + caja_h),
                  COLOR_PUNTO, max(1, grosor - 1))

    cv2.putText(imagen, texto, (x + margen, y + margen + alto_txt),
                cv2.FONT_HERSHEY_SIMPLEX, escala, COLOR_TEXTO,
                grosor, cv2.LINE_AA)


def dibujar(imagen, torres, ruta):
    """Silueta, centro de masa y etiqueta legible de cada torre."""
    alto, ancho = imagen.shape[:2]

    # El tamano del texto se adapta a la resolucion de la foto
    escala = max(0.5, min(1.4, ancho / 1400))
    grosor = max(1, int(round(escala * 1.8)))
    radio = max(4, int(round(escala * 7)))

    for t in torres:
        cv2.polylines(imagen, [t["poligono"]], True, COLOR_SILUETA,
                      max(2, grosor), cv2.LINE_AA)

    for n, t in enumerate(torres, 1):
        x, y = t["centro"]
        p = (int(round(x)), int(round(y)))

        # Punto: circulo blanco relleno con anillo rojo, bien visible
        cv2.circle(imagen, p, radio + 3, (255, 255, 255), -1, cv2.LINE_AA)
        cv2.circle(imagen, p, radio + 3, COLOR_PUNTO, grosor, cv2.LINE_AA)
        cv2.circle(imagen, p, max(1, radio - 3), COLOR_PUNTO, -1, cv2.LINE_AA)

        dibujar_etiqueta(imagen, f"T{n}  ({p[0]}, {p[1]})", p, escala, grosor)

    base = os.path.splitext(os.path.basename(ruta))[0]
    salida = f"torres_{base}.jpg"
    cv2.imwrite(salida, imagen)
    print(f"  -> {salida}")


def procesar(ruta, model):
    imagen = cv2.imread(ruta)
    if imagen is None:
        print(f"\n[!] No se pudo abrir: {ruta}")
        return []

    nombre = os.path.basename(ruta)
    resultado = model(ruta, conf=CONFIANZA, verbose=False)[0]
    torres = centros_de_masa(resultado, model)

    print(f"\n=== {nombre} ===")
    print(f"Torres detectadas: {len(torres)}")

    filas = []
    if torres:
        print(f"  {'#':<4}{'x (px)':>10}{'y (px)':>10}{'area':>11}{'conf':>8}")
        for n, t in enumerate(torres, 1):
            x, y = t["centro"]
            print(f"  {n:<4}{x:>10.1f}{y:>10.1f}{t['area']:>11.0f}{t['conf']:>8.2f}")
            filas.append({
                "imagen": nombre,
                "torre": n,
                "x_px": round(x, 1),
                "y_px": round(y, 1),
                "area_px": round(t["area"], 0),
                "conf": round(t["conf"], 3),
            })
    else:
        print("  [!] Ninguna torre detectada. Prueba bajando CONFIANZA.")

    dibujar(imagen, torres, ruta)
    return filas


def recolectar_rutas(argumentos):
    if not argumentos:
        return ["prueba.jpeg"]

    rutas = []
    for arg in argumentos:
        if os.path.isdir(arg):
            for ext in EXTENSIONES:
                rutas.extend(sorted(glob.glob(os.path.join(arg, f"*{ext}"))))
        else:
            rutas.append(arg)
    return rutas


def main():
    rutas = recolectar_rutas(sys.argv[1:])
    if not rutas:
        print("No se encontraron imagenes.")
        return

    print(f"Imagenes a procesar: {len(rutas)}")
    model = YOLO(MODELO)

    todas = []
    for ruta in rutas:
        todas.extend(procesar(ruta, model))

    print("\n" + "=" * 52)
    print(f"Imagenes procesadas: {len(rutas)}")
    print(f"Torres en total:     {len(todas)}")

    if todas:
        confianzas = [f["conf"] for f in todas]
        print(f"Confianza promedio:  {np.mean(confianzas):.2f} "
              f"(min {min(confianzas):.2f}, max {max(confianzas):.2f})")

        with open(CSV_SALIDA, "w", newline="") as f:
            escritor = csv.DictWriter(f, fieldnames=list(todas[0].keys()))
            escritor.writeheader()
            escritor.writerows(todas)
        print(f"\nResultados guardados en: {CSV_SALIDA}")


if __name__ == "__main__":
    main()
