"""Formato compartido de calibración y perfiles físicos, sin interfaz gráfica."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from chess_simulator.coordenadas_tablero import TableroFisico
from chess_simulator.rutas import CONFIG
from chess_simulator.vision_vivo import homografia

VERSION = 1


def ruta_calibracion(source, directorio=None):
    identidad = hashlib.sha256(json.dumps(source).encode()).hexdigest()[:16]
    return Path(directorio or CONFIG) / f"calibracion_{identidad}.json"


def _leer(ruta):
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    if not isinstance(datos, dict):
        raise ValueError("El perfil debe ser un objeto JSON")
    return datos


def _escribir(ruta, datos):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def cargar_tablero(ruta):
    return TableroFisico.desde_dict(_leer(ruta))


def guardar_tablero(ruta, tablero):
    _escribir(ruta, tablero.a_dict())


def _validar_geometria(resolucion, esquinas):
    if (not isinstance(resolucion, (list, tuple)) or len(resolucion) != 2
            or any(type(v) is not int or v <= 0 for v in resolucion)):
        raise ValueError("Resolución inválida")
    try:
        homografia(esquinas)
        if any(not (0 <= x <= resolucion[0] and 0 <= y <= resolucion[1]) for x, y in esquinas):
            raise ValueError("Vértices fuera de la resolución")
    except (TypeError, OverflowError) as error:
        raise ValueError("Vértices inválidos") from error


def guardar_calibracion(ruta, source, resolucion, esquinas, tablero=None, contexto=None):
    """contexto identifica montaje, orientación, lente, zoom y recorte del operador."""
    _validar_geometria(resolucion, esquinas)
    _escribir(ruta, {"version": VERSION, "fecha": datetime.now(timezone.utc).isoformat(),
                    "source": source, "resolucion": list(resolucion),
                    "esquinas": [list(map(float, p)) for p in esquinas],
                    "tablero": tablero.a_dict() if tablero else None,
                    "contexto": contexto})


def cargar_calibracion(ruta, source, resolucion, tablero=None, contexto=None, *, legado_doble=False):
    datos = _leer(ruta)
    version = datos.get("version")
    if version is not None and (type(version) is not int or version != VERSION):
        raise ValueError("Versión de calibración no compatible")
    # El formato doble antiguo identifica la fuente únicamente en su ruta hash.
    if datos.get("source") != source and not (version is None and legado_doble and "source" not in datos):
        raise ValueError("La calibración pertenece a otra cámara o resolución")
    if resolucion is None or datos.get("resolucion") != list(resolucion):
        raise ValueError("La calibración pertenece a otra cámara o resolución")
    _validar_geometria(resolucion, datos.get("esquinas"))
    asociado = datos.get("tablero")
    if asociado is not None:
        asociado = TableroFisico.desde_dict(asociado)
    if tablero is not None:
        if asociado is None:
            raise ValueError("Perfil antiguo sin medidas: recalibre y guarde con el tablero físico")
        if asociado != tablero:
            raise ValueError("El tablero o sus dimensiones cambiaron; recalibre")
    if datos.get("contexto") != contexto:
        raise ValueError("Cambió el montaje, lente, orientación, zoom o recorte; recalibre")
    return datos["esquinas"]


def cargar_camara(source, resolucion, tablero=None, contexto=None, *, modo="simple", directorio=None):
    """Lee primero el formato común; solo busca legado si aún no existe."""
    directorio = Path(directorio or CONFIG)
    ruta = ruta_calibracion(source, directorio)
    if ruta.exists():
        return cargar_calibracion(ruta, source, resolucion, tablero, contexto)
    if modo == "doble":
        identidad = hashlib.sha256(str(source).encode()).hexdigest()[:16]
        ruta = directorio / f"calibracion_doble_{identidad}.json"
    elif isinstance(source, str):
        identidad = hashlib.sha256(source.encode()).hexdigest()[:12]
        ruta = directorio / f"calibracion_camara_url_{identidad}.json"
    else:
        ruta = directorio / f"calibracion_camara_{source}.json"
    return cargar_calibracion(ruta, source, resolucion, tablero, contexto, legado_doble=modo == "doble")
