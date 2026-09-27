import argparse
from pathlib import Path
import time

import pygame

from chess_simulator.rutas import OBSERVACION
from chess_simulator.entrada import EntradaArchivo
from chess_simulator.seguimiento import Seguimiento, indices

# ----- CONFIGURACION -----
CASILLA = 80                    # pixeles por casilla
LADO = CASILLA * 8              # 640x640
CLARO = (240, 217, 181)
OSCURO = (181, 136, 99)
# -------------------------

# Simbolos unicode de ajedrez
SIMBOLOS = {
    "?": "♜",  # Torre detectada cuyo color aún no se conoce (vista de imágenes).
    "t": "♜", "c": "♞", "a": "♝",
    "d": "♛", "r": "♚", "p": "♟",
    "T": "♖", "C": "♘", "A": "♗",
    "D": "♕", "R": "♔", "P": "♙",
}


def dibujar_tablero(pantalla):
    """Dibuja las 64 casillas alternando color."""
    for fila in range(8):
        for col in range(8):
            color = CLARO if (fila + col) % 2 == 0 else OSCURO
            rect = pygame.Rect(col * CASILLA, fila * CASILLA, CASILLA, CASILLA)
            pygame.draw.rect(pantalla, color, rect)


def dibujar_piezas(pantalla, fuente, posicion):
    """Dibuja cada pieza centrada en su casilla."""
    for fila in range(8):
        for col in range(8):
            pieza = posicion[fila][col]
            if pieza == "":
                continue
            neutra = pieza.startswith("?")
            simbolo = SIMBOLOS[pieza[1:].lower()] if neutra and len(pieza) > 1 else SIMBOLOS[pieza]
            color = (65, 85, 115) if neutra else ((255, 255, 255) if pieza.isupper() else (20, 20, 20))
            texto = fuente.render(simbolo, True, color)
            # Centrar dentro de la casilla
            x = col * CASILLA + (CASILLA - texto.get_width()) // 2
            y = fila * CASILLA + (CASILLA - texto.get_height()) // 2
            pantalla.blit(texto, (x, y))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Tablero conectado a observaciones externas")
    parser.add_argument("--entrada", type=Path,
                        default=OBSERVACION,
                        help="Archivo JSON publicado por el detector (por defecto datos/observacion.json)")
    parser.add_argument("--duracion", type=float, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    pygame.init()
    pantalla = pygame.display.set_mode((LADO, LADO + 120))
    pygame.display.set_caption("Ajedrez — seguimiento de movimientos")
    fuente = pygame.font.SysFont("segoeuisymbol,dejavusans", int(CASILLA * 0.7))
    fuente_info = pygame.font.SysFont("arial", 18)
    reloj = pygame.time.Clock()
    seguimiento = Seguimiento(reflejar_observaciones=True)
    entrada = EntradaArchivo(args.entrada)
    ultima_lectura = -1.0
    inicio = time.monotonic()
    corriendo = True
    try:
        while corriendo:
            ahora = time.monotonic()
            for evento in pygame.event.get():
                if evento.type == pygame.QUIT:
                    corriendo = False
                elif evento.type == pygame.KEYDOWN:
                    if evento.key == pygame.K_ESCAPE:
                        corriendo = False
                    elif evento.key == pygame.K_r:
                        # Resincronización explícita, nunca automática ante errores.
                        seguimiento = Seguimiento(reflejar_observaciones=True)
            if ahora - ultima_lectura >= 0.1:
                ultima_lectura = ahora
                try:
                    observacion = entrada.leer()
                    movimiento = seguimiento.recibir(observacion, ahora)
                    if movimiento:
                        print(movimiento.texto(), flush=True)
                except FileNotFoundError:
                    seguimiento.invalidar("Esperando datos del detector")
                except (OSError, ValueError, UnicodeError):
                    seguimiento.invalidar("Observación inválida o no disponible; posición conservada")
            seguimiento.comprobar_conexion(ahora)
            pantalla.fill((30, 30, 35))
            dibujar_tablero(pantalla)
            if seguimiento.posicion is not None:
                dibujar_piezas(pantalla, fuente, seguimiento.posicion)
            if seguimiento.ultimo_movimiento:
                ultimo = seguimiento.ultimo_movimiento
                for casilla in (ultimo.origen, ultimo.destino):
                    f, c = indices(casilla)
                    pygame.draw.rect(pantalla, (35, 125, 200), (c * CASILLA, f * CASILLA, CASILLA, CASILLA), 3)
            lineas = [
                "TABLERO A PARTIR DE DETECCIONES",
                seguimiento.estado,
                f"Movimientos confirmados: {len(seguimiento.historial)}",
                "R: resincronizar   Esc: salir",
            ]
            for i, linea in enumerate(lineas):
                pantalla.blit(fuente_info.render(linea, True, (240, 240, 240)), (10, LADO + 8 + i * 26))
            pygame.display.flip()
            reloj.tick(60)
            if args.duracion is not None and ahora - inicio >= args.duracion:
                corriendo = False
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
