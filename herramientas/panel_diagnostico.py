"""Panel inferior legible: tablero con estados y diagnóstico al lado.

Sustituye la mitad de abajo de deteccion_doble.dibujar(). En vez de una
leyenda fija, muestra lo que cambia: qué ve cada cámara, qué aporta la
segunda, y qué casillas conviene revisar.
"""
import unicodedata

import cv2
import numpy as np

from chess_simulator.seguimiento import nombre
from chess_simulator.diagnostico import (
    AMBAS, RESCATE_1, RESCATE_2, SOLO_1, SOLO_2, CONFLICTO, CIEGAS,
    contar_clases, problemas, resumen,
)

ALTO = 450
ANCHO = 1280
CASILLA = 47
MARGEN_X, MARGEN_Y = 34, 14
BOARD_W = CASILLA * 8

FONDO = (26, 24, 22)
CLARA = (182, 212, 236)
OSCURA = (92, 132, 162)
BLANCO = (242, 242, 242)
TENUE = (150, 150, 155)

# Un color por estado, usado igual en el tablero y en el resumen para
# que la vista y los números se lean como una sola cosa.
COLOR = {
    AMBAS:     (120, 220, 130),   # verde
    RESCATE_1: (255, 180, 90),    # azul
    RESCATE_2: (90, 150, 255),    # naranja
    SOLO_1:    (80, 220, 255),    # ambar
    SOLO_2:    (80, 220, 255),
    CONFLICTO: (80, 80, 255),     # rojo
    CIEGAS:    (130, 130, 130),   # gris
}

INSIGNIA = {RESCATE_1: "1", RESCATE_2: "2", SOLO_1: "1!", SOLO_2: "2!",
            CONFLICTO: "X", CIEGAS: "?"}

ETIQUETA = {
    AMBAS: "confirmadas por las dos",
    RESCATE_1: "solo las ve la camara 1",
    RESCATE_2: "solo las ve la camara 2",
    CONFLICTO: "las camaras discrepan",
    CIEGAS: "tapadas, sin informacion",
}


def _txt(img, texto, punto, escala=.45, color=BLANCO, grosor=1):
    """OpenCV no trae acentos en esta fuente."""
    texto = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    cv2.putText(img, texto, punto, cv2.FONT_HERSHEY_SIMPLEX, escala,
                color, grosor, cv2.LINE_AA)


def _rayado(img, x0, y0, lado, color, paso=7):
    """Trama diagonal para las casillas sin información."""
    for d in range(-lado, lado, paso):
        cv2.line(img, (x0 + max(0, d), y0 + max(0, -d)),
                 (x0 + min(lado, d + lado), y0 + min(lado, lado - d)),
                 color, 1, cv2.LINE_AA)


def dibujar_tablero(lienzo, posicion, casillas, dudosas):
    ox, oy = MARGEN_X, MARGEN_Y

    for f in range(8):
        for c in range(8):
            x, y = ox + c * CASILLA, oy + f * CASILLA
            base = CLARA if (f + c) % 2 == 0 else OSCURA
            cv2.rectangle(lienzo, (x, y), (x + CASILLA - 1, y + CASILLA - 1), base, -1)

            info = casillas.get((f, c)) if casillas else None
            estado = info["estado"] if info else None
            color = COLOR.get(estado)

            if estado == CIEGAS:
                _rayado(lienzo, x, y, CASILLA - 1, (70, 70, 72))

            pieza = posicion[f][c] if posicion else ""
            if pieza:
                clara = pieza.lstrip("?").isupper()
                cv2.circle(lienzo, (x + CASILLA // 2, y + CASILLA // 2 - 1), 16,
                           (238, 238, 238) if clara else (28, 28, 28), -1, cv2.LINE_AA)
                cv2.circle(lienzo, (x + CASILLA // 2, y + CASILLA // 2 - 1), 16,
                           (120, 120, 120), 1, cv2.LINE_AA)
                letra = pieza.lstrip("?").upper()
                (tw, th), _ = cv2.getTextSize(letra, cv2.FONT_HERSHEY_SIMPLEX, .62, 2)
                _txt(lienzo, letra,
                     (x + (CASILLA - tw) // 2, y + (CASILLA + th) // 2 - 1), .62,
                     (20, 20, 20) if clara else (246, 246, 246), 2)

            # El recuadro dice el estado; la insignia lo abrevia
            if color and estado != AMBAS:
                cv2.rectangle(lienzo, (x + 1, y + 1),
                              (x + CASILLA - 2, y + CASILLA - 2), color, 2)
                marca = INSIGNIA.get(estado, "")
                if marca:
                    cv2.rectangle(lienzo, (x + CASILLA - 17, y + 1),
                                  (x + CASILLA - 2, y + 14), color, -1)
                    _txt(lienzo, marca, (x + CASILLA - 16, y + 12), .34, (10, 10, 10), 1)
            elif estado == AMBAS:
                cv2.circle(lienzo, (x + 7, y + 7), 3, COLOR[AMBAS], -1, cv2.LINE_AA)
            elif (f, c) in (dudosas or ()):
                cv2.rectangle(lienzo, (x + 1, y + 1),
                              (x + CASILLA - 2, y + CASILLA - 2), (0, 140, 255), 2)

    for n in range(8):
        _txt(lienzo, str(8 - n), (ox - 18, oy + n * CASILLA + 31), .42, TENUE)
        _txt(lienzo, "abcdefgh"[n], (ox + n * CASILLA + 21, oy + BOARD_W + 17), .42, TENUE)
    cv2.rectangle(lienzo, (ox, oy), (ox + BOARD_W, oy + BOARD_W), (60, 62, 66), 1)


def dibujar_diagnostico(lienzo, posicion, casillas, inferencia, mensaje, movimiento):
    x0 = MARGEN_X + BOARD_W + 44
    y = 28
    cuenta = resumen(casillas) if casillas else {}

    _txt(lienzo, "QUE APORTA CADA CAMARA", (x0, y), .52, BLANCO, 1)
    y += 24

    # Fila de chips: un renglón por estado, con su color del tablero
    for estado in (AMBAS, RESCATE_1, RESCATE_2, CONFLICTO, CIEGAS):
        n = cuenta.get(estado, 0)
        if estado == CONFLICTO:
            n = cuenta.get(CONFLICTO, 0)
        if estado == RESCATE_1:
            n += cuenta.get(SOLO_1, 0)
        if estado == RESCATE_2:
            n += cuenta.get(SOLO_2, 0)
        color = COLOR[estado]
        cv2.rectangle(lienzo, (x0, y - 10), (x0 + 13, y + 2), color, -1)
        _txt(lienzo, f"{n:>2}", (x0 + 20, y), .47, BLANCO, 1)
        _txt(lienzo, ETIQUETA[estado], (x0 + 46, y), .44, TENUE)
        y += 21

    r1 = cuenta.get(RESCATE_1, 0) + cuenta.get(SOLO_1, 0)
    r2 = cuenta.get(RESCATE_2, 0) + cuenta.get(SOLO_2, 0)
    y += 6
    if casillas:
        if r1 + r2 == 0:
            aviso = "Las dos camaras ven lo mismo: la segunda no aporta nada"
            color = (80, 220, 255)
        else:
            aviso = f"Sin la segunda camara faltarian {r2} pieza(s); sin la primera, {r1}"
            color = COLOR[AMBAS]
        _txt(lienzo, aviso, (x0, y), .44, color)
    y += 26

    # --- Conteo por clase ---
    _txt(lienzo, "PIEZAS POR CLASE", (x0, y), .52, BLANCO, 1)
    y += 22
    filas, total = contar_clases(posicion)
    cx = x0
    for fila in filas:
        exceso, faltan = fila["exceso"], fila["faltan"]
        color = (80, 80, 255) if exceso else ((80, 220, 255) if faltan else TENUE)
        _txt(lienzo, fila["clase"], (cx, y), .5, BLANCO, 1)
        _txt(lienzo, f'{fila["n"]}/{fila["esperadas"]}', (cx + 16, y), .45, color)
        if exceso:
            _txt(lienzo, f"+{exceso}", (cx + 16, y + 16), .4, (80, 80, 255), 1)
        elif faltan:
            _txt(lienzo, f"-{faltan}", (cx + 16, y + 16), .4, (80, 220, 255), 1)
        cx += 76
    _txt(lienzo, f"total {total}/32", (cx + 4, y), .45,
         (80, 80, 255) if total > 32 else TENUE)
    y += 42

    # --- Casillas a revisar ---
    _txt(lienzo, "CASILLAS A REVISAR", (x0, y), .52, BLANCO, 1)
    y += 21
    lista, cuantas = problemas(casillas, limite=6) if casillas else ([], 0)
    if not lista:
        _txt(lienzo, "ninguna" if casillas else "esperando vistas", (x0, y), .44, TENUE)
        y += 19
    for casilla, info in lista:
        color = COLOR[info["estado"]]
        cv2.rectangle(lienzo, (x0, y - 9), (x0 + 11, y + 1), color, -1)
        _txt(lienzo, casilla, (x0 + 18, y), .46, BLANCO, 1)
        _txt(lienzo, info["detalle"][:62], (x0 + 54, y), .42, TENUE)
        y += 19
    if cuantas > len(lista):
        _txt(lienzo, f"... y {cuantas - len(lista)} mas", (x0, y), .42, TENUE)
        y += 19

    # --- Pie ---
    y = ALTO - 48
    cv2.line(lienzo, (x0, y - 10), (ANCHO - 20, y - 10), (54, 52, 50), 1)
    _txt(lienzo, f"inferencia {inferencia*1000:.0f} ms", (x0, y + 4), .42, TENUE)
    _txt(lienzo, str(movimiento)[:52], (x0 + 150, y + 4), .42, TENUE)
    _txt(lienzo, str(mensaje)[:78], (x0, y + 22), .43, (90, 200, 255))
    _txt(lienzo, "1/2 calibrar   L cargar   R reconectar   S reiniciar   H ayuda   Q salir",
         (x0, y + 40), .4, (110, 110, 114))


def panel_inferior(posicion, casillas, dudosas, inferencia, mensaje, movimiento):
    lienzo = np.full((ALTO, ANCHO, 3), FONDO, np.uint8)
    dibujar_tablero(lienzo, posicion, casillas, dudosas)
    dibujar_diagnostico(lienzo, posicion, casillas, inferencia, mensaje, movimiento)
    return lienzo


AYUDA = [
    "AYUDA",
    "",
    "1 / 2    calibrar cada camara (congela la imagen)",
    "         clics en orden: a8 > h8 > h1 > a1",
    "L        cargar calibraciones guardadas",
    "         solo si NO movio las camaras",
    "R        reconectar camaras",
    "S        empezar una posicion nueva",
    "H        ocultar esta ayuda",
    "Q / Esc  salir",
    "",
    "EN EL TABLERO",
    "punto verde    la ven las dos camaras",
    "borde azul 1   solo la ve la camara 1 (la 2 la tiene tapada)",
    "borde naranja 2  solo la ve la camara 2",
    "borde ambar 1! 2!  una la ve y la otra dice que esta vacia",
    "               son los falsos positivos mas probables",
    "borde rojo X   las camaras discrepan en la pieza",
    "rayado gris ?  tapada en las dos; conserva el estado anterior",
    "",
    "T torre  C caballo  A alfil  D dama  R rey  P peon",
]


def panel_ayuda():
    lienzo = np.full((ALTO, ANCHO, 3), FONDO, np.uint8)
    for n, linea in enumerate(AYUDA):
        negrita = linea and not linea.startswith(" ") and linea.isupper()
        _txt(lienzo, linea, (MARGEN_X, 24 + n * 20), .5 if negrita else .44,
             BLANCO if negrita else TENUE, 1)
    return lienzo
