"""Fusión conservadora de dos vistas en coordenadas del tablero."""
import cv2
import numpy as np

from chess_simulator.seguimiento import Observacion, nombre
from chess_simulator.vision_vivo import construir_observacion, homografia


def observar_vista(detecciones, esquinas, secuencia):
    """Las siluetas sobre otras casillas impiden interpretar su ausencia como vacío.

    Es una aproximación de oclusión sobre el plano, no un detector de manos.
    """
    obs, _, _, _ = construir_observacion(detecciones, esquinas, secuencia)
    mascara = np.zeros((160, 160), np.uint8)
    matriz = np.diag([20., 20., 1.]) @ homografia(esquinas)
    for d in detecciones:
        poligono = np.asarray(d["poligono"], np.float32).reshape(-1, 1, 2)
        proyectado = cv2.perspectiveTransform(poligono, matriz).reshape(-1, 2)
        if np.isfinite(proyectado).all():
            cv2.fillPoly(mascara, [np.rint(np.clip(proyectado, -10000, 10000)).astype(np.int32)], 255)
    desconocidas = set(obs.desconocidas)
    for f in range(8):
        for c in range(8):
            region = mascara[f*20:(f+1)*20, c*20:(c+1)*20]
            if not obs.tablero[f][c] and np.count_nonzero(region) / 400 >= .2:
                desconocidas.add((f, c))
    return Observacion(obs.secuencia, obs.tablero, not desconocidas, obs.confianza,
                       frozenset(desconocidas), obs.confianzas)


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
                piezas.append({"casilla": casilla, "pieza": candidatas[0][1]})
                confianzas[casilla] = max(conf for _, _, conf in candidatas)
                procedencias[casilla] = "+".join(str(i+1) for i, _, _ in candidatas)
            elif any((f, c) in obs.desconocidas or (not obs.completa and not obs.desconocidas)
                     for obs in vistas):
                dudas.append(casilla)
    return Observacion.desde_dict({"secuencia": secuencia, "piezas": piezas,
        "desconocidas": dudas, "completa": not dudas, "confianza": 1.,
        "confianzas": confianzas}), procedencias


def par_valido(paquetes, ahora, max_desfase=.25, max_edad=2.):
    return (len(paquetes) == 2 and all(p is not None and "frame" in p and
            not p.get("error") and 0 <= ahora - p["instante"] < max_edad for p in paquetes)
            and abs(paquetes[0]["instante"] - paquetes[1]["instante"]) <= max_desfase)
