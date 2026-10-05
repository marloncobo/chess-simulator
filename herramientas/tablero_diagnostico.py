"""Tablero de diagnóstico dibujado con pygame, el mismo motor del main.

Se renderiza fuera de pantalla a una Surface y se devuelve como array
BGR, listo para pegarlo en el panel de OpenCV. Así la ventana sigue
siendo una sola y no hay que cambiar la arquitectura, pero las piezas
se ven con los símbolos de ajedrez de verdad en vez de letras.

pygame nunca abre ventana desde aquí: solo se inicializa el módulo de
fuentes, que no necesita display.
"""
import os

# pygame saluda por stdout al importarse; aqui solo es ruido.
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import numpy as np
import pygame

from chess_simulator.diagnostico import (
    AMBAS, RESCATE_1, RESCATE_2, SOLO_1, SOLO_2, CONFLICTO, CIEGAS,
)

# Mismos valores que chess_simulator/tablero_pygame.py
CLARO = (240, 217, 181)
OSCURO = (181, 136, 99)

SIMBOLOS = {
    "?": "♜",
    "t": "♜", "c": "♞", "a": "♝",
    "d": "♛", "r": "♚", "p": "♟",
    "T": "♖", "C": "♘", "A": "♗",
    "D": "♕", "R": "♔", "P": "♙",
}

# En RGB, porque aquí manda pygame. La conversión a BGR va al final.
COLOR = {
    AMBAS:     (130, 220, 120),
    RESCATE_1: (90, 180, 255),
    RESCATE_2: (255, 150, 90),
    SOLO_1:    (255, 220, 80),
    SOLO_2:    (255, 220, 80),
    CONFLICTO: (255, 80, 80),
    CIEGAS:    (128, 128, 132),
}

INSIGNIA = {RESCATE_1: "1", RESCATE_2: "2", SOLO_1: "1!", SOLO_2: "2!",
            CONFLICTO: "X", CIEGAS: "?"}

FONDO = (22, 24, 26)
TENUE = (155, 155, 160)

_fuentes = {}


def _fuente(nombre, tam):
    """Las fuentes se crean una vez; SysFont es costoso por llamada."""
    clave = (nombre, tam)
    if clave not in _fuentes:
        if not pygame.font.get_init():
            pygame.font.init()
        _fuentes[clave] = pygame.font.SysFont(nombre, tam)
    return _fuentes[clave]


def _simbolo(pieza):
    """Devuelve (glifo, color) replicando la lógica del tablero del main."""
    neutra = pieza.startswith("?")
    if neutra and len(pieza) > 1:
        glifo = SIMBOLOS[pieza[1:].lower()]
        return glifo, (65, 85, 115)
    glifo = SIMBOLOS[pieza]
    return glifo, ((255, 255, 255) if pieza.isupper() else (20, 20, 20))


def _glifo_con_contorno(superficie, fuente, glifo, color, centro_rect):
    """
    Dibuja la pieza con un borde del color contrario.

    Sin esto, una pieza blanca sobre casilla clara (o negra sobre
    oscura) casi desaparece: los simbolos de ajedrez son huecos y solo
    se distinguen por su contorno.
    """
    borde = (25, 25, 30) if sum(color) > 380 else (245, 245, 245)
    x, y, w, h = centro_rect

    contorno = fuente.render(glifo, True, borde)
    px = x + (w - contorno.get_width()) // 2
    py = y + (h - contorno.get_height()) // 2
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1),
                   (-1, -1), (1, -1), (-1, 1), (1, 1)):
        superficie.blit(contorno, (px + dx, py + dy))

    superficie.blit(fuente.render(glifo, True, color), (px, py))


def _rayado(superficie, rect, color, paso=7):
    """Trama diagonal para las casillas sin información."""
    x0, y0, w, h = rect
    for d in range(-h, w, paso):
        inicio = (x0 + max(0, d), y0 + max(0, -d))
        fin = (x0 + min(w, d + h), y0 + min(h, w - d))
        pygame.draw.line(superficie, color, inicio, fin, 1)


def dibujar(posicion, casillas, dudosas, casilla_px=47, margen=(34, 14)):
    """
    Renderiza el tablero con su diagnóstico y lo devuelve en BGR.

    El borde y la insignia dicen quién vio cada casilla; el glifo, qué
    pieza es. Las dos capas se leen por separado.
    """
    if not pygame.font.get_init():
        pygame.font.init()

    mx, my = margen
    lado = casilla_px * 8
    ancho, alto = mx + lado + 14, my + lado + 26

    sup = pygame.Surface((ancho, alto))
    sup.fill(FONDO)

    f_pieza = _fuente("segoeuisymbol,dejavusans", int(casilla_px * .78))
    f_marca = _fuente("dejavusans", 11)
    f_coord = _fuente("dejavusans", 12)

    for fila in range(8):
        for col in range(8):
            x, y = mx + col * casilla_px, my + fila * casilla_px
            rect = pygame.Rect(x, y, casilla_px, casilla_px)
            pygame.draw.rect(sup, CLARO if (fila + col) % 2 == 0 else OSCURO, rect)

            info = casillas.get((fila, col)) if casillas else None
            estado = info["estado"] if info else None

            if estado == CIEGAS:
                _rayado(sup, (x, y, casilla_px, casilla_px), (96, 96, 100))

            pieza = posicion[fila][col] if posicion else ""
            if pieza:
                glifo, color_glifo = _simbolo(pieza)
                _glifo_con_contorno(sup, f_pieza, glifo, color_glifo,
                                    (x, y, casilla_px, casilla_px))

            color = COLOR.get(estado)
            if estado == AMBAS:
                pygame.draw.circle(sup, COLOR[AMBAS], (x + 7, y + 7), 3)
            elif color:
                pygame.draw.rect(sup, color, rect, 2)
                marca = INSIGNIA.get(estado, "")
                if marca:
                    etiqueta = f_marca.render(marca, True, (15, 15, 15))
                    fondo = pygame.Rect(x + casilla_px - etiqueta.get_width() - 5, y + 1,
                                        etiqueta.get_width() + 4, etiqueta.get_height() + 2)
                    pygame.draw.rect(sup, color, fondo)
                    sup.blit(etiqueta, (fondo.x + 2, fondo.y + 1))
            elif (fila, col) in (dudosas or ()) and not (info and info.get("sin_ver")):
                pygame.draw.rect(sup, (255, 160, 40), rect, 2)

            # No presentar una pieza retenida como si acabara de observarse.
            if pieza and (not info or info.get("pieza") != pieza):
                etiqueta = f_marca.render("H", True, (245, 245, 245))
                fondo = pygame.Rect(x+1, y+casilla_px-15, 13, 14)
                pygame.draw.rect(sup, (70, 70, 75), fondo)
                sup.blit(etiqueta, (fondo.x+2, fondo.y))

    for n in range(8):
        num = f_coord.render(str(8 - n), True, TENUE)
        sup.blit(num, (mx - 16, my + n * casilla_px + casilla_px // 2 - 7))
        letra = f_coord.render("abcdefgh"[n], True, TENUE)
        sup.blit(letra, (mx + n * casilla_px + casilla_px // 2 - 4, my + lado + 5))

    pygame.draw.rect(sup, (66, 68, 72), pygame.Rect(mx, my, lado, lado), 1)

    # pygame entrega (ancho, alto, 3) en RGB; OpenCV espera (alto, ancho, 3) en BGR
    return pygame.surfarray.array3d(sup).swapaxes(0, 1)[:, :, ::-1].copy()
