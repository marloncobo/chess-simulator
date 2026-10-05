"""Prueba con dos fotos: la misma cadena que en vivo, sin cámaras ni puentes.

Toma dos fotos del MISMO tablero desde dos posiciones (sin mover nada entre
una y otra), corre el modelo, asigna casillas, fusiona las dos vistas y
muestra el mismo panel que la ventana en vivo, más un resumen en la terminal.

Uso:
    python -m herramientas.probar_fotos fotoA.jpg fotoB.jpg

La primera vez se abre cada foto: haga clic en las 4 esquinas EXTERIORES de
la cuadrícula en el orden a8, h8, h1, a1. Enter acepta, R repite. Las
esquinas se guardan en config/esquinas_fotos.json, así que la siguiente vez
con las mismas fotos no hay que volver a marcarlas (--recalibrar para
repetir).

Opciones útiles:
    --guardar-par datos/verificacion/pares.json
        Añade el par a ese archivo con la posición que detectó la fusión.
        Corrija a mano esa "posicion" y luego mida aciertos con
        python -m herramientas.evaluar_pares datos/verificacion/pares.json
    --sin-ventana     no abre ventanas (las esquinas deben estar guardadas)
    --confianza 0.5   cambia el filtro de YOLO (por defecto 0.25)
"""
import argparse
import json
import os
from pathlib import Path

import cv2
import numpy as np

from chess_simulator.diagnostico import diagnosticar, problemas, resumen, contar_clases
from chess_simulator.fusion_camaras import FiltroCasillas, fusionar, observar_vista
from chess_simulator.reglas_deteccion import CONFIANZA_DETECTOR
from chess_simulator.rutas import CONFIG, MODELO
from chess_simulator.seguimiento import nombre
from chess_simulator.vision_vivo import extraer, homografia

VERTICES = ("a8", "h8", "h1", "a1")
VENTANA = "Marque a8, h8, h1, a1 | Enter: aceptar | R: repetir | Esc: salir"
COLORES = {"BLANCA": (80, 230, 80), "NEGRA": (255, 170, 50)}


def ruta_esquinas():
    return CONFIG / "esquinas_fotos.json"


def clave(ruta, forma):
    return f"{Path(ruta).resolve()}|{forma[1]}x{forma[0]}"


def leer_guardadas():
    try:
        return json.loads(ruta_esquinas().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def guardar_esquinas(ruta, forma, esquinas):
    datos = leer_guardadas()
    datos[clave(ruta, forma)] = [list(map(float, p)) for p in esquinas]
    ruta_esquinas().parent.mkdir(parents=True, exist_ok=True)
    ruta_esquinas().write_text(json.dumps(datos, indent=1), encoding="utf-8")


def dibujar_rejilla(imagen, esquinas, grosor=2):
    inversa = np.linalg.inv(homografia(esquinas))
    for n in range(9):
        for extremos in ([[n, 0], [n, 8]], [[0, n], [8, n]]):
            p = cv2.perspectiveTransform(np.float32(extremos).reshape(-1, 1, 2), inversa).reshape(-1, 2)
            cv2.line(imagen, tuple(np.rint(p[0]).astype(int)), tuple(np.rint(p[1]).astype(int)),
                     (70, 160, 140), grosor)
    for f in range(8):
        for c in range(8):
            p = cv2.perspectiveTransform(np.float32([[[c + .5, f + .5]]]), inversa)[0, 0]
            cv2.putText(imagen, nombre(f, c), (int(p[0]) - 12, int(p[1]) + 5),
                        cv2.FONT_HERSHEY_SIMPLEX, .5, (255, 0, 255), 1, cv2.LINE_AA)


def marcar_esquinas(frame, titulo):
    """Clics en a8, h8, h1, a1 sobre la foto reducida a la pantalla."""
    alto, ancho = frame.shape[:2]
    escala = min(1.0, 1200 / ancho, 800 / alto)
    pequena = cv2.resize(frame, (round(ancho * escala), round(alto * escala)), interpolation=cv2.INTER_AREA)
    puntos = []

    def clic(evento, x, y, *_):
        if evento == cv2.EVENT_LBUTTONDOWN and len(puntos) < 4:
            puntos.append((x / escala, y / escala))

    cv2.namedWindow(VENTANA, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(VENTANA, clic)
    while True:
        vista = pequena.copy()
        for n, (x, y) in enumerate(puntos):
            xy = (round(x * escala), round(y * escala))
            cv2.circle(vista, xy, 6, (100, 255, 100), -1)
            cv2.putText(vista, VERTICES[n], (xy[0] + 8, xy[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, .7, (100, 255, 100), 2)
        aviso = f"{titulo}: clic en {VERTICES[len(puntos)]}" if len(puntos) < 4 else "Enter: aceptar | R: repetir"
        if len(puntos) == 4:
            try:
                dibujar_rejilla(vista, [(x * escala, y * escala) for x, y in puntos], 1)
            except ValueError:
                aviso = "Esquinas invalidas: pulse R y repita en orden a8, h8, h1, a1"
        cv2.putText(vista, aviso, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, .8, (0, 0, 0), 4)
        cv2.putText(vista, aviso, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, .8, (255, 255, 255), 2)
        cv2.imshow(VENTANA, vista)
        tecla = cv2.waitKey(30) & 0xFF
        if tecla in (ord("r"), ord("R")):
            puntos.clear()
        elif tecla in (13, 10) and len(puntos) == 4:
            try:
                homografia(puntos)
                break
            except ValueError:
                puntos.clear()
        elif tecla == 27 or cv2.getWindowProperty(VENTANA, cv2.WND_PROP_VISIBLE) < 1:
            cv2.destroyAllWindows()
            raise SystemExit("Cancelado")
    cv2.destroyWindow(VENTANA)
    return puntos


def observar_foto(red, frame, esquinas, confianza=CONFIANZA_DETECTOR):
    """Lo mismo que hace la sesión en vivo con un cuadro, sin movimiento."""
    resultado = red(frame, conf=confianza, max_det=64, verbose=False)[0]
    detecciones = extraer(resultado, frame)
    filtro = FiltroCasillas()
    filtro.evaluar(frame, esquinas, 0.)
    return detecciones, filtro.verificar_vacios(observar_vista(detecciones, esquinas, 1))


def tablero_texto(obs):
    filas = []
    for f in range(8):
        celdas = []
        for c in range(8):
            if (f, c) in obs.desconocidas:
                celdas.append(" ?")
            else:
                celdas.append(f"{obs.tablero[f][c] or '·':>2}")
        filas.append(f"{8 - f} " + " ".join(celdas))
    filas.append("   " + "  ".join("abcdefgh"))
    return filas


def panel_foto(frame, detecciones, esquinas, titulo):
    imagen = frame.copy()
    grosor = max(2, round(max(frame.shape[:2]) / 600))
    dibujar_rejilla(imagen, esquinas, grosor)
    for d in detecciones:
        color = COLORES.get(d["color"], (0, 190, 255))
        cv2.polylines(imagen, [d["poligono"]], True, color, grosor)
        x, y = map(int, d["punto"])
        cv2.putText(imagen, f'{d["pieza"]} {d["conf"]:.2f}', (x - 20, y + 25),
                    cv2.FONT_HERSHEY_SIMPLEX, .5 * grosor, color, grosor, cv2.LINE_AA)
    lienzo = np.zeros((480, 640, 3), np.uint8)
    alto, ancho = imagen.shape[:2]
    escala = min(640 / ancho, 440 / alto)
    w, h = round(ancho * escala), round(alto * escala)
    lienzo[40 + (440 - h) // 2:40 + (440 - h) // 2 + h, (640 - w) // 2:(640 - w) // 2 + w] = \
        cv2.resize(imagen, (w, h), interpolation=cv2.INTER_AREA)
    cv2.putText(lienzo, titulo[:60], (12, 27), cv2.FONT_HERSHEY_SIMPLEX, .65, (100, 230, 100), 1, cv2.LINE_AA)
    return lienzo


def anadir_par(destino, rutas, esquinas, fusion):
    destino = Path(destino)
    try:
        datos = json.loads(destino.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        datos = {"pares": []}
    base = destino.resolve().parent
    posicion = {nombre(f, c): p for f in range(8) for c in range(8)
                if (p := fusion.tablero[f][c]) and not p.startswith("?")}
    rel = [os.path.relpath(Path(r).resolve(), base) for r in rutas]
    datos["pares"].append({
        "nombre": f"{Path(rutas[0]).stem} + {Path(rutas[1]).stem}",
        "a": rel[0], "b": rel[1],
        "esquinas_a": [list(map(round, p)) for p in esquinas[0]],
        "esquinas_b": [list(map(round, p)) for p in esquinas[1]],
        "posicion_sin_revisar": True,
        "posicion": posicion})
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(datos["pares"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("fotos", nargs=2, type=Path, metavar=("FOTO_1", "FOTO_2"))
    parser.add_argument("--modelo", type=Path, default=MODELO)
    parser.add_argument("--confianza", type=float, default=CONFIANZA_DETECTOR)
    parser.add_argument("--recalibrar", action="store_true", help="Volver a marcar las esquinas")
    parser.add_argument("--sin-ventana", action="store_true", help="No abrir ventanas")
    parser.add_argument("--salida", type=Path, default=Path("resultados"),
                        help="Carpeta donde se guarda la imagen del resultado")
    parser.add_argument("--guardar-par", type=Path, metavar="JSON",
                        help="Añadir el par a un archivo de verificación para evaluar_pares")
    args = parser.parse_args(argv)
    if not args.modelo.is_file():
        parser.error(f"No existe el modelo: {args.modelo}")

    frames, esquinas = [], []
    guardadas = leer_guardadas()
    for i, ruta in enumerate(args.fotos, 1):
        frame = cv2.imread(str(ruta))
        if frame is None:
            parser.error(f"No se pudo abrir la foto {ruta}")
        frames.append(frame)
        previas = None if args.recalibrar else guardadas.get(clave(ruta, frame.shape))
        if previas is None:
            if args.sin_ventana:
                parser.error(f"Faltan las esquinas de {ruta}; ejecute una vez sin --sin-ventana")
            previas = marcar_esquinas(frame, f"Foto {i}")
            guardar_esquinas(ruta, frame.shape, previas)
            print(f"Esquinas de la foto {i} guardadas en {ruta_esquinas()}")
        esquinas.append(previas)

    print("Cargando modelo...")
    from ultralytics import YOLO
    red = YOLO(str(args.modelo))
    detecciones, vistas = [], []
    for frame, e in zip(frames, esquinas):
        d, v = observar_foto(red, frame, e, args.confianza)
        detecciones.append(d)
        vistas.append(v)
    fusion, _ = fusionar(vistas, 1)
    casillas = diagnosticar(vistas, fusion)

    print()
    titulos = ("FOTO 1", "FOTO 2", "FUSION (lo que se confirmaria)")
    bloques = [tablero_texto(o) for o in (*vistas, fusion)]
    print("   ".join(f"{t:<26}" for t in titulos))
    for filas in zip(*bloques):
        print("   ".join(f"{f:<26}" for f in filas))
    print("  Mayuscula = blanca, minuscula = negra, ?X = color dudoso, ? = casilla en duda, · = vacia")

    r = resumen(casillas)
    print(f"\nCoinciden las dos: {r.get('AMBAS', 0)} | solo foto 1: {r.get('RESCATE_1', 0) + r.get('SOLO_1', 0)}"
          f" | solo foto 2: {r.get('RESCATE_2', 0) + r.get('SOLO_2', 0)} | discrepan: {r.get('CONFLICTO', 0)}"
          f" | inciertas: {r.get('CIEGAS', 0)}")
    filas, total = contar_clases(fusion.tablero)
    print("Piezas confirmadas: " + "  ".join(f"{x['clase']} {x['n']}/{x['esperadas']}" for x in filas)
          + f"  total {total}/32")
    lista, n = problemas(casillas, limite=20)
    if lista:
        print(f"\nCasillas a revisar ({n}):")
        for casilla, d in lista:
            print(f"  {casilla:<3} {d['estado']:<10} foto1 {d['v1'] or '-':<3} foto2 {d['v2'] or '-':<3} {d['detalle']}")

    from herramientas.panel_diagnostico import panel_inferior
    arriba = np.hstack([panel_foto(f, d, e, f"Foto 1 | {args.fotos[0].name}" if i == 0 else f"Foto 2 | {args.fotos[1].name}")
                        for i, (f, d, e) in enumerate(zip(frames, detecciones, esquinas))])
    abajo = panel_inferior(fusion.tablero, casillas, fusion.desconocidas, 0.,
                           "Prueba con fotos: resultado de un solo cuadro, sin confirmacion temporal", "")
    imagen = np.vstack([arriba, abajo])
    args.salida.mkdir(parents=True, exist_ok=True)
    destino = args.salida / f"fotos_{args.fotos[0].stem}_{args.fotos[1].stem}.jpg"
    cv2.imwrite(str(destino), imagen)
    print(f"\nImagen del resultado: {destino}")

    if args.guardar_par:
        n = anadir_par(args.guardar_par, args.fotos, esquinas, fusion)
        print(f"Par {n} añadido a {args.guardar_par}. Revise y corrija su 'posicion' a mano,"
              f" luego: python -m herramientas.evaluar_pares {args.guardar_par}")

    if not args.sin_ventana:
        cv2.namedWindow("Resultado", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Resultado", 1152, 837)
        cv2.imshow("Resultado", imagen)
        print("Pulse cualquier tecla en la ventana para cerrar.")
        cv2.waitKey(0)
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
