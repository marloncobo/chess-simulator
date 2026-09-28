"""
Prueba de complementacion entre dos camaras - TODAS LAS PIEZAS.

QUE DEMUESTRA
-------------
Que lo que una camara no ve por oclusion, la otra si. Compara tres
resultados sobre la misma posicion del tablero:

    solo camara A      lo que ve A por su cuenta
    solo camara B      lo que ve B por su cuenta
    A + B              la union, que es lo que se busca

Y dice explicitamente cuantas piezas rescata cada una.

COMO SE COMPARAN DOS FOTOS DISTINTAS
------------------------------------
Cada foto da coordenadas en pixeles de SU imagen, y esas no se
pueden comparar entre si. Marcando las 4 esquinas del tablero se
calcula una homografia por foto, que traduce pixeles a CASILLAS.

A partir de ahi las dos hablan el mismo idioma:

    foto A dice:  a1=TOWER, e4=PAWN, h1=TOWER
    foto B dice:  a1=TOWER,           h1=TOWER, a8=QUEEN

y la comparacion es directa.

CUANDO LAS DOS DISCREPAN
------------------------
Si ambas ven pieza en la misma casilla pero la clasifican distinto
(A dice PAWN, B dice BISHOP), se toma la de mayor confianza y la
casilla queda marcada con "!" en el informe. Son los casos que vale
la pena revisar a mano.

NO HACEN FALTA DOS CAMARAS PARA PROBARLO
----------------------------------------
Basta un celular: se toman las fotos desde dos posiciones distintas
sin mover el tablero. Para el analisis es lo mismo que dos camaras
fijas.

DOS FORMAS DE USARLO
--------------------

  A) CON DOS FOTOS  (lo mas rapido)

        python3 probar_dos_camaras.py fotoA.jpg fotoB.jpg

     Se abre cada foto y se hace clic en las 4 esquinas del tablero,
     en este orden: arriba-izquierda, arriba-derecha, abajo-derecha,
     abajo-izquierda. Funciona con las piezas en cualquier posicion.

  B) CON CUATRO FOTOS  (calibracion automatica)

        python3 probar_dos_camaras.py calibA.jpg calibB.jpg pruebaA.jpg pruebaB.jpg

     Las dos primeras, del tablero en POSICION INICIAL: la
     calibracion sale de las 4 torres de las esquinas, sin clics.
     Las dos ultimas son la posicion que se quiere medir, desde los
     mismos dos sitios.

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
CONFIANZA = 0.25
USAR_BASE = True      # la base de la mascara suele caer mejor en la casilla
CASILLA = 80
LADO = CASILLA * 8

# Clase que se usa para calibrar automaticamente (modo de 4 fotos)
CLASE_ESQUINA = "TOWER"

# Etiqueta corta de cada pieza para dibujarla en el tablero.
# Si el modelo usa otros nombres, se toman sus 2 primeras letras.
ABREVIATURA = {
    "KING": "R", "QUEEN": "D", "TOWER": "T", "ROOK": "T",
    "BISHOP": "A", "HORSE": "C", "KNIGHT": "C", "PAWN": "P",
}

# Color por tipo de pieza (BGR)
COLOR_PIEZA = {
    "KING":   (80, 80, 255),
    "QUEEN":  (200, 80, 255),
    "TOWER":  (255, 170, 90),
    "ROOK":   (255, 170, 90),
    "BISHOP": (90, 220, 255),
    "HORSE":  (120, 255, 160),
    "KNIGHT": (120, 255, 160),
    "PAWN":   (200, 200, 200),
}
COLOR_OTRA = (180, 160, 255)

# Origen de la deteccion
COLOR_A = (255, 170, 90)       # azul
COLOR_B = (90, 140, 255)       # naranja
COLOR_AMBAS = (130, 220, 120)  # verde
COLOR_CONFLICTO = (80, 80, 255)  # rojo

BLANCO = (255, 255, 255)
GRIS = (110, 110, 115)
# -------------------------


def abreviar(clase):
    return ABREVIATURA.get(clase.upper(), clase[:2].upper())


def color_de(clase):
    return COLOR_PIEZA.get(clase.upper(), COLOR_OTRA)


# ==========  DETECCION  ==========

def detectar(model, ruta):
    """Centro de masa, base y CLASE de cada pieza detectada."""
    imagen = cv2.imread(ruta)
    if imagen is None:
        raise SystemExit(f"No se pudo abrir: {ruta}")

    resultado = model(ruta, conf=CONFIANZA, verbose=False)[0]
    piezas = []

    if resultado.masks is not None:
        for i, poligono in enumerate(resultado.masks.xy):
            puntos = np.array(poligono, dtype=np.int32)
            M = cv2.moments(puntos)
            if M["m00"] == 0:
                continue

            cx = M["m10"] / M["m00"]
            piezas.append({
                "clase": model.names[int(resultado.boxes.cls[i])],
                "centro": (cx, M["m01"] / M["m00"]),
                "base": (cx, float(puntos[:, 1].max())),
                "conf": float(resultado.boxes.conf[i]),
                "poligono": puntos,
            })

    piezas.sort(key=lambda p: (p["centro"][1], p["centro"][0]))
    return imagen, piezas


def punto_de(pieza):
    return pieza["base"] if USAR_BASE else pieza["centro"]


def resumen_clases(piezas):
    conteo = {}
    for p in piezas:
        conteo[p["clase"]] = conteo.get(p["clase"], 0) + 1
    return "  ".join(f"{k}:{v}" for k, v in sorted(conteo.items())) or "-"


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


def calibrar_por_torres(piezas, etiqueta):
    """
    Homografia a partir de las 4 torres de esquina (posicion inicial).
    Sus centros estan a media casilla de cada borde, no en el borde.
    """
    torres = [p for p in piezas if p["clase"].upper() == CLASE_ESQUINA]

    if len(torres) != 4:
        print(f"  [!] {etiqueta}: se detectaron {len(torres)} "
              f"{CLASE_ESQUINA}, hacen falta exactamente 4.")
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
    Sirve con las piezas en cualquier posicion.
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
            cv2.polylines(vista, [np.array(puntos, np.int32)],
                          len(puntos) == 4, (255, 0, 255), 2, cv2.LINE_AA)

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
        if tecla == 27:
            cv2.destroyWindow(ventana)
            return None
        if tecla in (ord("z"), ord("Z")) and puntos:
            puntos.pop()
            redibujar()
        if tecla in (13, 10) and len(puntos) == 4:
            break

    cv2.destroyWindow(ventana)

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


def casillas_vistas(piezas, H):
    """
    {casilla: {"clase":, "conf":}} de lo que ve una camara.

    En una casilla solo cabe una pieza, asi que si dos detecciones
    caen en la misma se conserva la de mayor confianza.
    """
    vistas = {}
    for p in piezas:
        c = a_casilla(punto_de(p), H)
        if c is None:
            continue
        previo = vistas.get(c)
        if previo is None or p["conf"] > previo["conf"]:
            vistas[c] = {"clase": p["clase"], "conf": p["conf"]}
    return vistas


def fusionar(vistas_a, vistas_b):
    """
    Une lo que ve cada camara.

    Si ambas ven la misma casilla pero con clases distintas, gana la
    de mayor confianza y la casilla queda marcada como conflicto.
    """
    fusion = {}

    for c in set(vistas_a) | set(vistas_b):
        a, b = vistas_a.get(c), vistas_b.get(c)

        if a and b:
            if a["clase"] == b["clase"]:
                fusion[c] = {"clase": a["clase"],
                             "conf": max(a["conf"], b["conf"]),
                             "origen": "AB", "conflicto": False}
            else:
                gana = a if a["conf"] >= b["conf"] else b
                fusion[c] = {"clase": gana["clase"], "conf": gana["conf"],
                             "origen": "AB", "conflicto": True,
                             "clase_a": a["clase"], "clase_b": b["clase"]}
        elif a:
            fusion[c] = {**a, "origen": "A", "conflicto": False}
        else:
            fusion[c] = {**b, "origen": "B", "conflicto": False}

    return fusion


# ==========  DIBUJO  ==========

def vista_tablero(titulo, casillas, color_origen, subtitulo=""):
    """
    Tablero 8x8 con las casillas ocupadas.

    El borde indica QUIEN la vio (A, B o ambas) y la letra del centro
    QUE pieza es.
    """
    alto_cab = 54
    lienzo = np.full((LADO + alto_cab, LADO, 3), (32, 28, 26), np.uint8)

    for fila in range(8):
        for col in range(8):
            color = (235, 215, 180) if (fila + col) % 2 == 0 else (96, 150, 118)
            cv2.rectangle(lienzo,
                          (col * CASILLA, alto_cab + fila * CASILLA),
                          ((col + 1) * CASILLA, alto_cab + (fila + 1) * CASILLA),
                          color, -1)

    for c, datos in sorted(casillas.items()):
        fila, col = c
        x0, y0 = col * CASILLA, alto_cab + fila * CASILLA
        borde = color_origen(c, datos)
        relleno = color_de(datos["clase"])

        zona = lienzo[y0:y0 + CASILLA, x0:x0 + CASILLA]
        tinte = np.full_like(zona, relleno, dtype=np.uint8)
        lienzo[y0:y0 + CASILLA, x0:x0 + CASILLA] = cv2.addWeighted(
            zona, 0.55, tinte, 0.45, 0)

        grosor = 4 if datos.get("conflicto") else 3
        cv2.rectangle(lienzo, (x0, y0), (x0 + CASILLA, y0 + CASILLA),
                      borde, grosor)

        letra = abreviar(datos["clase"])
        if datos.get("conflicto"):
            letra += "!"

        (tw, th), _ = cv2.getTextSize(letra, cv2.FONT_HERSHEY_SIMPLEX,
                                      0.95, 2)
        px = x0 + (CASILLA - tw) // 2
        py = y0 + (CASILLA + th) // 2
        cv2.putText(lienzo, letra, (px, py), cv2.FONT_HERSHEY_SIMPLEX,
                    0.95, (0, 0, 0), 5, cv2.LINE_AA)
        cv2.putText(lienzo, letra, (px, py), cv2.FONT_HERSHEY_SIMPLEX,
                    0.95, BLANCO, 2, cv2.LINE_AA)

        etiqueta = nombre_casilla(fila, col)
        cv2.putText(lienzo, etiqueta, (x0 + 5, y0 + 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(lienzo, etiqueta, (x0 + 5, y0 + 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, BLANCO, 1, cv2.LINE_AA)

    for i in range(9):
        p = i * CASILLA
        cv2.line(lienzo, (p, alto_cab), (p, alto_cab + LADO), GRIS, 1)
        cv2.line(lienzo, (0, alto_cab + p), (LADO, alto_cab + p), GRIS, 1)

    cv2.putText(lienzo, titulo, (12, 26), cv2.FONT_HERSHEY_SIMPLEX,
                0.72, BLANCO, 2, cv2.LINE_AA)
    if subtitulo:
        cv2.putText(lienzo, subtitulo, (12, 46), cv2.FONT_HERSHEY_SIMPLEX,
                    0.42, (170, 170, 175), 1, cv2.LINE_AA)
    return lienzo


def anotar_foto(imagen, piezas, color, titulo, ancho_destino):
    """Foto original con las siluetas, puntos y clase de cada pieza."""
    img = imagen.copy()

    for p in piezas:
        c = color_de(p["clase"])
        cv2.polylines(img, [p["poligono"]], True, c, 2, cv2.LINE_AA)
        punto = tuple(int(round(v)) for v in punto_de(p))
        cv2.circle(img, punto, 7, BLANCO, -1, cv2.LINE_AA)
        cv2.circle(img, punto, 7, c, 2, cv2.LINE_AA)

        letra = abreviar(p["clase"])
        cv2.putText(img, letra, (punto[0] + 10, punto[1] - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(img, letra, (punto[0] + 10, punto[1] - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, c, 2, cv2.LINE_AA)

    escala = ancho_destino / img.shape[1]
    img = cv2.resize(img, (ancho_destino, int(img.shape[0] * escala)))

    cv2.rectangle(img, (0, 0), (img.shape[1], 26), (0, 0, 0), -1)
    cv2.putText(img, titulo, (8, 19), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, color, 1, cv2.LINE_AA)
    return img


def apilar(imagenes, horizontal=True):
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

    # --- 1. Deteccion ---
    print("\n--- DETECCION ---")
    img_a, piezas_a = detectar(model, prueba_a)
    img_b, piezas_b = detectar(model, prueba_b)
    print(f"  {os.path.basename(prueba_a)}: {len(piezas_a)} piezas   "
          f"{resumen_clases(piezas_a)}")
    print(f"  {os.path.basename(prueba_b)}: {len(piezas_b)} piezas   "
          f"{resumen_clases(piezas_b)}")

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
        _, cal_pa = detectar(model, calib_a)
        _, cal_pb = detectar(model, calib_b)
        H_a = calibrar_por_torres(cal_pa, "Camara A")
        H_b = calibrar_por_torres(cal_pb, "Camara B")

        if H_a is None or H_b is None:
            print("\n  No se pudo calibrar automaticamente.")
            print("  Prueba el modo de dos fotos, marcando las esquinas:")
            print(f"    python3 {os.path.basename(sys.argv[0])} "
                  f"{prueba_a} {prueba_b}")
            return

    print("  Las dos camaras quedaron calibradas.")

    # --- 3. A casillas y fusion ---
    vistas_a = casillas_vistas(piezas_a, H_a)
    vistas_b = casillas_vistas(piezas_b, H_b)
    fusion = fusionar(vistas_a, vistas_b)

    solo_a = {c for c in vistas_a if c not in vistas_b}
    solo_b = {c for c in vistas_b if c not in vistas_a}
    ambas = set(vistas_a) & set(vistas_b)
    conflictos = {c for c, d in fusion.items() if d.get("conflicto")}

    def listar(conjunto):
        return sorted(
            f"{nombre_casilla(*c)}={abreviar(fusion[c]['clase'])}"
            for c in conjunto)

    # --- 4. Informe ---
    print("\n" + "=" * 60)
    print("  COMPLEMENTACION")
    print("=" * 60)
    print(f"  Solo camara A ve:  {len(vistas_a):>2} piezas")
    print(f"  Solo camara B ve:  {len(vistas_b):>2} piezas")
    print(f"  Las dos juntas:    {len(fusion):>2} piezas")
    print()
    print(f"  Vistas por ambas:        {len(ambas):>2}")
    print(f"  B rescata (A no las ve): {len(solo_b):>2}   {listar(solo_b)}")
    print(f"  A rescata (B no las ve): {len(solo_a):>2}   {listar(solo_a)}")

    if conflictos:
        print()
        print(f"  Discrepancias de clase:  {len(conflictos):>2}")
        for c in sorted(conflictos):
            d = fusion[c]
            print(f"     {nombre_casilla(*c)}: A dice {d['clase_a']}, "
                  f"B dice {d['clase_b']}  ->  se toma {d['clase']} "
                  f"(conf {d['conf']:.2f})")

    mejor_sola = max(len(vistas_a), len(vistas_b))
    ganancia = len(fusion) - mejor_sola
    print()
    if ganancia > 0:
        print(f"  >> La segunda camara aporta {ganancia} pieza(s) que la "
              f"mejor camara sola no detectaba.")
    elif len(fusion) == mejor_sola and len(fusion) > 0:
        print("  >> Las dos camaras ven lo mismo. Para que se complementen,")
        print("     separalas mas: angulos opuestos o perpendiculares.")
    else:
        print("  >> No se detecto ninguna pieza. Revisa las fotos.")

    # --- 5. Comparacion visual ---
    def origen_a(c, d):
        return COLOR_A

    def origen_b(c, d):
        return COLOR_B

    def origen_union(c, d):
        if d.get("conflicto"):
            return COLOR_CONFLICTO
        if d["origen"] == "AB":
            return COLOR_AMBAS
        return COLOR_A if d["origen"] == "A" else COLOR_B

    tablero_a = vista_tablero("SOLO CAMARA A", vistas_a, origen_a,
                              f"{len(vistas_a)} piezas")
    tablero_b = vista_tablero("SOLO CAMARA B", vistas_b, origen_b,
                              f"{len(vistas_b)} piezas")
    tablero_u = vista_tablero(
        "A + B  (union)", fusion, origen_union,
        f"{len(fusion)} piezas   verde=ambas  azul=solo A  "
        f"naranja=solo B  rojo=discrepan")

    fila_tableros = apilar([tablero_a, tablero_b, tablero_u], horizontal=True)

    foto_a = anotar_foto(img_a, piezas_a, COLOR_A,
                         f"Camara A - {os.path.basename(prueba_a)}",
                         fila_tableros.shape[1] // 2)
    foto_b = anotar_foto(img_b, piezas_b, COLOR_B,
                         f"Camara B - {os.path.basename(prueba_b)}",
                         fila_tableros.shape[1] // 2)
    fila_fotos = apilar([foto_a, foto_b], horizontal=True)

    comparacion = apilar([fila_fotos, fila_tableros], horizontal=False)

    base = os.path.splitext(os.path.basename(prueba_a))[0]
    salida = f"comparacion_{base}.jpg"
    cv2.imwrite(salida, comparacion)
    print(f"\n  Comparacion visual: {salida}")

    # --- 6. CSV ---
    filas = []
    for c in sorted(fusion):
        d = fusion[c]
        a, b = vistas_a.get(c), vistas_b.get(c)
        filas.append({
            "casilla": nombre_casilla(*c),
            "pieza": d["clase"],
            "vista_por": d["origen"],
            "discrepan": "si" if d.get("conflicto") else "no",
            "clase_A": a["clase"] if a else "",
            "conf_A": round(a["conf"], 3) if a else "",
            "clase_B": b["clase"] if b else "",
            "conf_B": round(b["conf"], 3) if b else "",
        })

    if filas:
        with open("complementacion.csv", "w", newline="") as f:
            escritor = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
            escritor.writeheader()
            escritor.writerows(filas)
        print("  Detalle en tabla:   complementacion.csv")


if __name__ == "__main__":
    main()
