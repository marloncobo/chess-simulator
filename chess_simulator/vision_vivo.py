"""Geometría y observaciones de vídeo. No abre cámaras ni ventanas."""
import cv2
import numpy as np

from chess_simulator.seguimiento import Observacion, nombre
from chess_simulator.reglas_deteccion import UMBRAL_DUDA, excedentes
from chess_simulator.color_hsv import clasificar

CLASES = {"TOWER": "T", "HORSE": "C", "BISHOP": "A", "QUEEN": "D", "KING": "R", "PAWN": "P"}


def homografia(esquinas):
    puntos = np.asarray(esquinas, np.float32)
    if puntos.shape != (4, 2) or not np.isfinite(puntos).all():
        raise ValueError("Se necesitan cuatro vértices válidos")
    if not cv2.isContourConvex(puntos.reshape(-1, 1, 2)) or abs(cv2.contourArea(puntos)) < 100:
        raise ValueError("Vértices cruzados o demasiado próximos; pulse R")
    return cv2.getPerspectiveTransform(puntos, np.float32([[0, 0], [8, 0], [8, 8], [0, 8]]))


def _base(mascara, x, y, alto_frame, fraccion=.1):
    """Frente y ancho de la base en la imagen, para estimar el apoyo en el plano.

    La fila más baja de la silueta es el borde DELANTERO de la base, no su
    centro: el centro está detrás, a un radio de distancia. Aquí solo se
    toman las medidas en píxeles; apoyo_tablero hace la corrección sobre el
    plano, donde el radio se puede medir sin conocer el ángulo de la cámara.
    """
    filas = np.flatnonzero(mascara.any(axis=1))
    if not len(filas):
        return None
    abajo = int(filas[-1])
    if y + abajo >= alto_frame - 2:
        return None  # Silueta cortada por el borde inferior: no hay frente fiable.
    banda = max(2, int((abajo - filas[0] + 1) * fraccion))
    anchos = (mascara[abajo-banda:abajo+1] > 0).sum(axis=1)
    fila = abajo - banda + int(np.argmax(anchos))
    cols = np.flatnonzero(mascara[fila] > 0)
    if len(cols) < 2:
        return None
    return {"frente": (x + (cols[0] + cols[-1]) / 2, y + abajo + .5),
            "izq": (x + float(cols[0]), y + fila + .5),
            "der": (x + float(cols[-1]) + 1, y + fila + .5)}


def apoyo_tablero(d, matriz):
    """Punto de apoyo de una detección en coordenadas del tablero (casillas).

    Con la base medida: se proyecta el frente al plano y se retrocede, en la
    dirección que se aleja de la cámara, medio ancho de base. Medido sobre dos
    fotos reales (57 piezas) y con cámaras sintéticas de 25° a 70°, este
    estimador queda a menos de 0.16 casillas del centro real, frente a 0.25-0.30
    del cuantil 0.8/0.9. Sin base (pruebas, silueta cortada) usa d["punto"].
    """
    base = d.get("base")
    if base:
        frente = np.float32(base["frente"])
        puntos = np.float32([base["izq"], base["der"], frente, frente + (0, 10)])
        p = cv2.perspectiveTransform(puntos.reshape(-1, 1, 2), matriz).reshape(-1, 2)
        if np.isfinite(p).all():
            atras = p[2] - p[3]
            largo = float(np.linalg.norm(atras))
            if largo > 1e-9:
                radio = float(np.clip(np.linalg.norm(p[1] - p[0]) / 2, .05, .5))
                x, y = p[2] + atras / largo * radio
                return float(x), float(y)
    x, y = cv2.perspectiveTransform(np.float32(d["punto"]).reshape(1, 1, 2), matriz)[0, 0]
    return float(x), float(y)


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
        base = None
        if punto == "centro":
            apoyo = (x + float(xs.mean()), y + float(ys.mean()))
        else:
            # Centro de la banda inferior; solo se usa si no hay base medida.
            bajos = ys >= np.quantile(ys, .8)
            apoyo = (x + float(np.median(xs[bajos])), y + float(np.median(ys[bajos])))
            base = _base(mascara, x, y, frame.shape[0])
        detecciones.append({"pieza": codigo, "punto": apoyo, "base": base,
                            "poligono": poligono,
                            "conf": float(resultado.boxes.conf[i]),
                            **clasificar(hsv, poligono, **(parametros_hsv or {}))})
    return detecciones


def separar_razon(razon):
    """'Color dudoso + Baja confianza en e4' -> (['Color dudoso', 'Baja confianza'], 'e4')."""
    causas, _, casilla = razon.rpartition(" en ")
    return [c for c in causas.split(" + ") if c], casilla


def construir_observacion(detecciones, esquinas, secuencia):
    matriz = homografia(esquinas)
    piezas, por_casilla = [], {}
    vista = [[""] * 8 for _ in range(8)]
    razones, puntos, desconocidas, confianzas = [], [], [], {}
    for d in detecciones:
        x, y = apoyo_tablero(d, matriz)
        if not np.isfinite([x, y]).all() or not (0 <= x < 8 and 0 <= y < 8):
            continue
        col, fila = int(x), int(y)
        puntos.append((d, nombre(fila, col)))
        por_casilla.setdefault((fila, col), []).append((d, float(x), float(y)))
    for (fila, col), candidatas in por_casilla.items():
        candidatas.sort(key=lambda v: (-v[0]["conf"], v[0]["pieza"], v[1], v[2]))
        mejor, x, y = candidatas[0]
        # Se acumulan todos los motivos: el diagnóstico necesita saber, por
        # ejemplo, que el color era dudoso aunque la confianza también fuera baja.
        motivos = []
        if mejor.get("color") == "DUDOSA":
            motivos.append("Color dudoso")
        if mejor["conf"] < UMBRAL_DUDA:
            motivos.append("Baja confianza")
        for otra, xo, yo in candidatas[1:]:
            if otra["conf"] < UMBRAL_DUDA <= mejor["conf"]:
                # Con el detector en CONFIANZA_DETECTOR aparecen segundas lecturas
                # débiles de la misma silueta (rey .96 y rey .38 a 0.24 casillas).
                # No pueden afirmar nada: no deben anular a la detección firme.
                continue
            cerca = np.hypot(x-xo, y-yo) <= .2
            # Duplicados prácticamente en el mismo apoyo: mismo tipo, o una
            # clasificación claramente superior. No trasladar sobrantes a
            # casillas vecinas ni escoger arbitrariamente entre dos apoyos.
            duplicada = cerca and ((otra["pieza"] == mejor["pieza"] and otra.get("color") == mejor.get("color")) or mejor["conf"]-otra["conf"] >= .15)
            if not duplicada:
                motivos.append("Detecciones en conflicto")
                break
        if motivos:
            casilla = nombre(fila, col)
            desconocidas.append(casilla)
            razones.append(f"{' + '.join(motivos)} en {casilla}")
            continue
        color = mejor.get("color")
        codigo = (mejor["pieza"] if color == "BLANCA" else
                  mejor["pieza"].lower() if color == "NEGRA" else "?" + mejor["pieza"])
        vista[fila][col] = codigo
        piezas.append({"casilla": nombre(fila, col), "pieza": codigo})
        confianzas[nombre(fila, col)] = mejor["conf"]
    # Aplicar después de agrupar por casilla: duplicados de una misma pieza no
    # deben consumir varias plazas, ni deben hacerlo detecciones fuera del tablero.
    sobran = excedentes(((p["casilla"], p["pieza"]) for p in piezas),
                        lambda casilla: (-confianzas[casilla], casilla))
    if sobran:
        piezas = [p for p in piezas if p["casilla"] not in sobran]
        for casilla in sorted(sobran):
            fila, col = 8-int(casilla[1]), ord(casilla[0])-ord("a")
            vista[fila][col] = ""
            confianzas.pop(casilla)
            desconocidas.append(casilla)
            razones.append(f"{sobran[casilla]}: detección descartada en {casilla}")
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
