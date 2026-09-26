"""Contrato JSON para integrar un productor externo, sin extraer coordenadas."""
import json
import os
from pathlib import Path
import tempfile
import time

from seguimiento import Observacion, nombre


def crear_observacion(posicion, secuencia, completa=True, confianza=1.0):
    return {
        "secuencia": secuencia,
        "completa": completa,
        "confianza": confianza,
        "piezas": [
            {"casilla": nombre(f, c), "pieza": posicion[f][c]}
            for f in range(8) for c in range(8) if posicion[f][c]
        ],
    }


def publicar(ruta, datos):
    """Publicación atómica para que Pygame nunca lea medio documento."""
    Observacion.desde_dict(datos)
    ruta = Path(ruta)
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=ruta.parent, delete=False) as archivo:
            temporal = archivo.name
            json.dump(datos, archivo, ensure_ascii=False)
        # Windows puede negar el reemplazo mientras el consumidor tiene abierto
        # el archivo. Reintentos breves, sin exponer un documento parcial.
        for intento in range(10):
            try:
                os.replace(temporal, ruta)
                break
            except PermissionError:
                if intento == 9:
                    raise
                time.sleep(0.01)
    finally:
        if temporal and os.path.exists(temporal):
            os.unlink(temporal)


class EntradaArchivo:
    def __init__(self, ruta):
        self.ruta = Path(ruta)

    def leer(self):
        # Un único documento pequeño: la última observación, no un historial.
        if self.ruta.stat().st_size > 65536:
            raise ValueError("La observación supera 64 KB")
        with self.ruta.open(encoding="utf-8") as archivo:
            return Observacion.desde_dict(json.load(archivo))
