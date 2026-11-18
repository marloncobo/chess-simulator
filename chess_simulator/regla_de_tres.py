"""Conversión lineal experimental para un tablero alineado con la imagen."""
from dataclasses import dataclass
import math

from chess_simulator.coordenadas_tablero import TableroFisico


def centimetros_a_metros(x, y):
    return x / 100, y / 100


@dataclass(frozen=True)
class EscalaTablero:
    origen: tuple
    # Proyecciones en píxeles: superior, inferior, izquierdo, derecho.
    lados: tuple
    tablero: TableroFisico

    @property
    def px_por_cm(self):
        superior, inferior, izquierdo, derecho = self.lados
        return ((superior + inferior) / (200 * self.tablero.ancho_m),
                (izquierdo + derecho) / (200 * self.tablero.alto_m))

    @property
    def cm_por_px(self):
        sx, sy = self.px_por_cm
        return 1 / sx, 1 / sy

    def pixeles_a_cm(self, x, y):
        sx, sy = self.px_por_cm
        return (x - self.origen[0]) / sx, (y - self.origen[1]) / sy

    def casilla(self, x_cm, y_cm):
        ancho, alto = self.tablero.ancho_m * 100, self.tablero.alto_m * 100
        if not (0 <= x_cm <= ancho and 0 <= y_cm <= alto):
            return None
        columna = min(7, int(8 * x_cm / ancho))
        fila = min(7, int(8 * y_cm / alto))
        return f"{'abcdefgh'[columna]}{8 - fila}"

    def centro_cm(self, casilla):
        x, y = self.tablero.centro(casilla)
        return x * 100, y * 100


def calibrar(esquinas, ancho_cm=40, alto_cm=40):
    tablero = TableroFisico("regla-de-tres", *centimetros_a_metros(ancho_cm, alto_cm))
    a, b, c, d = esquinas
    lados = b[0]-a[0], c[0]-d[0], d[1]-a[1], c[1]-b[1]
    if not all(math.isfinite(v) and v > 0 for v in lados):
        raise ValueError("Revise el orden de las esquinas: a8, h8, h1, a1.")
    for p, q, r in ((a,b,c), (b,c,d), (c,d,a), (d,a,b)):
        if (q[0]-p[0])*(r[1]-q[1]) <= (q[1]-p[1])*(r[0]-q[0]):
            raise ValueError("Las cuatro esquinas deben formar un tablero convexo.")
    return EscalaTablero(tuple(a), lados, tablero)
