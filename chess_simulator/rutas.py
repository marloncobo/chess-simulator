"""Rutas del proyecto independientes del directorio de ejecución."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MODELOS = RAIZ / "modelos"
MODELO = MODELOS / "bestnano.pt"
IMAGENES = RAIZ / "datos" / "imagenes"
CONFIG = RAIZ / "config"
RESULTADOS = RAIZ / "resultados"
OBSERVACION = RAIZ / "datos" / "observacion.json"
