"""Geometría y observaciones de vídeo. No abre cámaras ni ventanas."""
import cv2
import numpy as np

from chess_simulator.seguimiento import Observacion, nombre
from chess_simulator.reglas_deteccion import MAX_TORRES
from chess_simulator.color_hsv import clasificar

CLASES = {"TOWER": "T", "HORSE": "C", "BISHOP": "A", "QUEEN": "D", "KING": "R", "PAWN": "P"}


def homografia(esquinas):
    puntos = np.asarray(esquinas, np.float32)
    if puntos.shape != (4, 2) or not np.isfinite(puntos).all():
        raise ValueError("Se necesitan cuatro vértices válidos")
    if not cv2.isContourConvex(puntos.reshape(-1, 1, 2)) or abs(cv2.contourArea(puntos)) < 100:
        raise ValueError("Vértices cruzados o demasiado próximos; pulse R")
    return cv2.getPerspectiveTransform(puntos, np.float32([[0, 0], [8, 0], [8, 8], [0, 8]]))


def extraer(resultado, frame, punto="base", parametros_hsv=None):
    """Tipo por segmentación y color HSV sobre el interior de cada silueta."""
    detecciones = []
    if resultado.masks is None:
        return detecciones
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    for i, poligono in enumerate(resultado.masks.xy):
        clase = resultado.names[int(resultado.boxes.cls[i])]
        codigo = CLASES.get(clase)
        if codigo is None:
            continue
        poligono = np.asarray(poligono, np.int32)
        x, y, w, h = cv2.boundingRect(poligono)
        x, y = max(0, x), max(0, y)
        roi = frame[y:y+h, x:x+w]
        if roi.size == 0:
            continue
        mascara = np.zeros(roi.shape[:2], np.uint8)
        cv2.fillPoly(mascara, [poligono - (x, y)], 255)
        ys, xs = np.where(mascara > 0)
        if len(xs) < 20:
            continue
        if punto == "centro":
            apoyo = (x + float(xs.mean()), y + float(ys.mean()))
        else:
            # Centro de la banda inferior, aproximación al apoyo de la pieza.
            bajos = ys >= np.quantile(ys, .8)
            apoyo = (x + float(np.median(xs[bajos])), y + float(np.median(ys[bajos])))
        detecciones.append({"pieza": codigo, "punto": apoyo,
                            "poligono": poligono,
                            "conf": float(resultado.boxes.conf[i]),
                            **clasificar(hsv, poligono, **(parametros_hsv or {}))})
    return detecciones


def construir_observacion(detecciones, esquinas, secuencia):
    matriz = homografia(esquinas)
    piezas, por_casilla = [], {}
    vista = [[""] * 8 for _ in range(8)]
    razones, puntos, desconocidas, confianzas = [], [], [], {}
    for d in detecciones:
        x, y = cv2.perspectiveTransform(np.float32(d["punto"]).reshape(1, 1, 2), matriz)[0, 0]
        if not np.isfinite([x, y]).all() or not (0 <= x < 8 and 0 <= y < 8):
            continue
        col, fila = int(x), int(y)
        puntos.append((d, nombre(fila, col)))
        por_casilla.setdefault((fila, col), []).append((d, float(x), float(y)))
    for (fila, col), candidatas in por_casilla.items():
        candidatas.sort(key=lambda v: (-v[0]["conf"], v[0]["pieza"], v[1], v[2]))
        mejor, x, y = candidatas[0]
        razon = None
        if mejor.get("color") == "DUDOSA":
            razon = "Color dudoso"
        if mejor["conf"] < .5:
            razon = "Baja confianza"
        for otra, xo, yo in candidatas[1:]:
            cerca = np.hypot(x-xo, y-yo) <= .2
            # Duplicados prácticamente en el mismo apoyo: mismo tipo, o una
            # clasificación claramente superior. No trasladar sobrantes a
            # casillas vecinas ni escoger arbitrariamente entre dos apoyos.
            duplicada = cerca and ((otra["pieza"] == mejor["pieza"] and otra.get("color") == mejor.get("color")) or mejor["conf"]-otra["conf"] >= .15)
            if not duplicada:
                razon = "Detecciones en conflicto"
        if razon:
            casilla = nombre(fila, col)
            desconocidas.append(casilla)
            razones.append(f"{razon} en {casilla}")
            continue
        color = mejor.get("color")
        codigo = (mejor["pieza"] if color == "BLANCA" else
                  mejor["pieza"].lower() if color == "NEGRA" else "?" + mejor["pieza"])
        vista[fila][col] = codigo
        piezas.append({"casilla": nombre(fila, col), "pieza": codigo})
        confianzas[nombre(fila, col)] = mejor["conf"]
    # Aplicar después de agrupar por casilla: duplicados de una misma torre no
    # deben consumir varias plazas, ni deben hacerlo detecciones fuera del tablero.
    torres = sorted((p for p in piezas if p["pieza"] in ("?T", "T", "t")),
                    key=lambda p: (-confianzas[p["casilla"]], p["casilla"]))
    excedentes = {p["casilla"] for p in torres[MAX_TORRES:]}
    if excedentes:
        piezas = [p for p in piezas if p["casilla"] not in excedentes]
        for casilla in sorted(excedentes):
            fila, col = 8-int(casilla[1]), ord(casilla[0])-ord("a")
            vista[fila][col] = ""
            confianzas.pop(casilla)
            desconocidas.append(casilla)
            razones.append(f"Límite de {MAX_TORRES} torres: detección descartada en {casilla}")
    obs = Observacion.desde_dict({"secuencia": secuencia, "completa": not desconocidas,
                                 "desconocidas": desconocidas,
                                 "confianza": min(confianzas.values(), default=1),
                                 "confianzas": confianzas,
                                 "piezas": piezas})
    return obs, vista, puntos, razones


class FiltroEscena:
    """Rechaza frames con cambios grandes: mano/movimiento, no identifica manos."""
    def __init__(self):
        self.anterior = None

    def estable(self, frame, esquinas):
        h = homografia(esquinas)
        h = np.diag([20., 20., 1.]) @ h
        gris = cv2.cvtColor(cv2.warpPerspective(frame, h, (160, 160)), cv2.COLOR_BGR2GRAY)
        gris = cv2.GaussianBlur(gris, (5, 5), 0)
        previo, self.anterior = self.anterior, gris
        if previo is None:
            return False
        return float(np.mean(cv2.absdiff(previo, gris) > 25)) < .035
