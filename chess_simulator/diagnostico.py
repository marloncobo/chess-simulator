"""Diagnóstico por casilla de la fusión de dos vistas.

Responde la pregunta que el tablero combinado no contesta: por qué una
casilla quedó como quedó, y qué aporta cada cámara.

Se calcula a partir de las dos observaciones por vista más el resultado
fusionado, sin tocar fusionar(): solo hay que conservar las
observaciones en la sesión.

ESTADOS
-------
    AMBAS       las dos cámaras ven la misma pieza. Máxima fiabilidad.
    RESCATE_1   solo la cámara 1 la ve; la 2 la tiene tapada.
    RESCATE_2   solo la cámara 2 la ve; la 1 la tiene tapada.
                Estos dos son la razón de ser del montaje: miden
                cuánto aporta realmente la segunda cámara.
    SOLO_1      la cámara 1 ve pieza y la 2 dice VACÍA con fiabilidad.
    SOLO_2      lo mismo al revés.
                fusionar() acepta estos casos ("una evidencia positiva
                basta"), pero una cámara afirmó que no hay nada. Son
                los candidatos número uno a falso positivo.
    CONFLICTO   las dos ven pieza pero discrepan en tipo o color.
    CIEGAS      las dos la tienen tapada. Sin información.
    VACIA       las dos coinciden en que está vacía.
"""
from collections import Counter

from chess_simulator.seguimiento import nombre

# Piezas de un juego estándar. Las promociones alteran el reparto pero
# nunca el total, así que un exceso por clase señala un error probable.
ESPERADAS = {"R": 2, "D": 2, "T": 4, "A": 4, "C": 4, "P": 16}

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

    'pieza' es lo que quedó confirmado tras fusionar (vacío si nada).
    'v1' y 'v2' son lo que vio cada cámara, para poder compararlas.
    """
    if len(observaciones) != 2:
        raise ValueError("Se requieren exactamente dos observaciones")
    o1, o2 = observaciones
    casillas = {}

    for f in range(8):
        for c in range(8):
            tapada1 = (f, c) in o1.desconocidas
            tapada2 = (f, c) in o2.desconocidas
            p1 = "" if tapada1 else o1.tablero[f][c]
            p2 = "" if tapada2 else o2.tablero[f][c]

            if p1 and p2:
                estado = AMBAS if p1 == p2 else CONFLICTO
                detalle = "" if p1 == p2 else f"vista 1 dice {p1}, vista 2 dice {p2}"
            elif p1:
                estado = RESCATE_1 if tapada2 else SOLO_1
                detalle = ("la vista 2 la tiene tapada" if tapada2
                           else "la vista 2 dice que esta vacia")
            elif p2:
                estado = RESCATE_2 if tapada1 else SOLO_2
                detalle = ("la vista 1 la tiene tapada" if tapada1
                           else "la vista 1 dice que esta vacia")
            elif tapada1 and tapada2:
                estado, detalle = CIEGAS, "tapada en las dos vistas"
            elif tapada1 or tapada2:
                # Una la tapa, la otra la ve vacía: sin evidencia positiva
                estado = CIEGAS
                detalle = f"tapada en la vista {1 if tapada1 else 2}"
            else:
                estado, detalle = VACIA, ""

            confirmada = fusion.tablero[f][c] if fusion else ""
            casillas[(f, c)] = {"estado": estado, "pieza": confirmada,
                                "v1": o1.tablero[f][c], "v2": o2.tablero[f][c],
                                "tapada1": tapada1, "tapada2": tapada2,
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
    Cuántas piezas existen en el tablero gracias a cada cámara.

    Es la medida directa de si el montaje de dos cámaras sirve: si
    ambos números son cero, las dos ven lo mismo y la segunda no
    está aportando nada.
    """
    r = resumen(casillas)
    return r.get(RESCATE_1, 0), r.get(RESCATE_2, 0), r.get(AMBAS, 0)
