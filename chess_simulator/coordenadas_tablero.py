"""Referencia planar del tablero: origen a8, X hacia h8, Y hacia a1."""
from dataclasses import dataclass
import math

EJES = {"origen": "a8", "x": "h8", "y": "a1"}


@dataclass(frozen=True)
class TableroFisico:
    identificador: str
    ancho_m: float
    alto_m: float

    def __post_init__(self):
        if not isinstance(self.identificador, str) or not self.identificador.strip():
            raise ValueError("El tablero necesita un identificador")
        for valor in (self.ancho_m, self.alto_m):
            if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor) or valor <= 0:
                raise ValueError("Ancho y alto deben ser números positivos finitos en metros")

    def a_metros(self, x, y):
        """Acepta los bordes exteriores 0 y 8; nunca recorta puntos exteriores."""
        if not all(math.isfinite(v) and 0 <= v <= 8 for v in (x, y)):
            raise ValueError("Punto fuera del tablero o no finito")
        return x * self.ancho_m / 8, y * self.alto_m / 8

    def centro(self, casilla):
        if not isinstance(casilla, str) or len(casilla) != 2 or casilla[0] not in "abcdefgh" or casilla[1] not in "12345678":
            raise ValueError("Casilla inválida; use a1…h8")
        return self.a_metros(ord(casilla[0])-97+.5, 8-int(casilla[1])+.5)

    def a_dict(self):
        return {"identificador": self.identificador, "ancho_m": self.ancho_m,
                "alto_m": self.alto_m, "ejes": dict(EJES)}

    @classmethod
    def desde_dict(cls, datos):
        if not isinstance(datos, dict) or datos.get("ejes") != EJES:
            raise ValueError("Convención requerida: origen a8, X hacia h8, Y hacia a1")
        try:
            return cls(datos["identificador"], datos["ancho_m"], datos["alto_m"])
        except KeyError as error:
            raise ValueError(f"Falta un campo del tablero: {error}") from error
