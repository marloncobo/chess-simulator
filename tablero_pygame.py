import pygame

# ----- CONFIGURACION -----
CASILLA = 80                    # pixeles por casilla
LADO = CASILLA * 8              # 640x640
CLARO = (240, 217, 181)
OSCURO = (181, 136, 99)
BORDE = (60, 40, 25)
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
    "t": "\u265C", "c": "\u265E", "a": "\u265D",
    "d": "\u265B", "r": "\u265A", "p": "\u265F",
    "T": "\u2656", "C": "\u2658", "A": "\u2657",
    "D": "\u2655", "R": "\u2654", "P": "\u2659",
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


def centro_casilla(fila, col):
    """Devuelve la coordenada (x, y) del centro de una casilla."""
    return (col * CASILLA + CASILLA // 2, fila * CASILLA + CASILLA // 2)


def main():
    pygame.init()
    pantalla = pygame.display.set_mode((LADO, LADO))
    pygame.display.set_caption("Tablero de ajedrez")

    # DejaVu Sans trae los simbolos de ajedrez en Ubuntu
    fuente = pygame.font.SysFont("dejavusans", int(CASILLA * 0.7))

    # Coordenadas de las 4 torres en la posicion inicial
    print("Centros de las 4 torres en el tablero digital:")
    for fila, col in [(0, 0), (0, 7), (7, 0), (7, 7)]:
        pieza = POSICION_INICIAL[fila][col]
        print(f"  fila {fila}, col {col}  ->  {centro_casilla(fila, col)}  ({pieza})")

    corriendo = True
    while corriendo:
        for evento in pygame.event.get():
            if evento.type == pygame.QUIT:
                corriendo = False
            elif evento.type == pygame.KEYDOWN and evento.key == pygame.K_ESCAPE:
                corriendo = False
            elif evento.type == pygame.MOUSEBUTTONDOWN:
                # Click: muestra en que casilla caiste
                mx, my = evento.pos
                col, fila = mx // CASILLA, my // CASILLA
                letra = "abcdefgh"[col]
                numero = 8 - fila
                print(f"Click en {letra}{numero}  (fila {fila}, col {col})")

        dibujar_tablero(pantalla)
        dibujar_piezas(pantalla, fuente, POSICION_INICIAL)
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
