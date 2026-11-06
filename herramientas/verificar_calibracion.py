"""Informe de precisión con medidas independientes: python -m herramientas.verificar_calibracion."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path

import cv2
import numpy as np

from chess_simulator.calibracion import cargar_tablero, cargar_calibracion
from chess_simulator.rutas import RESULTADOS
from chess_simulator.vision_vivo import homografia


def evaluar(esquinas, tablero, muestras, tolerancia_mm=None):
    """Cada muestra lleva pixel, xy_m medido e id del punto físico repetido."""
    if not muestras:
        raise ValueError("Se necesitan medidas independientes de validación")
    if tolerancia_mm is not None and (not np.isfinite(tolerancia_mm) or tolerancia_mm < 0):
        raise ValueError("La tolerancia debe ser finita y no negativa")
    matriz = homografia(esquinas)
    grupos, referencias, filas = defaultdict(list), {}, []
    for muestra in muestras:
        pixel = np.asarray(muestra["pixel"], dtype=float)
        real = np.asarray(muestra["xy_m"], dtype=float)
        if pixel.shape != (2,) or real.shape != (2,) or not np.isfinite([pixel, real]).all():
            raise ValueError("Cada muestra necesita pixel y xy_m finitos de dos componentes")
        if not (0 <= real[0] <= tablero.ancho_m and 0 <= real[1] <= tablero.alto_m):
            raise ValueError("La medida física está fuera del tablero")
        if any(np.linalg.norm(pixel-np.asarray(p)) < 1e-3 for p in esquinas):
            raise ValueError("No valide con los cuatro vértices usados para ajustar")
        xt, yt = cv2.perspectiveTransform(pixel.astype(np.float32).reshape(1, 1, 2), matriz)[0, 0]
        estimado = tablero.a_metros(float(xt), float(yt))
        identificador = muestra["id"]
        if not isinstance(identificador, str) or not identificador.strip():
            raise ValueError("Cada muestra necesita un id de punto físico")
        if identificador in referencias and not np.allclose(referencias[identificador], real, rtol=0, atol=1e-9):
            raise ValueError("Un id repetido debe conservar su posición física medida")
        referencias[identificador] = real
        grupos[identificador].append(estimado)
        error = (np.asarray(estimado)-real)*1000
        filas.append({"id": identificador, "captura": muestra.get("captura"),
                      "pixel": pixel.tolist(), "medido_m": real.tolist(), "estimado_m": estimado,
                      "error_xy_mm": error.tolist(), "error_mm": float(np.linalg.norm(error))})
    errores = np.array([f["error_mm"] for f in filas])
    repetibilidad = {}
    for identificador, puntos in grupos.items():
        if len(puntos) > 1:
            puntos = np.asarray(puntos)*1000
            repetibilidad[identificador] = {
                "capturas": len(puntos),
                "dispersion_max_mm": float(np.max(np.linalg.norm(puntos[:, None]-puntos[None, :], axis=2)))}
    return {"fecha": datetime.now(timezone.utc).isoformat(), "tablero": tablero.a_dict(),
            "muestras": filas, "cantidad": len(filas), "puntos_distintos": len(grupos),
            "error_medio_mm": float(errores.mean()), "error_max_mm": float(errores.max()),
            "rmse_mm": float(np.sqrt(np.mean(errores**2))),
            "repetibilidad": repetibilidad, "tolerancia_mm": tolerancia_mm,
            "dentro_tolerancia": bool(errores.max() <= tolerancia_mm) if tolerancia_mm is not None else None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tablero", type=Path, required=True)
    parser.add_argument("--calibracion", type=Path, required=True)
    parser.add_argument("--medidas", type=Path, required=True,
                        help="JSON con source, resolucion y muestras independientes")
    parser.add_argument("--contexto-calibracion")
    parser.add_argument("--tolerancia-mm", type=float)
    parser.add_argument("--salida", type=Path, default=RESULTADOS / "precision_calibracion.json")
    args = parser.parse_args(argv)
    try:
        tablero = cargar_tablero(args.tablero)
        datos = json.loads(args.medidas.read_text(encoding="utf-8"))
        esquinas = cargar_calibracion(args.calibracion, datos["source"], datos["resolucion"],
                                     tablero, args.contexto_calibracion)
        informe = evaluar(esquinas, tablero, datos["muestras"], args.tolerancia_mm)
        informe["calibracion"] = str(args.calibracion.resolve())
        informe["source"] = datos["source"]
        informe["resolucion"] = datos["resolucion"]
        informe["contexto"] = args.contexto_calibracion
        args.salida.parent.mkdir(parents=True, exist_ok=True)
        args.salida.write_text(json.dumps(informe, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(f"Error medio: {informe['error_medio_mm']:.2f} mm; máximo: {informe['error_max_mm']:.2f} mm")
    print(f"Informe: {args.salida}")
    return informe


if __name__ == "__main__":
    main()
