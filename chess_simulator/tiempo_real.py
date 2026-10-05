"""Interfaz de cámara, calibración interactiva y estado temporal con color HSV."""
import json
from pathlib import Path
import time

import cv2
import numpy as np
import pygame

from chess_simulator.captura_vivo import FlujoVivo, leer_ultimo, ultimo
from chess_simulator.rutas import CONFIG
from chess_simulator.seguimiento import SeguimientoPorCasilla
from chess_simulator.tablero_pygame import LADO, CASILLA, dibujar_tablero, dibujar_piezas
from chess_simulator.vision_vivo import FiltroEscena, construir_observacion, homografia


def guardar_calibracion(ruta, source, resolucion, esquinas):
    homografia(esquinas)
    datos = {"source": source, "resolucion": list(resolucion), "esquinas": esquinas}
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    Path(ruta).write_text(json.dumps(datos, indent=2), encoding="utf-8")


def cargar_calibracion(ruta, source, resolucion):
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    if datos.get("source") != source or datos.get("resolucion") != list(resolucion):
        raise ValueError("La calibración pertenece a otra cámara o resolución")
    homografia(datos.get("esquinas"))
    return datos["esquinas"]


def ejecutar(modelo, source=1, backend="auto", punto="base", duracion=None, confianza=.25, parametros_hsv=None):
    pygame.init()
    pantalla = pygame.display.set_mode((1200, 820))
    pygame.display.set_caption(f"Ajedrez en tiempo real · source={source}")
    fuente = pygame.font.SysFont("segoeuisymbol,dejavusans", int(CASILLA*.7))
    texto = pygame.font.SysFont("arial", 17)
    tablero = pygame.Surface((LADO, LADO))
    reloj = pygame.time.Clock()
    flujo = FlujoVivo(modelo, source, backend, punto, confianza, parametros_hsv=parametros_hsv)
    seguimiento = SeguimientoPorCasilla()
    filtro = FiltroEscena()
    frame, congelada, paquete, resultado = None, None, None, None
    esquinas, asignadas = [], []
    resolucion = None
    rect_video = pygame.Rect(10, 100, 540, 540)
    botones = [(pygame.Rect(10+i*135, 660, 125, 32), etiqueta, tecla)
               for i, (etiqueta, tecla) in enumerate((("Recalibrar", pygame.K_r),
                   ("Cargar", pygame.K_l), ("Guardar", pygame.K_g), ("Pausa", pygame.K_SPACE)))]
    estado = f"Abriendo source={source}. Acepte la notificación del celular."
    estado_camara = "Esperando imagen"
    pausa, corriendo = False, True
    recibida, procesada = 0., 0.
    limite_calibracion = 0.
    historial_visible = []
    ultimo_diagnostico = None
    if isinstance(source, str):
        # Una URL no sirve como nombre de archivo; se identifica por su huella.
        import hashlib
        calibracion = CONFIG / f"calibracion_camara_url_{hashlib.sha256(source.encode()).hexdigest()[:12]}.json"
    else:
        calibracion = CONFIG / f"calibracion_camara_{source}.json"
    inicio = time.monotonic()
    # No se cambia a source=0 si el celular no responde.
    print(f"Abriendo únicamente source={source}; acepte la notificación en el celular.", flush=True)
    flujo.iniciar()
    try:
        while corriendo:
            ahora = time.monotonic()
            nuevo = leer_ultimo(flujo.frames)
            if nuevo:
                if "error" in nuevo:
                    estado_camara = nuevo["error"]
                    seguimiento.invalidar("Sin imagen de cámara")
                else:
                    frame, paquete = nuevo["frame"], nuevo
                    recibida = ahora
                    nueva_resolucion = (frame.shape[1], frame.shape[0])
                    if resolucion is not None and resolucion != nueva_resolucion:
                        esquinas, congelada = [], None
                        estado = "Cambió la resolución; marque de nuevo los vértices"
                        seguimiento.invalidar(estado)
                    resolucion = nueva_resolucion
                    estado_camara = f"source={source} · {resolucion[0]}×{resolucion[1]}"
                    if not pausa and congelada is None:
                        ultimo(flujo.pendientes, nuevo)
            for evento in pygame.event.get():
                if evento.type == pygame.MOUSEBUTTONDOWN and evento.button == 1:
                    for rect, _, tecla in botones:
                        if rect.collidepoint(evento.pos):
                            evento = pygame.event.Event(pygame.KEYDOWN, key=tecla)
                            break
                if evento.type == pygame.QUIT:
                    corriendo = False
                elif evento.type == pygame.KEYDOWN:
                    if evento.key == pygame.K_ESCAPE:
                        corriendo = False
                    elif evento.key == pygame.K_SPACE:
                        pausa = not pausa
                        limite_calibracion = ahora
                        filtro = FiltroEscena()
                        seguimiento.invalidar("Pausado" if pausa else "Esperando muestras nuevas")
                    elif evento.key == pygame.K_r:
                        esquinas, congelada, asignadas = [], None, []
                        filtro = FiltroEscena()
                        limite_calibracion = ahora
                        seguimiento.invalidar("Recalibrando; posición conservada")
                        estado = "Marque los cuatro vértices: a8, h8, h1, a1"
                    elif evento.key == pygame.K_s:
                        seguimiento = SeguimientoPorCasilla()
                        limite_calibracion = ahora
                        filtro = FiltroEscena()
                        estado = "Sincronizando la distribución visible"
                    elif evento.key == pygame.K_g and len(esquinas) == 4:
                        try:
                            guardar_calibracion(calibracion, source, resolucion, esquinas)
                            estado = "Calibración guardada (sin fotografías)"
                        except (OSError, ValueError) as error:
                            estado = str(error)
                    elif evento.key == pygame.K_l and resolucion is not None:
                        try:
                            esquinas = cargar_calibracion(calibracion, source, resolucion)
                            congelada = None
                            limite_calibracion = ahora
                            filtro = FiltroEscena()
                            seguimiento.invalidar("Calibración cargada; esperando estabilidad")
                            estado = "Calibración cargada. Si movió el celular, pulse R."
                        except (OSError, ValueError, TypeError, AttributeError) as error:
                            estado = f"No se pudo cargar: {str(error)[:90]}"
                elif evento.type == pygame.MOUSEBUTTONDOWN and evento.button == 1:
                    if frame is not None and rect_video.collidepoint(evento.pos) and len(esquinas) < 4:
                        if congelada is None:
                            congelada = frame.copy()
                        alto, ancho = congelada.shape[:2]
                        x = (evento.pos[0]-rect_video.x)*ancho/rect_video.width
                        y = (evento.pos[1]-rect_video.y)*alto/rect_video.height
                        esquinas.append((x, y))
                        estado = f"Vértices marcados: {len(esquinas)}/4"
                        if len(esquinas) == 4:
                            try:
                                homografia(esquinas)
                                guardar_calibracion(calibracion, source, resolucion, esquinas)
                                congelada = None
                                limite_calibracion = ahora
                                filtro = FiltroEscena()
                                estado = "Calibrado; esperando distribución estable"
                            except (ValueError, OSError) as error:
                                esquinas, congelada = [], None
                                estado = str(error)
            salida = leer_ultimo(flujo.resultados)
            if salida:
                if "error" in salida:
                    estado = salida["error"]
                    seguimiento.invalidar(estado)
                else:
                    resultado = salida
                    procesada = ahora
                    if (not pausa and len(esquinas) == 4 and salida["instante"] > limite_calibracion
                            and ahora-salida["instante"] < 2 and ahora-recibida < 2):
                        obs, vista, asignadas, razones = construir_observacion(
                            salida["detecciones"], esquinas, salida["secuencia"])
                        quieta = filtro.estable(salida["frame"], esquinas)
                        if not quieta:
                            seguimiento.invalidar("Movimiento u oclusión; esperando imagen estable",
                                                  conservar_movimiento=True, ahora=ahora)
                        else:
                            movimiento = seguimiento.recibir(obs, ahora)
                            if movimiento:
                                historial_visible.append(movimiento.texto())
                                print(movimiento.texto(), flush=True)
                        estado = f"Detectadas: {len(salida['detecciones'])} · reflejadas: {sum(bool(p) for f in (seguimiento.posicion or []) for p in f)} · {seguimiento.estado}"
                        if estado != ultimo_diagnostico:
                            print(estado, flush=True)
                            ultimo_diagnostico = estado
                    elif len(esquinas) == 4 and not pausa:
                        seguimiento.invalidar("Resultado antiguo descartado")
            if len(esquinas) != 4:
                seguimiento.invalidar("Falta calibrar los cuatro vértices")
            elif pausa:
                estado = "Pausado · Espacio para continuar"
            elif ahora-recibida > 3:
                seguimiento.invalidar("Sin vídeo reciente; posición conservada")
                estado = seguimiento.estado
            elif procesada and ahora-procesada > 3:
                seguimiento.invalidar("Sin detecciones recientes; posición conservada")
                estado = seguimiento.estado
            pantalla.fill((30, 30, 35))
            imagen = congelada if congelada is not None else frame
            if imagen is not None:
                alto, ancho = imagen.shape[:2]
                escala = min(540/ancho, 560/alto)
                tam = (max(1, round(ancho*escala)), max(1, round(alto*escala)))
                rect_video = pygame.Rect(10, 100, *tam)
                rgb = cv2.cvtColor(cv2.resize(imagen, tam), cv2.COLOR_BGR2RGB)
                pantalla.blit(pygame.image.frombuffer(rgb.tobytes(), tam, "RGB"), rect_video)

                def en_pantalla(p):
                    return (10+round(p[0]*tam[0]/ancho), 100+round(p[1]*tam[1]/alto))

                if len(esquinas) > 1:
                    pygame.draw.lines(pantalla, (50, 220, 130), len(esquinas) == 4,
                                      [en_pantalla(p) for p in esquinas], 2)
                if len(esquinas) == 4:
                    inversa = np.linalg.inv(homografia(esquinas))
                    for n in range(1, 8):
                        for extremos in ([[n,0],[n,8]], [[0,n],[8,n]]):
                            pts = cv2.perspectiveTransform(np.float32(extremos).reshape(-1,1,2), inversa).reshape(-1,2)
                            pygame.draw.line(pantalla, (65,155,150), en_pantalla(pts[0]), en_pantalla(pts[1]), 1)
                for i, p in enumerate(esquinas):
                    xy = en_pantalla(p)
                    pygame.draw.circle(pantalla, (50, 220, 130), xy, 5)
                    pantalla.blit(texto.render(("a8", "h8", "h1", "a1")[i], True, (50, 220, 130)), xy)
                if resultado and ahora-resultado["instante"] < 1 and congelada is None:
                    for d in resultado["detecciones"]:
                        xy = en_pantalla(d["punto"])
                        color = d.get("color", "DUDOSA")
                        tinta = {"BLANCA": (80, 230, 80), "NEGRA": (50, 170, 255)}.get(color, (255, 180, 0))
                        pygame.draw.circle(pantalla, tinta, xy, 4)
                        etiqueta = d["pieza"] + {"BLANCA": " B", "NEGRA": " N"}.get(color, " ?")
                        pantalla.blit(texto.render(etiqueta, True, tinta), xy)
            dibujar_tablero(tablero)
            if seguimiento.posicion is not None:
                dibujar_piezas(tablero, fuente, seguimiento.posicion)
            for fila, col in seguimiento.dudosas:
                pygame.draw.rect(tablero, (245, 150, 40),
                                 (col*CASILLA+2, fila*CASILLA+2, CASILLA-4, CASILLA-4), 3)
            pantalla.blit(tablero, (560, 60))
            for rect, etiqueta, _ in botones:
                pygame.draw.rect(pantalla, (55,75,90), rect, border_radius=4)
                pantalla.blit(texto.render(etiqueta, True, (245,245,245)), (rect.x+10, rect.y+6))
            lineas = [
                (10, 10, estado_camara),
                (10, 35, "Vértices exteriores: a8 > h8 > h1 > a1 (clics)."),
                (10, 60, "R: recalibrar · G: guardar · L: cargar calibración"),
                (560, 10, "POSICIÓN DETECTADA · blancas y negras (HSV)"),
                (10, 712, estado[:130]),
                (10, 738, "Espacio: pausa · S: nueva posición inicial · Esc: cerrar cámara"),
                (10, 792, "Color en cámara: verde = blanca · azul = negra · naranja = dudosa"),
                (10, 766, historial_visible[-1] if historial_visible else "Esperando un movimiento confirmado"),
                (560, 36, f"Inferencia: {resultado['inferencia']*1000:.0f} ms" if resultado else "Cargando detector..."),
            ]
            for x, y, linea in lineas:
                pantalla.blit(texto.render(linea, True, (235, 235, 240)), (x, y))
            pygame.display.flip()
            reloj.tick(30)
            if duracion is not None and ahora-inicio >= duracion:
                corriendo = False
    finally:
        flujo.cerrar()
        pygame.quit()
