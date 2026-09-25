import pygame

# ----- CONFIGURACION -----
CASILLA = 80                    # pixeles por casilla
LADO = CASILLA * 8              # 640x640
CLARO = (240, 217, 181)
OSCURO = (181, 136, 99)
# -------------------------

# Posicion inicial estandar.
# Mayuscula = blancas, minuscula = negras.
# t=torre  c=caballo  a=alfil  d=dama  r=rey  p=peon
POSICION_INICIAL = [
    ["t", "c", "a", "d", "r", "a", "c", "t"],   # fila 0  (negras)
    ["p", "p", "p", "p", "p", "p", "p", "p"],   # fila 1
    ["",  "",  "",  "",  "",  "",  "",  ""],
    ["",  "",  "",  "",  "",  "",  "",  ""],
    ["",  "",  "",  "",  "",  "",  "",  ""],
    ["",  "",  "",  "",  "",  "",  "",  ""],
    ["P", "P", "P", "P", "P", "P", "P", "P"],   # fila 6
    ["T", "C", "A", "D", "R", "A", "C", "T"],   # fila 7  (blancas)
]

# Simbolos unicode de ajedrez
SIMBOLOS = {
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
            simbolo = SIMBOLOS[pieza]
            color = (255, 255, 255) if pieza.isupper() else (20, 20, 20)
            texto = fuente.render(simbolo, True, color)
            # Centrar dentro de la casilla
            x = col * CASILLA + (CASILLA - texto.get_width()) // 2
            y = fila * CASILLA + (CASILLA - texto.get_height()) // 2
            pantalla.blit(texto, (x, y))


def main():
    pygame.init()
    pantalla = pygame.display.set_mode((LADO, LADO))
    pygame.display.set_caption("Tablero de ajedrez")

    # DejaVu Sans trae los simbolos de ajedrez en Ubuntu
    fuente = pygame.font.SysFont("dejavusans", int(CASILLA * 0.7))

    corriendo = True
    while corriendo:
        for evento in pygame.event.get():
            if evento.type == pygame.QUIT:
                corriendo = False
            elif evento.type == pygame.KEYDOWN and evento.key == pygame.K_ESCAPE:
                corriendo = False

        dibujar_tablero(pantalla)
        dibujar_piezas(pantalla, fuente, POSICION_INICIAL)
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()