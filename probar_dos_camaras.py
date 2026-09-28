"""
Prueba de complementacion entre dos camaras.

QUE DEMUESTRA
-------------
Que lo que una camara no ve por oclusion, la otra si. Compara tres
resultados sobre la misma posicion del tablero:

    solo camara A      lo que ve A por su cuenta
    solo camara B      lo que ve B por su cuenta
    A + B              la union, que es lo que se busca

Y dice explicitamente cuantas piezas rescato cada una.

NO HACEN FALTA DOS CAMARAS PARA PROBARLO
----------------------------------------
Basta un celular. Se toman las fotos desde dos posiciones distintas,
sin mover el tablero entre una y otra. Para el analisis es lo mismo
que tener dos camaras fijas.

DOS FORMAS DE USARLO
--------------------

  A) CON DOS FOTOS  (lo mas rapido)

        python3 probar_dos_camaras.py fotoA.jpg fotoB.jpg

     Se abre cada foto y se hace clic en las 4 esquinas del tablero,
     en este orden: arriba-izquierda, arriba-derecha, abajo-derecha,
     abajo-izquierda. Con eso queda calibrada.

     Funciona con las piezas en cualquier posicion, porque las
     esquinas del tablero se ven igual esten donde esten las piezas.

  B) CON CUATRO FOTOS  (calibracion automatica)

        python3 probar_dos_camaras.py calibA.jpg calibB.jpg pruebaA.jpg pruebaB.jpg

     Las dos primeras son del tablero en POSICION INICIAL, con las 4
     torres en las esquinas: de ahi sale la calibracion sola, sin
     clics. Las dos ultimas son la posicion que se quiere medir,
     tomadas desde los mismos dos sitios.

     Util cuando se van a probar muchas posiciones seguidas: se
     calibra una vez y las camaras ya no se tocan.

Genera:
    comparacion_<nombre>.jpg   las tres vistas lado a lado
    complementacion.csv        el detalle en tabla
"""

import csv
import os
import sys

import cv2
import numpy as np
from ultralytics import YOLO

# ----- CONFIGURACION -----
MODELO = "modelos/bestnano.pt"
CLASE_TORRE = "TOWER"
CONFIANZA = 0.25
USAR_BASE = True      # la base de la mascara suele caer mejor en la casilla
CASILLA = 80
LADO = CASILLA * 8

COLOR_A = (255, 170, 90)       # azul   BGR
COLOR_B = (90, 140, 255)       # naranja
COLOR_AMBAS = (130, 220, 120)  # verde
BLANCO = (255, 255, 255)
GRIS = (110, 110, 115)
# -------------------------


# ==========  DETECCION  ==========

def detectar_torres(model, ruta):
    """Centro de masa y base de la mascara de cada torre."""
    imagen = cv2.imread(ruta)
    if imagen is None:
        raise SystemExit(f"No se pudo abrir: {ruta}")

    resultado = model(ruta, conf=CONFIANZA, verbose=False)[0]
    torres = []

    if resultado.masks is not None:
        for i, poligono in enumerate(resultado.masks.xy):
            if model.names[int(resultado.boxes.cls[i])] != CLASE_TORRE:
                continue

            puntos = np.array(poligono, dtype=np.int32)
            M = cv2.moments(puntos)
            if M["m00"] == 0:
                continue

            cx = M["m10"] / M["m00"]
            torres.append({
                "centro": (cx, M["m01"] / M["m00"]),
                "base": (cx, float(puntos[:, 1].max())),
                "conf": float(resultado.boxes.conf[i]),
                "poligono": puntos,
            })

    torres.sort(key=lambda t: (t["centro"][1], t["centro"][0]))
    return imagen, torres


def punto_de(torre):
    return torre["base"] if USAR_BASE else torre["centro"]


# ==========  GEOMETRIA  ==========

def ordenar_esquinas(puntos):
    puntos = np.array(puntos, dtype=np.float32)
    suma = puntos.sum(axis=1)
    resta = puntos[:, 1] - puntos[:, 0]
    return np.array([
        puntos[np.argmin(suma)],
        puntos[np.argmin(resta)],
        puntos[np.argmax(suma)],
        puntos[np.argmax(resta)],
    ], dtype=np.float32)


def calibrar(torres, etiqueta):
    """
    Homografia a partir de las 4 torres de esquina.

    Sus centros estan a media casilla de cada borde, no en el borde.
    """
    if len(torres) != 4:
        print(f"  [!] {etiqueta}: se detectaron {len(torres)} torres, "
              f"hacen falta exactamente 4.")
        print("      Revisa que la foto de calibracion tenga el tablero")
        print("      en posicion inicial y las 4 esquinas visibles.")
        return None

    m = CASILLA / 2
    destino = np.array([
        [m, m],
        [LADO - m, m],
        [LADO - m, LADO - m],
        [m, LADO - m],
    ], dtype=np.float32)

    origen = ordenar_esquinas([punto_de(t) for t in torres])
    H, _ = cv2.findHomography(origen, destino)
    return H


def calibrar_a_mano(imagen, etiqueta):
    """
    Homografia marcando las 4 esquinas del tablero con el raton.

    Sirve con las piezas en cualquier posicion: las esquinas del
    tablero se ven igual esten donde esten las fichas.
    """
    ventana = f"Marca las 4 esquinas - {etiqueta}"
    puntos = []

    alto, ancho = imagen.shape[:2]
    escala = min(1.0, 1100 / ancho, 800 / alto)
    vista = cv2.resize(imagen, (int(ancho * escala), int(alto * escala)))
    base = vista.copy()

    ORDEN = ["arriba-izquierda", "arriba-derecha",
             "abajo-derecha", "abajo-izquierda"]

    def redibujar():
        vista[:] = base
        cv2.rectangle(vista, (0, 0), (vista.shape[1], 52), (0, 0, 0), -1)

        if len(puntos) < 4:
            texto = f"{etiqueta}: clic en la esquina {ORDEN[len(puntos)]}"
            color = (90, 200, 255)
        else:
            texto = f"{etiqueta}: listo. ENTER para continuar"
            color = (130, 220, 120)

        cv2.putText(vista, texto, (10, 21), cv2.FONT_HERSHEY_SIMPLEX,
                    0.58, color, 1, cv2.LINE_AA)
        cv2.putText(vista, "Z deshacer el ultimo clic    ESC cancelar",
                    (10, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                    (160, 160, 165), 1, cv2.LINE_AA)

        for n, p in enumerate(puntos, 1):
            cv2.circle(vista, p, 7, BLANCO, -1, cv2.LINE_AA)
            cv2.circle(vista, p, 7, (255, 0, 255), 2, cv2.LINE_AA)
            cv2.putText(vista, str(n), (p[0] + 11, p[1] - 9),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4,
                        cv2.LINE_AA)
            cv2.putText(vista, str(n), (p[0] + 11, p[1] - 9),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 1,
                        cv2.LINE_AA)

        if len(puntos) > 1:
            cerrar = len(puntos) == 4
            cv2.polylines(vista, [np.array(puntos, np.int32)], cerrar,
                          (255, 0, 255), 2, cv2.LINE_AA)

        cv2.imshow(ventana, vista)

    def al_clic(evento, x, y, flags, params):
        if evento == cv2.EVENT_LBUTTONDOWN and len(puntos) < 4:
            puntos.append((x, y))
            redibujar()

    cv2.namedWindow(ventana)
    cv2.setMouseCallback(ventana, al_clic)
    redibujar()

    while True:
        tecla = cv2.waitKey(20) & 0xFF
        if tecla == 27:                       # ESC
            cv2.destroyWindow(ventana)
            return None
        if tecla in (ord("z"), ord("Z")) and puntos:
            puntos.pop()
            redibujar()
        if tecla in (13, 10) and len(puntos) == 4:
            break

    cv2.destroyWindow(ventana)

    # Los clics estan sobre la imagen reducida: se devuelven a escala real
    reales = [(x / escala, y / escala) for x, y in puntos]

    destino = np.array([
        [0, 0], [LADO, 0], [LADO, LADO], [0, LADO],
    ], dtype=np.float32)

    H, _ = cv2.findHomography(ordenar_esquinas(reales), destino)
    return H


def a_casilla(punto, H):
    if H is None:
        return None
    p = np.array([[[punto[0], punto[1]]]], dtype=np.float32)
    q = cv2.perspectiveTransform(p, H)[0][0]
    col, fila = int(q[0] // CASILLA), int(q[1] // CASILLA)
    if 0 <= col < 8 and 0 <= fila < 8:
        return fila, col
    return None


def nombre_casilla(fila, col):
    return f"{'abcdefgh'[col]}{8 - fila}"


def casillas_vistas(torres, H):
    """{casilla: confianza} de lo que ve una camara."""
    vistas = {}
    for t in torres:
        c = a_casilla(punto_de(t), H)
        if c is not None:
            vistas[c] = max(vistas.get(c, 0.0), t["conf"])
    return vistas


# ==========  DIBUJO  ==========

def vista_tablero(titulo, casillas, color_por_casilla, subtitulo=""):
    """Dibuja un tablero 8x8 con las casillas ocupadas marcadas."""
    alto_cab = 54
    lienzo = np.full((LADO + alto_cab, LADO, 3), (32, 28, 26), np.uint8)

    for fila in range(8):
        for col in range(8):
            color = (235, 215, 180) if (fila + col) % 2 == 0 else (96, 150, 118)
            cv2.rectangle(lienzo,
                          (col * CASILLA, alto_cab + fila * CASILLA),
                          ((col + 1) * CASILLA, alto_cab + (fila + 1) * CASILLA),
                          color, -1)

    for (fila, col) in casillas:
        x0, y0 = col * CASILLA, alto_cab + fila * CASILLA
        color = color_por_casilla((fila, col))

        zona = lienzo[y0:y0 + CASILLA, x0:x0 + CASILLA]
        tinte = np.full_like(zona, color, dtype=np.uint8)
        lienzo[y0:y0 + CASILLA, x0:x0 + CASILLA] = cv2.addWeighted(
            zona, 0.5, tinte, 0.5, 0)

        cv2.rectangle(lienzo, (x0, y0), (x0 + CASILLA, y0 + CASILLA),
                      color, 3)
        cv2.circle(lienzo, (x0 + CASILLA // 2, y0 + CASILLA // 2),
                   9, BLANCO, -1, cv2.LINE_AA)
        cv2.circle(lienzo, (x0 + CASILLA // 2, y0 + CASILLA // 2),
                   9, color, 2, cv2.LINE_AA)

        texto = nombre_casilla(fila, col)
        cv2.putText(lienzo, texto, (x0 + 6, y0 + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(lienzo, texto, (x0 + 6, y0 + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, BLANCO, 1, cv2.LINE_AA)

    for i in range(9):
        p = i * CASILLA
        cv2.line(lienzo, (p, alto_cab), (p, alto_cab + LADO), GRIS, 1)
        cv2.line(lienzo, (0, alto_cab + p), (LADO, alto_cab + p), GRIS, 1)

    cv2.putText(lienzo, titulo, (12, 26), cv2.FONT_HERSHEY_SIMPLEX,
                0.72, BLANCO, 2, cv2.LINE_AA)
    if subtitulo:
        cv2.putText(lienzo, subtitulo, (12, 46), cv2.FONT_HERSHEY_SIMPLEX,
                    0.46, (170, 170, 175), 1, cv2.LINE_AA)
    return lienzo


def anotar_foto(imagen, torres, color, titulo, ancho_destino):
    """Foto original con las siluetas y puntos detectados."""
    img = imagen.copy()
    for n, t in enumerate(torres, 1):
        cv2.polylines(img, [t["poligono"]], True, (0, 255, 255), 2, cv2.LINE_AA)
        p = tuple(int(round(v)) for v in punto_de(t))
        cv2.circle(img, p, 8, BLANCO, -1, cv2.LINE_AA)
        cv2.circle(img, p, 8, color, 2, cv2.LINE_AA)
        cv2.putText(img, str(n), (p[0] + 12, p[1] - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(img, str(n), (p[0] + 12, p[1] - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)

    escala = ancho_destino / img.shape[1]
    img = cv2.resize(img, (ancho_destino, int(img.shape[0] * escala)))

    cv2.rectangle(img, (0, 0), (img.shape[1], 26), (0, 0, 0), -1)
    cv2.putText(img, titulo, (8, 19), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, color, 1, cv2.LINE_AA)
    return img


def apilar(imagenes, horizontal=True):
    """Une imagenes rellenando para que encajen."""
    if horizontal:
        alto = max(i.shape[0] for i in imagenes)
        ajustadas = []
        for i in imagenes:
            relleno = np.full((alto - i.shape[0], i.shape[1], 3),
                              (32, 28, 26), np.uint8)
            ajustadas.append(np.vstack([i, relleno]) if relleno.size else i)
        return np.hstack(ajustadas)

    ancho = max(i.shape[1] for i in imagenes)
    ajustadas = []
    for i in imagenes:
        relleno = np.full((i.shape[0], ancho - i.shape[1], 3),
                          (32, 28, 26), np.uint8)
        ajustadas.append(np.hstack([i, relleno]) if relleno.size else i)
    return np.vstack(ajustadas)


# ==========  PROGRAMA  ==========

def main():
    args = sys.argv[1:]

    if len(args) not in (2, 4):
        print(__doc__)
        return

    modo_clic = len(args) == 2

    if modo_clic:
        prueba_a, prueba_b = args
        calib_a = calib_b = None
    else:
        calib_a, calib_b, prueba_a, prueba_b = args

    for ruta in args:
        if not os.path.exists(ruta):
            raise SystemExit(f"No se encuentra el archivo: {ruta}")

    if not os.path.exists(MODELO):
        raise SystemExit(f"No se encuentra el modelo: {MODELO}")

    model = YOLO(MODELO)

    # --- 1. Deteccion en las fotos de prueba ---
    print("\n--- DETECCION ---")
    img_a, torres_pa = detectar_torres(model, prueba_a)
    img_b, torres_pb = detectar_torres(model, prueba_b)
    print(f"  {os.path.basename(prueba_a)}: {len(torres_pa)} torres")
    print(f"  {os.path.basename(prueba_b)}: {len(torres_pb)} torres")

    # --- 2. Calibracion ---
    if modo_clic:
        print("\n--- CALIBRACION A MANO ---")
        print("  Se abrira cada foto. Haz clic en las 4 esquinas del")
        print("  tablero: arriba-izq, arriba-der, abajo-der, abajo-izq.")
        print("  Luego ENTER. (Z deshace, ESC cancela)")

        H_a = calibrar_a_mano(img_a, "Camara A")
        if H_a is None:
            print("\n  Calibracion cancelada.")
            return

        H_b = calibrar_a_mano(img_b, "Camara B")
        if H_b is None:
            print("\n  Calibracion cancelada.")
            return
    else:
        print("\n--- CALIBRACION AUTOMATICA (posicion inicial) ---")
        _, torres_ca = detectar_torres(model, calib_a)
        _, torres_cb = detectar_torres(model, calib_b)
        print(f"  {os.path.basename(calib_a)}: {len(torres_ca)} torres")
        print(f"  {os.path.basename(calib_b)}: {len(torres_cb)} torres")

        H_a = calibrar(torres_ca, "Camara A")
        H_b = calibrar(torres_cb, "Camara B")

        if H_a is None or H_b is None:
            print("\n  No se pudo calibrar automaticamente.")
            print("  Prueba el modo de dos fotos, marcando las esquinas:")
            print(f"    python3 {os.path.basename(sys.argv[0])} "
                  f"{prueba_a} {prueba_b}")
            return

    print("  Las dos camaras quedaron calibradas.")

    vistas_a = casillas_vistas(torres_pa, H_a)
    vistas_b = casillas_vistas(torres_pb, H_b)

    solo_a = set(vistas_a) - set(vistas_b)
    solo_b = set(vistas_b) - set(vistas_a)
    ambas = set(vistas_a) & set(vistas_b)
    union = set(vistas_a) | set(vistas_b)

    # --- 3. El resultado ---
    print("\n" + "=" * 56)
    print("  COMPLEMENTACION")
    print("=" * 56)
    print(f"  Solo camara A ve:   {len(vistas_a)} torres   "
          f"{sorted(nombre_casilla(*c) for c in vistas_a)}")
    print(f"  Solo camara B ve:   {len(vistas_b)} torres   "
          f"{sorted(nombre_casilla(*c) for c in vistas_b)}")
    print(f"  Las dos juntas:     {len(union)} torres   "
          f"{sorted(nombre_casilla(*c) for c in union)}")
    print()
    print(f"  Vistas por ambas:        {len(ambas):>2}   "
          f"{sorted(nombre_casilla(*c) for c in ambas)}")
    print(f"  B rescata (A no las ve): {len(solo_b):>2}   "
          f"{sorted(nombre_casilla(*c) for c in solo_b)}")
    print(f"  A rescata (B no las ve): {len(solo_a):>2}   "
          f"{sorted(nombre_casilla(*c) for c in solo_a)}")

    mejor_sola = max(len(vistas_a), len(vistas_b))
    ganancia = len(union) - mejor_sola
    print()
    if ganancia > 0:
        print(f"  >> La segunda camara aporta {ganancia} torre(s) que la "
              f"mejor camara sola no detectaba.")
    elif len(union) == mejor_sola and len(union) > 0:
        print("  >> Las dos camaras ven lo mismo. Para que se complementen,")
        print("     separalas mas: angulos opuestos o perpendiculares.")
    else:
        print("  >> No se detecto ninguna torre. Revisa las fotos de prueba.")

    # --- 4. Comparacion visual ---
    def color_a(_):
        return COLOR_A

    def color_b(_):
        return COLOR_B

    def color_union(c):
        if c in ambas:
            return COLOR_AMBAS
        return COLOR_A if c in solo_a else COLOR_B

    tablero_a = vista_tablero("SOLO CAMARA A", vistas_a, color_a,
                              f"{len(vistas_a)} torres")
    tablero_b = vista_tablero("SOLO CAMARA B", vistas_b, color_b,
                              f"{len(vistas_b)} torres")
    tablero_u = vista_tablero(
        "A + B  (union)", union, color_union,
        f"{len(union)} torres   verde=ambas  azul=solo A  naranja=solo B")

    fila_tableros = apilar([tablero_a, tablero_b, tablero_u], horizontal=True)

    foto_a = anotar_foto(img_a, torres_pa, COLOR_A,
                         f"Camara A - {os.path.basename(prueba_a)}",
                         fila_tableros.shape[1] // 2)
    foto_b = anotar_foto(img_b, torres_pb, COLOR_B,
                         f"Camara B - {os.path.basename(prueba_b)}",
                         fila_tableros.shape[1] // 2)
    fila_fotos = apilar([foto_a, foto_b], horizontal=True)

    comparacion = apilar([fila_fotos, fila_tableros], horizontal=False)

    base = os.path.splitext(os.path.basename(prueba_a))[0]
    salida = f"comparacion_{base}.jpg"
    cv2.imwrite(salida, comparacion)
    print(f"\n  Comparacion visual: {salida}")

    # --- 5. CSV ---
    filas = []
    for c in sorted(union):
        origen = ("AB" if c in ambas else "A" if c in solo_a else "B")
        filas.append({
            "casilla": nombre_casilla(*c),
            "vista_por": origen,
            "conf_A": round(vistas_a.get(c, 0.0), 3),
            "conf_B": round(vistas_b.get(c, 0.0), 3),
        })

    if filas:
        with open("complementacion.csv", "w", newline="") as f:
            escritor = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
            escritor.writeheader()
            escritor.writerows(filas)
        print("  Detalle en tabla:   complementacion.csv")


if __name__ == "__main__":
    main()
