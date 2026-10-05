"""Restricciones del prototipo compartidas por fotografía y vídeo."""

# Piezas de un juego estándar, sumando ambos colores. Una detección que
# supera el tope de su clase es casi seguro un error del modelo. Las
# promociones pueden romper estos topes (una tercera dama, por ejemplo);
# si se juegan, ajustar aquí.
LIMITES = {"R": 2, "D": 2, "T": 4, "A": 4, "C": 4, "P": 16}

# Tope por color. El rey es la única clase que ninguna partida legal
# puede exceder, ni siquiera con promociones.
LIMITES_POR_COLOR = {"R": 1}

NOMBRE_CLASE = {"R": "reyes", "D": "damas", "T": "torres",
                "A": "alfiles", "C": "caballos", "P": "peones"}

# Compatibilidad con el código que solo conocía el tope de torres.
MAX_TORRES = LIMITES["T"]

# Confianza del modelo bajo la cual una detección deja la casilla en duda
# en lugar de afirmarla. El detector debe filtrar por debajo de este valor
# para que esta regla tenga efecto (ver CONFIANZA_DETECTOR).
UMBRAL_DUDA = .5

# Umbral que se pasa a YOLO. Una pieza medio tapada produce detecciones de
# confianza baja: conservarlas permite que su casilla quede "desconocida"
# en esa vista (no "vacía") y que la otra cámara la confirme.
CONFIANZA_DETECTOR = .25


def tipo(codigo):
    """Clase sin color: 'T', 't' y '?T' son todos torre."""
    return codigo.lstrip("?").upper() if codigo else ""


def color(codigo):
    """'B' para blancas, 'N' para negras, '' si el color no está resuelto."""
    if not codigo or codigo.startswith("?"):
        return ""
    return "B" if codigo.isupper() else "N"


def excedentes(piezas, prioridad):
    """Casillas que sobran según LIMITES y LIMITES_POR_COLOR.

    piezas: iterable de (clave, codigo). prioridad(clave) devuelve una tupla
    ordenable: las claves con menor prioridad se conservan primero. Devuelve
    {clave: motivo} con las que superan algún tope.
    """
    ordenadas = sorted(piezas, key=lambda p: prioridad(p[0]))
    por_clase, por_color, sobran = {}, {}, {}
    for clave, codigo in ordenadas:
        clase, col = tipo(codigo), color(codigo)
        if clase not in LIMITES:
            continue
        tope_color = LIMITES_POR_COLOR.get(clase)
        if por_clase.get(clase, 0) >= LIMITES[clase]:
            sobran[clave] = f"Límite de {LIMITES[clase]} {NOMBRE_CLASE[clase]}"
            continue
        if tope_color is not None and col and por_color.get((clase, col), 0) >= tope_color:
            sobran[clave] = f"Límite por color de {NOMBRE_CLASE[clase]} ({tope_color})"
            continue
        por_clase[clase] = por_clase.get(clase, 0) + 1
        if col:
            por_color[clase, col] = por_color.get((clase, col), 0) + 1
    return sobran
