"""Punto de entrada: fotografía -> detector de torres -> casillas -> Pygame.

El modo imagen es una inspección estática, no una fuente de muestras temporales.
No inventa color ni piezas que el detector actual no devuelve.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
import pygame

from chess_simulator.seguimiento import nombre
from chess_simulator.tablero_pygame import CASILLA, LADO, dibujar_piezas, dibujar_tablero

from chess_simulator.rutas import IMAGENES, MODELO


def detectar(ruta, modelo):
    # Reutilizar el detector sin ejecutar su CLI ni sobrescribir sus CSV/imágenes.
    from chess_simulator.torres import CONFIANZA, centros_de_masa, limitar_torres
    from ultralytics import YOLO

    red = YOLO(str(modelo))
    resultado = red(str(ruta), conf=CONFIANZA, verbose=False)[0]
    return limitar_torres(centros_de_masa(resultado, red))


def proyectar(torres, esquinas):
    """Los vértices corresponden a los extremos a8, h8, h1, a1 del tablero.

    Se usa el centroide existente, con la limitación de perspectiva/altura que
    tiene ese punto. No se confunden los centros de las torres con las esquinas.
    """
    puntos = np.asarray(esquinas, dtype=np.float32)
    if puntos.shape != (4, 2) or not np.isfinite(puntos).all():
        raise ValueError("Marque cuatro vértices válidos")
    if not cv2.isContourConvex(puntos.reshape(-1, 1, 2)) or abs(cv2.contourArea(puntos)) < 1:
        raise ValueError("Los vértices deben formar un cuadrilátero sin cruces")
    destino = np.float32([[0, 0], [8, 0], [8, 8], [0, 8]])
    matriz = cv2.getPerspectiveTransform(puntos, destino)
    posicion = [[""] * 8 for _ in range(8)]
    asignadas, fuera, ocupadas = [], [], set()
    for i, torre in enumerate(torres, 1):
        punto = np.float32(torre["centro"]).reshape(1, 1, 2)
        x, y = cv2.perspectiveTransform(punto, matriz)[0, 0]
        if not np.isfinite([x, y]).all() or not (0 <= x < 8 and 0 <= y < 8):
            fuera.append(i)
            continue
        col, fila = int(x), int(y)
        if (fila, col) in ocupadas:
            raise ValueError("Dos detecciones caen en la misma casilla; revise la calibración")
        ocupadas.add((fila, col))
        posicion[fila][col] = "?"
        asignadas.append((i, nombre(fila, col)))
    return posicion, asignadas, fuera


def elegir_imagen():
    import tkinter as tk
    from tkinter.filedialog import askopenfilename

    ventana = tk.Tk()
    ventana.withdraw()
    try:
        return askopenfilename(title="Seleccione una fotografía del tablero",
                               initialdir=str(IMAGENES),
                               filetypes=[("Imágenes", "*.jpg *.jpeg *.png *.bmp *.webp")])
    finally:
        ventana.destroy()


def mostrar_imagen(ruta, modelo):
    # imdecode admite rutas Unicode en Windows.
    imagen = cv2.imdecode(np.fromfile(ruta, dtype=np.uint8), cv2.IMREAD_COLOR)
    if imagen is None:
        raise ValueError(f"No se pudo abrir la imagen: {ruta}")
    alto, ancho = imagen.shape[:2]
    escala = min(540 / ancho, 570 / alto)
    tamano = (max(1, round(ancho * escala)), max(1, round(alto * escala)))
    reducida = cv2.resize(imagen, tamano)
    rgb = cv2.cvtColor(reducida, cv2.COLOR_BGR2RGB)
    pygame.init()
    pantalla = pygame.display.set_mode((1200, 780))
    pygame.display.set_caption("Fotografía y tablero detectado — solo torres")
    foto = pygame.image.frombuffer(rgb.tobytes(), tamano, "RGB")
    rect_foto = foto.get_rect(topleft=(10, 100))
    tablero = pygame.Surface((LADO, LADO))
    fuente = pygame.font.SysFont("segoeuisymbol,dejavusans", int(CASILLA * 0.7))
    texto = pygame.font.SysFont("arial", 18)
    reloj = pygame.time.Clock()
    esquinas, torres = [], None
    posicion, asignadas, fuera = [[""] * 8 for _ in range(8)], [], []
    estado = "Cargando modelo y detectando torres..."
    descartadas = []
    futuro_procesado = False
    executor = ThreadPoolExecutor(max_workers=1)
    futuro = executor.submit(detectar, ruta, modelo)
    corriendo = True

    def coordenada_pantalla(p):
        return (rect_foto.x + round(p[0] * tamano[0] / ancho),
                rect_foto.y + round(p[1] * tamano[1] / alto))

    def actualizar():
        nonlocal posicion, asignadas, fuera, estado
        if torres is None or len(esquinas) != 4:
            return
        try:
            posicion, asignadas, fuera = proyectar(torres, esquinas)
            estado = "  ".join(f"T{i}: {casilla}" for i, casilla in asignadas) or "Ninguna torre asignada"
            if fuera:
                estado += " | Fuera: " + ", ".join(map(str, fuera))
        except ValueError as error:
            posicion, asignadas, fuera = [[""] * 8 for _ in range(8)], [], []
            estado = str(error)

    try:
        while corriendo:
            for evento in pygame.event.get():
                if evento.type == pygame.QUIT or (evento.type == pygame.KEYDOWN and evento.key == pygame.K_ESCAPE):
                    corriendo = False
                elif evento.type == pygame.KEYDOWN and evento.key == pygame.K_r:
                    esquinas.clear()
                    posicion, asignadas, fuera = [[""] * 8 for _ in range(8)], [], []
                    estado = "Marque de nuevo los cuatro vértices"
                elif evento.type == pygame.MOUSEBUTTONDOWN and evento.button == 1:
                    if rect_foto.collidepoint(evento.pos) and len(esquinas) < 4:
                        x = (evento.pos[0] - rect_foto.x) * ancho / tamano[0]
                        y = (evento.pos[1] - rect_foto.y) * alto / tamano[1]
                        esquinas.append((x, y))
                        actualizar()
            if futuro.done() and not futuro_procesado:
                futuro_procesado = True
                try:
                    torres, descartadas = futuro.result()
                    estado = f"{len(torres)} torres detectadas. Marque los cuatro vértices."
                    actualizar()
                except Exception as error:
                    estado = "Error al detectar; consulte la terminal"
                    print(f"Error de detección: {error}", flush=True)
            pantalla.fill((30, 30, 35))
            pantalla.blit(foto, rect_foto)
            dibujar_tablero(tablero)
            dibujar_piezas(tablero, fuente, posicion)
            pantalla.blit(tablero, (560, 60))
            for i, p in enumerate(esquinas):
                punto = coordenada_pantalla(p)
                pygame.draw.circle(pantalla, (60, 220, 120), punto, 5)
                pantalla.blit(texto.render(("a8", "h8", "h1", "a1")[i], True, (60, 220, 120)), punto)
            if len(esquinas) > 1:
                pygame.draw.lines(pantalla, (60, 220, 120), len(esquinas) == 4,
                                  [coordenada_pantalla(p) for p in esquinas], 2)
            for i, torre in enumerate(torres or [], 1):
                punto = coordenada_pantalla(torre["centro"])
                pygame.draw.circle(pantalla, (240, 90, 65), punto, 5)
                pantalla.blit(texto.render(f"T{i}", True, (250, 70, 40)), (punto[0] + 7, punto[1]))
            lineas = [
                (10, 10, "Marque los vértices EXTERIORES de las 64 casillas:"),
                (10, 36, "a8 → h8 → h1 → a1. R: repetir. Esc: salir."),
                (560, 10, "SOLO TORRES DETECTADAS · gris = color desconocido"),
                (10, 712, estado),
                (10, 738, f"Fotografía estática · centros de silueta · descartadas por el detector: {len(descartadas)}"),
            ]
            for x, y, linea in lineas:
                pantalla.blit(texto.render(linea, True, (240, 240, 240)), (x, y))
            pygame.display.flip()
            reloj.tick(60)
    finally:
        pygame.quit()
        # La inferencia en curso termina sin tocar la ventana ni escribir archivos.
        executor.shutdown(wait=True, cancel_futures=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--imagen", type=Path, help="Fotografía a detectar; si se omite se abre un selector")
    grupo.add_argument("--entrada", type=Path, help="Observaciones JSON externas (modo de seguimiento existente)")
    grupo.add_argument("--camara", action="store_true", help="Detección en tiempo real; usa source=1")
    from herramientas.probar_dos_camaras import fuente
    parser.add_argument("--source", type=fuente, default=1,
                        help="Índice de cámara (por defecto 1) o URL del puente del celular, "
                             "por ejemplo http://127.0.0.1:5002/stream")
    parser.add_argument("--backend", choices=("auto", "msmf", "dshow"), default="auto")
    parser.add_argument("--punto", choices=("base", "centro"), default="base",
                        help="Base aproximada para vista inclinada o centro para vista cenital")
    parser.add_argument("--confianza", type=float, default=.25,
                        help="Confianza mínima de YOLO (por defecto 0.25)")
    parser.add_argument("--duracion", type=float, help=argparse.SUPPRESS)
    parser.add_argument("--modelo", type=Path, default=MODELO, help="Modelo local de segmentación")
    parser.add_argument("--hsv-negra-max", type=int, default=85, help="V máximo para piezas negras")
    parser.add_argument("--hsv-blanca-min", type=int, default=125, help="V mínimo para piezas blancas")
    parser.add_argument("--hsv-saturacion-max", type=int, default=110, help="S máximo para piezas blancas")
    parser.add_argument("--hsv-erosion", type=int, default=3, help="Erosión interior de la máscara (0 a 15 px)")
    args = parser.parse_args(argv)
    if args.camara:
        if not args.modelo.is_file():
            parser.error(f"El modelo local no existe: {args.modelo}")
        from chess_simulator.tiempo_real import ejecutar
        if isinstance(args.source, str) and args.backend != "auto":
            parser.error("Una URL de cámara necesita --backend auto")
        if not 0 < args.confianza <= 1:
            parser.error("--confianza debe estar entre 0 y 1")
        if not (0 <= args.hsv_negra_max < args.hsv_blanca_min <= 255
                and 0 <= args.hsv_saturacion_max <= 255 and 0 <= args.hsv_erosion <= 15):
            parser.error("Umbrales HSV inválidos: 0 <= negra < blanca <= 255, S entre 0 y 255, erosión entre 0 y 15")
        parametros_hsv = dict(negra_max=args.hsv_negra_max, blanca_min=args.hsv_blanca_min,
                              saturacion_max=args.hsv_saturacion_max, erosion=args.hsv_erosion)
        ejecutar(args.modelo, args.source, args.backend, args.punto, args.duracion, args.confianza,
                 parametros_hsv=parametros_hsv)
        return
    if args.entrada is not None:
        from chess_simulator.tablero_pygame import main as ejecutar_tablero
        ejecutar_tablero(["--entrada", str(args.entrada)])
        return
    ruta = args.imagen
    if ruta is None:
        elegida = elegir_imagen()
        if not elegida:
            return
        ruta = Path(elegida)
    if not ruta.is_file():
        parser.error(f"La imagen no existe: {ruta}")
    if not args.modelo.is_file():
        parser.error(f"El modelo local no existe: {args.modelo}")
    try:
        mostrar_imagen(ruta, args.modelo)
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
