"""Diagnóstico por casilla de la fusión de dos vistas.

Responde la pregunta que el tablero combinado no contesta: por qué una
casilla quedó como quedó, y qué aporta cada cámara.

Se calcula a partir de las dos observaciones por vista más el resultado
fusionado, sin tocar fusionar(): solo hay que conservar las
observaciones en la sesión.

ESTADOS
-------
    AMBAS       las dos cámaras proponen la misma pieza; no mide exactitud real.
    RESCATE_1   solo la cámara 1 la ve; la 2 la tiene tapada.
    RESCATE_2   solo la cámara 2 la ve; la 1 la tiene tapada.
                Estos dos son la razón de ser del montaje: miden
                cuánto aporta realmente la segunda cámara.
    SOLO_1      la cámara 1 ve pieza y la 2 no aporta evidencia positiva.
    SOLO_2      lo mismo al revés.
                Requieren mayor confianza y confirmación temporal. El detalle
                distingue ausencia de incertidumbre de color, fondo o movimiento.
    CONFLICTO   las dos ven pieza pero discrepan en tipo o color.
    CIEGAS      información insuficiente; ver motivo por cámara.
    VACIA       las dos coinciden en que está vacía.
"""
from collections import Counter

from chess_simulator.reglas_deteccion import LIMITES
from chess_simulator.seguimiento import nombre

# Piezas de un juego estándar. Las promociones alteran el reparto pero
# nunca el total, así que un exceso por clase señala un error probable.
ESPERADAS = LIMITES

NOMBRE_CLASE = {"R": "rey", "D": "dama", "T": "torre",
                "A": "alfil", "C": "caballo", "P": "peon"}

AMBAS, RESCATE_1, RESCATE_2 = "AMBAS", "RESCATE_1", "RESCATE_2"
SOLO_1, SOLO_2, CONFLICTO = "SOLO_1", "SOLO_2", "CONFLICTO"
CIEGAS, VACIA = "CIEGAS", "VACIA"

# Los que merecen mirarse con lupa
PROBLEMATICOS = (CONFLICTO, SOLO_1, SOLO_2, CIEGAS)


def _tipo(codigo):
    """Clase de pieza sin color: 'T', 't' y '?T' son todos torre."""
    return codigo.lstrip("?").upper() if codigo else ""


def diagnosticar(observaciones, fusion=None):
    """
    Devuelve {(fila, col): {"estado":, "pieza":, "v1":, "v2":, "detalle":}}

    'pieza' es la propuesta fusionada, aún pendiente de confirmación temporal.
    'v1' y 'v2' son lo que vio cada cámara, para poder compararlas.
    """
    if len(observaciones) != 2:
        raise ValueError("Se requieren exactamente dos observaciones")
    o1, o2 = observaciones
    casillas = {}

    for f in range(8):
        for c in range(8):
            dudosa1 = (f, c) in o1.desconocidas
            dudosa2 = (f, c) in o2.desconocidas
            motivo1 = getattr(o1, "motivos", {}).get((f, c), "Duda sin clasificar" if dudosa1 else "")
            motivo2 = getattr(o2, "motivos", {}).get((f, c), "Duda sin clasificar" if dudosa2 else "")
            # Los motivos se acumulan ("Baja confianza + Oclusion por silueta"):
            # basta con que la oclusión sea uno de ellos.
            tapada1 = "Oclusion por silueta" in motivo1.split(" + ")
            tapada2 = "Oclusion por silueta" in motivo2.split(" + ")
            p1 = "" if dudosa1 else o1.tablero[f][c]
            p2 = "" if dudosa2 else o2.tablero[f][c]

            if p1 and p2:
                estado = AMBAS if p1 == p2 else CONFLICTO
                detalle = "" if p1 == p2 else f"vista 1 dice {p1}, vista 2 dice {p2}"
            elif p1:
                estado = RESCATE_1 if tapada2 else SOLO_1
                detalle = (f"vista 2: {motivo2}" if dudosa2
                           else "vista 2: ausencia; confirmar deteccion unilateral")
            elif p2:
                estado = RESCATE_2 if tapada1 else SOLO_2
                detalle = (f"vista 1: {motivo1}" if dudosa1
                           else "vista 1: ausencia; confirmar deteccion unilateral")
            elif dudosa1 or dudosa2:
                estado = CIEGAS
                detalle = " / ".join(f"v{i}: {m}" for i, m in ((1, motivo1), (2, motivo2)) if m)
            else:
                estado, detalle = VACIA, ""

            confirmada = fusion.tablero[f][c] if fusion else ""
            if fusion and (f, c) in fusion.desconocidas and (p1 or p2) and estado != CONFLICTO:
                motivo = getattr(fusion, "motivos", {}).get((f, c), "confianza o posicion")
                detalle += f"; pendiente: {motivo}"
            casillas[(f, c)] = {"estado": estado, "pieza": confirmada,
                                "v1": o1.tablero[f][c], "v2": o2.tablero[f][c],
                                "tapada1": tapada1, "tapada2": tapada2,
                                "motivo1": motivo1, "motivo2": motivo2,
                                "detalle": detalle}
    return casillas


def contar_clases(tablero):
    """Piezas por clase frente a las de un juego estándar."""
    conteo = Counter()
    for fila in tablero or ():
        for pieza in fila:
            if pieza:
                conteo[_tipo(pieza)] += 1

    filas = []
    for clase, tope in ESPERADAS.items():
        n = conteo.get(clase, 0)
        filas.append({"clase": clase, "nombre": NOMBRE_CLASE[clase],
                      "n": n, "esperadas": tope,
                      "exceso": max(0, n - tope),
                      "faltan": max(0, tope - n) if clase == "R" else 0})
    return filas, sum(conteo.values())


def resumen(casillas):
    """Cuántas casillas hay en cada estado."""
    return Counter(d["estado"] for d in casillas.values())


def problemas(casillas, limite=8):
    """
    Las casillas que conviene revisar, de más grave a menos.

    Un conflicto es peor que un solo-ve-una, y ese es peor que una
    ciega: el conflicto significa que el modelo se contradice.
    """
    orden = {CONFLICTO: 0, SOLO_1: 1, SOLO_2: 1, CIEGAS: 2}
    encontradas = [(orden[d["estado"]], nombre(f, c), d)
                   for (f, c), d in casillas.items()
                   if d["estado"] in PROBLEMATICOS]
    encontradas.sort(key=lambda t: (t[0], t[1]))
    return [(casilla, d) for _, casilla, d in encontradas[:limite]], len(encontradas)


def aporte_segunda_camara(casillas):
    """
    Propuestas exclusivas con oclusión estimada en la otra vista y coincidencias.
    Son contadores de evidencia, no una medición de precisión ni de piezas
    reales recuperadas: eso requiere compararlas con un tablero etiquetado.
    """
    r = resumen(casillas)
    return r.get(RESCATE_1, 0), r.get(RESCATE_2, 0), r.get(AMBAS, 0)
