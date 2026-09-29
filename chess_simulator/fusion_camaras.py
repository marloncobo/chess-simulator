"""Fusión conservadora de dos vistas en coordenadas del tablero."""
import cv2
import numpy as np
from dataclasses import dataclass, field

from chess_simulator.seguimiento import Observacion, nombre
from chess_simulator.vision_vivo import construir_observacion, homografia


@dataclass(frozen=True)
class Vista(Observacion):
    motivos: dict = field(default_factory=dict)
    apoyos: dict = field(default_factory=dict)


def con_dudas(obs, motivos, apoyos=None):
    tablero = [list(f) for f in obs.tablero]
    confianzas = [list(f) for f in obs.confianzas]
    for f, c in motivos:
        tablero[f][c] = ""
        confianzas[f][c] = 0.
    return Vista(obs.secuencia, tuple(map(tuple, tablero)), not motivos, obs.confianza,
                 frozenset(motivos), tuple(map(tuple, confianzas)), motivos, apoyos or {})


class FiltroCasillas:
    """Movimiento local y comprobación de fondo vacío, sin identificar manos.

    Aprende el color de casillas vacías uniformes por paridad. Una ausencia
    cuya apariencia no coincide se conserva como incierta incluso inmóvil.
    Las referencias se reinician al recalibrar, no al desaparecer una pieza.
    """
    def __init__(self):
        self.anterior = None
        self.hasta = np.zeros((8, 8))
        self.fondo = {}
        self.imagen = None

    def evaluar(self, frame, esquinas, ahora):
        matriz = np.diag([20., 20., 1.]) @ homografia(esquinas)
        self.imagen = cv2.cvtColor(cv2.warpPerspective(frame, matriz, (160, 160)), cv2.COLOR_BGR2LAB)
        if self.anterior is None:
            self.hasta[:] = ahora + .6
        else:
            diferencia = np.max(np.abs(self.imagen.astype(float)-self.anterior.astype(float)), axis=2) > 25
            for f in range(8):
                for c in range(8):
                    if diferencia[f*20:(f+1)*20, c*20:(c+1)*20].mean() > .08:
                        self.hasta[f, c] = ahora + .8
        self.anterior = self.imagen.copy()
        return {(f, c) for f in range(8) for c in range(8) if ahora < self.hasta[f, c]}

    def verificar_vacios(self, vista):
        motivos = dict(vista.motivos)
        medidas, muestras = {}, {0: [], 1: []}
        for f in range(8):
            for c in range(8):
                if vista.tablero[f][c] or (f, c) in vista.desconocidas:
                    continue
                pixeles = self.imagen[f*20+4:f*20+16, c*20+4:c*20+16].reshape(-1, 3).astype(float)
                color = np.median(pixeles, axis=0)
                dispersion = np.percentile(np.linalg.norm(pixeles-color, axis=1), 90)
                medidas[f, c] = (color, dispersion)
                if dispersion < 25:
                    muestras[(f+c)%2].append(color)
        for paridad, colores in muestras.items():
            if paridad not in self.fondo and len(colores) >= 3:
                centro = np.median(colores, axis=0)
                cercanos = [p for p in colores if np.linalg.norm(p-centro) < 25]
                if len(cercanos) >= 3:
                    self.fondo[paridad] = np.median(cercanos, axis=0)
        for (f, c), (color, dispersion) in medidas.items():
            fondo = self.fondo.get((f+c)%2)
            if fondo is None or dispersion >= 25 or np.linalg.norm(color-fondo) >= 35:
                motivos[f, c] = "Fondo no verificable"
        return con_dudas(vista, motivos, vista.apoyos)


def observar_vista(detecciones, esquinas, secuencia, movimiento=()):
    """Las siluetas sobre otras casillas impiden interpretar su ausencia como vacío.

    Es una aproximación de oclusión sobre el plano, no un detector de manos.
    """
    obs, _, _, razones = construir_observacion(detecciones, esquinas, secuencia)
    motivos = {p: "Deteccion dudosa" for p in obs.desconocidas}
    for razon in razones:
        causa, _, casilla = razon.rpartition(" en ")
        for p in obs.desconocidas:
            if nombre(*p) == casilla:
                motivos[p] = causa
    apoyos = {}
    h = homografia(esquinas)
    for d in detecciones:
        x, y = cv2.perspectiveTransform(np.float32(d["punto"]).reshape(1, 1, 2), h)[0, 0]
        if not (0 <= x < 8 and 0 <= y < 8):
            continue
        f, c = int(y), int(x)
        if (f, c) not in apoyos or d["conf"] > apoyos[f, c][2]:
            apoyos[f, c] = (float(x), float(y), d["conf"])
        # No redondear un apoyo fronterizo a una casilla arbitraria. También
        # proteger la vecina para no borrarla por un pequeño error geométrico.
        cols = {c} | ({c-1} if x-c < .12 else set()) | ({c+1} if x-c > .88 else set())
        filas = {f} | ({f-1} if y-f < .12 else set()) | ({f+1} if y-f > .88 else set())
        if len(cols) > 1 or len(filas) > 1:
            for fila in filas:
                for col in cols:
                    if 0 <= fila < 8 and 0 <= col < 8:
                        motivos[fila, col] = "Apoyo cerca del borde"
    mascara = np.zeros((160, 160), np.uint8)
    matriz = np.diag([20., 20., 1.]) @ homografia(esquinas)
    for d in detecciones:
        poligono = np.asarray(d["poligono"], np.float32).reshape(-1, 1, 2)
        proyectado = cv2.perspectiveTransform(poligono, matriz).reshape(-1, 2)
        if np.isfinite(proyectado).all():
            cv2.fillPoly(mascara, [np.rint(np.clip(proyectado, -10000, 10000)).astype(np.int32)], 255)
    for f in range(8):
        for c in range(8):
            region = mascara[f*20:(f+1)*20, c*20:(c+1)*20]
            if not obs.tablero[f][c] and np.count_nonzero(region) / 400 >= .2:
                motivos.setdefault((f, c), "Oclusion por silueta")
    for celda in movimiento:
        motivos[celda] = "Movimiento local"
    return con_dudas(obs, motivos, apoyos)


def fusionar(vistas, secuencia):
    """Una evidencia positiva basta; los conflictos quedan sin confirmar.

    Vacío requiere ausencia fiable en AMBAS vistas. No se suman probabilidades
    del mismo modelo como si fueran mediciones independientes.
    """
    if len(vistas) != 2:
        raise ValueError("Se requieren exactamente dos vistas")
    piezas, dudas, confianzas, procedencias = [], [], {}, {}
    for f in range(8):
        for c in range(8):
            casilla = nombre(f, c)
            candidatas = [(i, obs.tablero[f][c], obs.confianzas[f][c])
                          for i, obs in enumerate(vistas)
                          if (f, c) not in obs.desconocidas and obs.tablero[f][c]]
            tipos = {p for _, p, _ in candidatas}
            if len(tipos) > 1:
                dudas.append(casilla)
            elif candidatas:
                if len(candidatas) == 1 and candidatas[0][2] < .7:
                    dudas.append(casilla)
                    continue
                piezas.append({"casilla": casilla, "pieza": candidatas[0][1]})
                confianzas[casilla] = max(conf for _, _, conf in candidatas)
                procedencias[casilla] = "+".join(str(i+1) for i, _, _ in candidatas)
            elif any((f, c) in obs.desconocidas or (not obs.completa and not obs.desconocidas)
                     for obs in vistas):
                dudas.append(casilla)
    # Apoyos muy próximos de vistas distintas que cayeron en casillas vecinas:
    # no confirmar dos piezas cuando pueden ser la misma mal localizada.
    ambiguas = set()
    for a in piezas:
        for b in piezas:
            ca, cb = a["casilla"], b["casilla"]
            if ca >= cb or a["pieza"] != b["pieza"] or {procedencias[ca], procedencias[cb]} != {"1", "2"}:
                continue
            fa, xa = 8-int(ca[1]), ord(ca[0])-97
            fb, xb = 8-int(cb[1]), ord(cb[0])-97
            pa = getattr(vistas[int(procedencias[ca])-1], "apoyos", {}).get((fa, xa))
            pb = getattr(vistas[int(procedencias[cb])-1], "apoyos", {}).get((fb, xb))
            if pa and pb and np.hypot(pa[0]-pb[0], pa[1]-pb[1]) < .55:
                ambiguas.update((ca, cb))
    piezas = [p for p in piezas if p["casilla"] not in ambiguas]
    for casilla in ambiguas:
        dudas.append(casilla)
        confianzas.pop(casilla)
        procedencias.pop(casilla)
    return Observacion.desde_dict({"secuencia": secuencia, "piezas": piezas,
        "desconocidas": dudas, "completa": not dudas, "confianza": 1.,
        "confianzas": confianzas}), procedencias


def par_valido(paquetes, ahora, max_desfase=.25, max_edad=2.):
    return (len(paquetes) == 2 and all(p is not None and "frame" in p and
            not p.get("error") and 0 <= ahora - p["instante"] < max_edad for p in paquetes)
            and abs(paquetes[0]["instante"] - paquetes[1]["instante"]) <= max_desfase)
