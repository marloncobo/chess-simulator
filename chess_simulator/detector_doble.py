"""Un modelo en un proceso separado para inferir pares de imágenes."""
from queue import Empty
import time

from chess_simulator.captura_vivo import ultimo, leer_ultimo


def inferir_par(modelo, entrada, salida, parar, confianza=.5):
    salida.cancel_join_thread()
    try:
        from ultralytics import YOLO
        from chess_simulator.vision_vivo import extraer
        red = YOLO(str(modelo))
        if red.task != "segment":
            raise ValueError("El modelo debe ser de segmentacion")
        ultimo(salida, {"listo": True})
        while not parar.is_set():
            try:
                trabajo = entrada.get(timeout=.2)
            except Empty:
                continue
            reciente = leer_ultimo(entrada)
            if reciente is not None:
                trabajo = reciente
            inicio = time.monotonic()
            imagenes = [p["frame"] for p in trabajo["paquetes"]]
            resultados = red(imagenes, conf=confianza, max_det=64, verbose=False)
            vistas = [{**p, "detecciones": extraer(r, p["frame"])}
                      for p, r in zip(trabajo["paquetes"], resultados)]
            ultimo(salida, {"revision": trabajo["revision"], "vistas": vistas,
                            "inferencia": time.monotonic() - inicio})
    except Exception as error:
        ultimo(salida, {"error": f"Detector: {error}"})
