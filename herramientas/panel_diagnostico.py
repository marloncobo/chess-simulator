"""Panel inferior legible: tablero con estados y diagnóstico al lado.

Sustituye la mitad de abajo de deteccion_doble.dibujar(). En vez de una
leyenda fija, muestra lo que cambia: qué ve cada cámara, qué aporta la
segunda, y qué casillas conviene revisar.
"""
import unicodedata

import cv2
import numpy as np

from chess_simulator.seguimiento import nombre
from herramientas.tablero_diagnostico import dibujar as dibujar_pygame
from chess_simulator.diagnostico import (
    AMBAS, RESCATE_1, RESCATE_2, SOLO_1, SOLO_2, CONFLICTO, CIEGAS, VACIA,
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
    VACIA:     (200, 200, 200),
}

INSIGNIA = {RESCATE_1: "1", RESCATE_2: "2", SOLO_1: "1!", SOLO_2: "2!",
            CONFLICTO: "X", CIEGAS: "?"}

ETIQUETA = {
    AMBAS: "las ven las dos camaras",
    RESCATE_1: "aporta solo la camara 1:",
    RESCATE_2: "aporta solo la camara 2:",
    CONFLICTO: "las camaras discrepan:",
    CIEGAS: "sin ver ahora, se conserva la pieza:",
    VACIA: "vacias",
}


def para_mostrar(casillas, posicion):
    """Una casilla que ninguna cámara ve bien y en la que no se recuerda
    ninguna pieza se muestra como vacía: es lo que el seguimiento ya cree
    (conserva el último estado confirmado). Solo quedan como "sin ver" las
    que tienen una pieza recordada que ahora no se puede comprobar.
    """
    if not casillas:
        return casillas
    salida = {}
    for (f, c), info in casillas.items():
        if info["estado"] == CIEGAS and not (posicion and posicion[f][c]):
            info = {**info, "estado": VACIA, "sin_ver": True}
        salida[f, c] = info
    return salida


def casillas_en(casillas, *estados):
    return sorted((nombre(f, c) for (f, c), d in casillas.items() if d["estado"] in estados),
                  key=lambda n: (n[0], n[1]))


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
    """Pega el tablero de pygame, el mismo motor grafico del main."""
    tablero = dibujar_pygame(posicion, casillas, dudosas,
                             casilla_px=CASILLA, margen=(MARGEN_X, MARGEN_Y))
    alto, ancho = tablero.shape[:2]
    lienzo[0:min(alto, ALTO), 0:ancho] = tablero[0:min(alto, ALTO)]


def dibujar_diagnostico(lienzo, posicion, casillas, inferencia, mensaje, movimiento):
    x0 = MARGEN_X + BOARD_W + 44
    y = 28
    cuenta = resumen(casillas) if casillas else {}

    _txt(lienzo, "QUE APORTA CADA CAMARA", (x0, y), .52, BLANCO, 1)
    y += 24

    # Un renglón por estado, con su color del tablero y las casillas.
    # "Aporta solo la camara N" no dice que la otra no vea esa pieza: dice que
    # la otra no dio una lectura fiable (tapada, confianza baja, color dudoso,
    # o la clasificó como otra pieza que superó su tope). El motivo exacto
    # aparece en CASILLAS A REVISAR.
    for estado in (AMBAS, RESCATE_1, RESCATE_2, CONFLICTO, CIEGAS, VACIA):
        grupo = {RESCATE_1: (RESCATE_1, SOLO_1), RESCATE_2: (RESCATE_2, SOLO_2)}.get(estado, (estado,))
        n = sum(cuenta.get(e, 0) for e in grupo)
        if estado == CIEGAS and not n:
            continue
        color = COLOR[estado]
        cv2.rectangle(lienzo, (x0, y - 10), (x0 + 13, y + 2), color, -1)
        _txt(lienzo, f"{n:>2}", (x0 + 20, y), .47, BLANCO, 1)
        _txt(lienzo, ETIQUETA[estado], (x0 + 46, y), .44, TENUE)
        if estado == VACIA:
            sin_ver = sum(1 for d in casillas.values() if d.get("sin_ver"))
            if sin_ver:
                _txt(lienzo, f"({sin_ver} sin verse ahora: se mantiene lo ultimo visto)",
                     (x0 + 100, y), .42, TENUE)
        elif estado != AMBAS and n:
            lista = " ".join(casillas_en(casillas, *grupo))
            ancho = cv2.getTextSize(ETIQUETA[estado], cv2.FONT_HERSHEY_SIMPLEX, .44, 1)[0][0]
            _txt(lienzo, lista[:58], (x0 + 46 + ancho + 10, y), .44, color, 1)
        y += 21
    y += 14

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
    lista, cuantas = problemas(casillas, limite=5) if casillas else ([], 0)
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
    casillas = para_mostrar(casillas, posicion)
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
    "borde azul 1   la confirma la camara 1; la 2 la tiene tapada",
    "borde naranja 2  la confirma la camara 2; la 1 la tiene tapada",
    "borde ambar 1! 2!  la confirma una camara; la otra la vio dudosa o no la vio",
    "               (el motivo de la otra camara sale en CASILLAS A REVISAR)",
    "letra H        pieza conservada del historial, no observada ahora",
    "borde rojo X   las camaras discrepan en la pieza",
    "rayado gris ?  pieza recordada que ahora ninguna camara alcanza a ver",
    "casilla limpia  vacia (tambien si ahora nadie la ve y no habia pieza)",
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
