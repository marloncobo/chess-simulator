"""Arnés de verificación: mide la cadena de visión contra posiciones anotadas a mano.

Responde la pregunta que las pruebas sintéticas no contestan: ¿con qué
frecuencia acierta el tablero? Corre el modelo real sobre pares de fotos,
aplica observar_vista y fusionar exactamente como en vivo (sin seguimiento
temporal) y compara casilla por casilla con la verdad.

Uso:
    python -m herramientas.evaluar_pares datos/verificacion/pares.json
    python -m herramientas.evaluar_pares datos/verificacion/pares.json --confianza .5
    python -m herramientas.evaluar_pares datos/verificacion/pares.json --csv resultados/eval.csv

Formato del JSON (rutas relativas al propio archivo):
    {"pares": [{"nombre": "medio juego 1",
                "a": "../../foto1.jpeg", "b": "../../foto2.jpeg",
                "esquinas_a": [[x, y] a8, h8, h1, a1],
                "esquinas_b": [...],
                "posicion": {"a2": "P", "b5": "a", ...}}]}
Mayúscula = blanca, minúscula = negra; las casillas no listadas están vacías.

Lo que importa leer en el resultado:
  * "falsas vacías": había pieza y el sistema afirmó vacío. Es el error más
    grave para el brazo; debería ser 0.
  * "errores afirmados": el sistema confirmó una pieza equivocada.
  * "en duda": no afirmó nada. Es seguro pero cuesta cobertura.
"""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import cv2

from chess_simulator.fusion_camaras import FiltroCasillas, fusionar, observar_vista
from chess_simulator.reglas_deteccion import CONFIANZA_DETECTOR
from chess_simulator.rutas import MODELO
from chess_simulator.seguimiento import indices, nombre
from chess_simulator.vision_vivo import extraer

CASILLAS = [nombre(f, c) for f in range(8) for c in range(8)]


def cargar_pares(ruta):
    ruta = Path(ruta)
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    pares = []
    for par in datos["pares"]:
        posicion = {}
        for casilla, pieza in par["posicion"].items():
            indices(casilla)
            if pieza not in "TCADRPtcadrp" or len(pieza) != 1:
                raise ValueError(f"Pieza invalida {pieza!r} en {casilla}")
            posicion[casilla] = pieza
        pares.append({**par, "a": ruta.parent / par["a"], "b": ruta.parent / par["b"],
                      "posicion": posicion})
    return pares


def clasificar_casilla(verdad, afirmado, en_duda):
    """Una etiqueta por casilla, desde el punto de vista del brazo."""
    if en_duda:
        return "duda_pieza" if verdad else "duda_vacia"
    if verdad and afirmado == verdad:
        return "acierto_pieza"
    if not verdad and not afirmado:
        return "acierto_vacia"
    if verdad and not afirmado:
        return "falsa_vacia"
    if not verdad and afirmado:
        return "pieza_fantasma"
    if afirmado.lstrip("?").upper() == verdad.upper():
        return "color_erroneo"
    return "clase_erronea"


def evaluar_observacion(obs, posicion):
    filas = {}
    for casilla in CASILLAS:
        f, c = indices(casilla)
        filas[casilla] = clasificar_casilla(posicion.get(casilla, ""), obs.tablero[f][c],
                                            (f, c) in obs.desconocidas)
    return filas


ETIQUETAS = [("acierto_pieza", "piezas correctas"), ("acierto_vacia", "vacias correctas"),
             ("duda_pieza", "en duda (habia pieza)"), ("duda_vacia", "en duda (estaba vacia)"),
             ("falsa_vacia", "FALSAS VACIAS"), ("pieza_fantasma", "piezas fantasma"),
             ("clase_erronea", "clase erronea"), ("color_erroneo", "color erroneo")]


def imprimir(titulo, conteo, total_piezas):
    afirmadas = conteo["acierto_pieza"] + conteo["clase_erronea"] + conteo["color_erroneo"] + conteo["pieza_fantasma"]
    print(f"  {titulo}")
    for clave, texto in ETIQUETAS:
        if conteo[clave] or clave in ("acierto_pieza", "falsa_vacia", "duda_pieza"):
            print(f"    {texto:<24}{conteo[clave]:>4}")
    print(f"    {'cobertura de piezas':<24}{conteo['acierto_pieza'] / max(1, total_piezas):>8.1%}")
    print(f"    {'precision afirmada':<24}{conteo['acierto_pieza'] / max(1, afirmadas):>8.1%}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pares", type=Path)
    parser.add_argument("--modelo", type=Path, default=MODELO)
    parser.add_argument("--confianza", type=float, default=CONFIANZA_DETECTOR)
    parser.add_argument("--csv", type=Path, help="Detalle por casilla")
    args = parser.parse_args(argv)

    from ultralytics import YOLO
    red = YOLO(str(args.modelo))
    pares = cargar_pares(args.pares)
    totales = {"vista 1": Counter(), "vista 2": Counter(), "fusion": Counter()}
    motivos = Counter()
    detalle = []
    piezas_totales = 0
    for par in pares:
        vistas = []
        for clave, esquinas in (("a", par["esquinas_a"]), ("b", par["esquinas_b"])):
            frame = cv2.imread(str(par[clave]))
            if frame is None:
                parser.error(f"No se pudo leer {par[clave]}")
            resultado = red(frame, conf=args.confianza, max_det=64, verbose=False)[0]
            # Igual que en vivo: después de observar, comprobar que las ausencias
            # se parecen al fondo vacío. Con una foto fija no hay movimiento.
            filtro = FiltroCasillas()
            filtro.evaluar(frame, esquinas, 0.)
            vistas.append(filtro.verificar_vacios(observar_vista(extraer(resultado, frame), esquinas, 1)))
        fusion, _ = fusionar(vistas, 1)
        piezas_totales += len(par["posicion"])
        por_fuente = {"vista 1": evaluar_observacion(vistas[0], par["posicion"]),
                      "vista 2": evaluar_observacion(vistas[1], par["posicion"]),
                      "fusion": evaluar_observacion(fusion, par["posicion"])}
        for fuente, filas in por_fuente.items():
            totales[fuente].update(filas.values())
        for casilla in CASILLAS:
            f, c = indices(casilla)
            if (f, c) in fusion.desconocidas and par["posicion"].get(casilla):
                motivo = getattr(fusion, "motivos", {}).get((f, c), "sin motivo")
                motivos[motivo.split(":")[0].split(" (")[0]] += 1
            detalle.append({"par": par.get("nombre", ""), "casilla": casilla,
                            "verdad": par["posicion"].get(casilla, ""),
                            "vista1": vistas[0].tablero[f][c], "vista2": vistas[1].tablero[f][c],
                            "fusion": fusion.tablero[f][c],
                            **{k: v[casilla] for k, v in por_fuente.items()},
                            "motivo_fusion": getattr(fusion, "motivos", {}).get((f, c), "")})

    print(f"{len(pares)} pares, {piezas_totales} piezas, umbral del detector {args.confianza}")
    for fuente, conteo in totales.items():
        imprimir(fuente, conteo, piezas_totales)
    errores = [d for d in detalle if d["fusion"] in ("falsa_vacia", "pieza_fantasma", "clase_erronea", "color_erroneo")]
    if errores:
        print("  Errores afirmados por la fusion:")
        for d in errores:
            print(f"    {d['par']} {d['casilla']}: verdad {d['verdad'] or '-'}, "
                  f"v1 {d['vista1'] or '-'}, v2 {d['vista2'] or '-'}, fusion {d['fusion']}")
    if motivos:
        print("  Piezas en duda tras la fusion, por motivo:")
        for motivo, n in motivos.most_common():
            print(f"    {n:>3}  {motivo}")
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="", encoding="utf-8") as archivo:
            escritor = csv.DictWriter(archivo, fieldnames=list(detalle[0]))
            escritor.writeheader()
            escritor.writerows(detalle)
        print(f"Detalle por casilla en {args.csv}")


if __name__ == "__main__":
    main()
