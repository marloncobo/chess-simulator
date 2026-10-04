"""Estado y confirmación temporal; independiente de cámara, YOLO y Pygame."""
from dataclasses import dataclass
import math
from chess_simulator.reglas_deteccion import excedentes, tipo

PIEZAS = frozenset("tcardpTCARDP") | frozenset("?" + p for p in "TCARDP")


def indices(casilla):
    if not isinstance(casilla, str) or len(casilla) != 2 or casilla[0] not in "abcdefgh" or casilla[1] not in "12345678":
        raise ValueError("Casilla inválida: use a1–h8")
    return 8 - int(casilla[1]), ord(casilla[0]) - ord("a")


def nombre(fila, columna):
    return "abcdefgh"[columna] + str(8 - fila)


@dataclass(frozen=True)
class Observacion:
    secuencia: int
    tablero: tuple
    completa: bool
    confianza: float
    desconocidas: frozenset = frozenset()
    confianzas: tuple = ()

    @classmethod
    def desde_dict(cls, datos):
        if not isinstance(datos, dict):
            raise ValueError("La observación debe ser un objeto JSON")
        secuencia = datos.get("secuencia")
        if type(secuencia) is not int or secuencia < 0:
            raise ValueError("secuencia debe ser un entero no negativo")
        completa = datos.get("completa")
        if type(completa) is not bool:
            raise ValueError("Indique completa: true o false")
        confianza = datos.get("confianza", 1.0)
        if type(confianza) not in (int, float) or not math.isfinite(confianza) or not 0 <= confianza <= 1:
            raise ValueError("confianza debe estar entre 0 y 1")
        piezas = datos.get("piezas")
        if not isinstance(piezas, list):
            raise ValueError("piezas debe ser una lista")
        tablero = [[""] * 8 for _ in range(8)]
        for item in piezas:
            if not isinstance(item, dict):
                raise ValueError("Cada pieza debe ser un objeto")
            fila, col = indices(item.get("casilla"))
            pieza = item.get("pieza")
            if not isinstance(pieza, str) or pieza not in PIEZAS:
                raise ValueError("Código de pieza inválido; use T/C/A/R/D/P, minúsculas o ?T/?C/?A/?R/?D/?P sin color")
            if tablero[fila][col]:
                raise ValueError("Dos piezas en la misma casilla")
            tablero[fila][col] = pieza
        desconocidas = datos.get("desconocidas", [])
        if not isinstance(desconocidas, list):
            raise ValueError("desconocidas debe ser una lista de casillas")
        desconocidas = frozenset(indices(c) for c in desconocidas)
        if completa and desconocidas:
            raise ValueError("Una observación completa no puede tener casillas desconocidas")
        if any(tablero[f][c] for f, c in desconocidas):
            raise ValueError("Una casilla desconocida no puede contener una pieza confirmada")
        por_casilla = datos.get("confianzas", {})
        if not isinstance(por_casilla, dict):
            raise ValueError("confianzas debe ser un objeto por casilla")
        confianzas = [[float(confianza) if p else 0. for p in fila] for fila in tablero]
        for casilla, valor in por_casilla.items():
            f, c = indices(casilla)
            if type(valor) not in (int, float) or not math.isfinite(valor) or not 0 <= valor <= 1 or not tablero[f][c]:
                raise ValueError("Confianza por casilla inválida")
            confianzas[f][c] = float(valor)
        return cls(secuencia, tuple(tuple(f) for f in tablero), completa, float(confianza),
                   desconocidas, tuple(map(tuple, confianzas)))


@dataclass(frozen=True)
class Movimiento:
    origen: str
    destino: str
    pieza: str
    capturada: str = ""
    tipo: str = "movimiento"

    def texto(self):
        return f"{self.pieza}: {self.origen} -> {self.destino} ({self.tipo})"


def detectar_movimiento(antes, despues, ultimo=None):
    """Reconoce cambios de posición; no es un validador de legalidad de ajedrez."""
    cambios = [(f, c) for f in range(8) for c in range(8) if antes[f][c] != despues[f][c]]
    salidas = [(f, c) for f, c in cambios if antes[f][c] and not despues[f][c]]
    llegadas = [(f, c) for f, c in cambios if despues[f][c]]
    if len(cambios) == 2 and len(salidas) == len(llegadas) == 1:
        fo, co = salidas[0]
        fd, cd = llegadas[0]
        pieza, nueva, capturada = antes[fo][co], despues[fd][cd], antes[fd][cd]
        if capturada and not capturada.startswith("?") and not pieza.startswith("?") and capturada.isupper() == pieza.isupper():
            return None
        promocion = (
            pieza.lower() == "p" and nueva.lower() in "dcat"
            and nueva.isupper() == pieza.isupper()
            and fd == (0 if pieza.isupper() else 7)
            and fo == (1 if pieza.isupper() else 6)
            and abs(cd - co) <= 1
            and bool(capturada) == (cd != co)
        )
        if pieza == nueva or promocion:
            tipo = "promoción" if promocion else ("captura" if capturada else "movimiento")
            return Movimiento(nombre(fo, co), nombre(fd, cd), pieza, capturada, tipo)
    # Enroque: comprobar exactamente las cuatro casillas, sin validar jaque/historial.
    if len(cambios) == 4:
        for fila, rey, torre in ((7, "R", "T"), (0, "r", "t")):
            for origen_t, destino_r, destino_t in ((7, 6, 5), (0, 2, 3)):
                esperado = [list(f) for f in antes]
                if antes[fila][4] != rey or antes[fila][origen_t] != torre:
                    continue
                if any(antes[fila][c] for c in range(min(4, origen_t) + 1, max(4, origen_t))):
                    continue
                esperado[fila][4] = esperado[fila][origen_t] = ""
                esperado[fila][destino_r], esperado[fila][destino_t] = rey, torre
                if tuple(map(tuple, esperado)) == despues:
                    return Movimiento(nombre(fila, 4), nombre(fila, destino_r), rey, tipo="enroque")
    # Captura al paso solo tras un avance doble confirmado del peón rival.
    if len(cambios) == 3 and len(salidas) == 2 and len(llegadas) == 1 and ultimo:
        fd, cd = llegadas[0]
        pieza = despues[fd][cd]
        for fo, co in salidas:
            rival = "p" if pieza == "P" else "P"
            if pieza not in "Pp" or antes[fo][co] != pieza:
                continue
            if fo != (3 if pieza == "P" else 4) or fd - fo != (-1 if pieza == "P" else 1) or abs(cd - co) != 1:
                continue
            if (fo, cd) not in salidas or antes[fo][cd] != rival or antes[fd][cd]:
                continue
            fu, cu = indices(ultimo.origen)
            if ultimo.pieza == rival and ultimo.destino == nombre(fo, cd) and abs(fu - fo) == 2 and cu == cd:
                return Movimiento(nombre(fo, co), nombre(fd, cd), pieza, rival, "captura al paso")
    return None


class Seguimiento:
    def __init__(self, estabilidad=0.4, minimo_muestras=3, timeout=1.5, confianza_minima=0.6,
                 reflejar_observaciones=False):
        self.reflejar_observaciones = reflejar_observaciones
        self.estabilidad = estabilidad
        self.minimo_muestras = minimo_muestras
        self.timeout = timeout
        self.confianza_minima = confianza_minima
        self.posicion = None
        self.historial = []
        self.ultimo_movimiento = None
        self.ultima_secuencia = -1
        self.ultima_recepcion = None
        self.estado = "Esperando observaciones"
        self._limpiar()

    def _limpiar(self):
        self.candidato = None
        self.inicio = None
        self.muestras = 0

    def invalidar(self, mensaje):
        self._limpiar()
        self.estado = mensaje

    def comprobar_conexion(self, ahora):
        if self.ultima_recepcion is not None and ahora - self.ultima_recepcion > self.timeout:
            self.invalidar("Sin datos recientes; posición conservada")

    def recibir(self, observacion, ahora):
        self.comprobar_conexion(ahora)
        if observacion.secuencia <= self.ultima_secuencia:
            return None
        self.ultima_secuencia = observacion.secuencia
        self.ultima_recepcion = ahora
        if not observacion.completa or observacion.confianza < self.confianza_minima:
            self.invalidar("Observación incompleta o poco fiable")
            return None
        tablero = observacion.tablero
        if tablero == self.posicion:
            self.invalidar("Posición confirmada")
            return None
        if tablero != self.candidato:
            self.candidato, self.inicio, self.muestras = tablero, ahora, 1
        else:
            self.muestras += 1
        self.estado = "Esperando estabilidad"
        if self.muestras < self.minimo_muestras or ahora - self.inicio < self.estabilidad:
            return None
        if self.posicion is None:
            self.posicion = tablero
            self.invalidar("Posición inicial sincronizada")
            return None
        movimiento = detectar_movimiento(self.posicion, tablero, self.ultimo_movimiento)
        if movimiento is None and not self.reflejar_observaciones:
            self.estado = "Cambio ambiguo; posición conservada"
            return None
        self.posicion = tablero
        self.ultimo_movimiento = movimiento
        if movimiento is not None:
            self.historial.append(movimiento)
        self.invalidar(movimiento.texto() if movimiento else "Distribución detectada actualizada")
        return movimiento


class SeguimientoPorCasilla(Seguimiento):
    """Confirma las celdas fiables sin bloquearlas por dudas en otras celdas.

    Las celdas desconocidas conservan su último estado. Las ausencias requieren
    más tiempo para no borrar una pieza por un fallo breve de segmentación.
    """
    def __init__(self, estabilidad=.6, minimo_muestras=3, timeout=3, espera_vacio=1.5, ventana_movimiento=10.):
        self.pendientes = {}
        self.dudosas = frozenset()
        self.espera_vacio = espera_vacio
        self.ventana_movimiento = ventana_movimiento
        self.ancla = None
        self.desde_cambio = None
        self.confianzas_confirmadas = {}
        self.torres_descartadas = 0
        self.descartadas = {}
        super().__init__(estabilidad, minimo_muestras, timeout, confianza_minima=.5,
                         reflejar_observaciones=True)

    def _limpiar(self):
        super()._limpiar()
        self.pendientes.clear()

    def invalidar(self, mensaje, conservar_movimiento=False, ahora=None):
        super().invalidar(mensaje)
        if conservar_movimiento:
            # Una imagen reciente con movimiento no es una desconexión.
            if ahora is not None:
                self.ultima_recepcion = ahora
        else:
            self.ancla = self.posicion
            self.desde_cambio = None
            self.ultimo_movimiento = None

    def recibir(self, observacion, ahora, procedencias=None):
        self.comprobar_conexion(ahora)
        if observacion.secuencia <= self.ultima_secuencia:
            return None
        self.ultima_secuencia = observacion.secuencia
        self.ultima_recepcion = ahora
        # Caducidad medida desde el primer cambio, no desde cada fluctuación.
        if self.desde_cambio is not None and ahora-self.desde_cambio > self.ventana_movimiento:
            self.ancla, self.desde_cambio = self.posicion, None
            self.ultimo_movimiento = None
        # Incompleta sin localización de la duda: oclusión general/entrada externa.
        if not observacion.completa and not observacion.desconocidas:
            self.invalidar("Observación incompleta o poco fiable", conservar_movimiento=True)
            return None
        # La confianza se evalúa por casilla: una pieza débil queda en duda sin
        # bloquear la actualización del resto del tablero.
        debiles = frozenset((f, c) for f in range(8) for c in range(8)
                            if observacion.tablero[f][c]
                            and (observacion.confianzas[f][c] if observacion.confianzas
                                 else observacion.confianza) < self.confianza_minima)
        self.dudosas = observacion.desconocidas | debiles
        antes = self.posicion
        nueva = [list(f) for f in antes] if antes is not None else [[""]*8 for _ in range(8)]
        hubo_confirmacion = False
        for f in range(8):
            for c in range(8):
                clave = (f, c)
                if clave in self.dudosas:
                    self.pendientes.pop(clave, None)
                    continue
                pieza = observacion.tablero[f][c]
                if antes is not None and pieza == antes[f][c]:
                    self.confianzas_confirmadas[clave] = (observacion.confianzas[f][c]
                                                         if observacion.confianzas else observacion.confianza)
                    self.pendientes.pop(clave, None)
                    continue
                anterior = self.pendientes.get(clave)
                if anterior is None or anterior[0] != pieza:
                    anterior = (pieza, ahora, 0)
                candidato = (pieza, anterior[1], anterior[2]+1)
                self.pendientes[clave] = candidato
                espera = self.espera_vacio if antes is not None and antes[f][c] and not pieza else self.estabilidad
                # Si el origen también se está vaciando, confirmar el traslado
                # al mismo ritmo evita mostrar la pieza duplicada temporalmente.
                if pieza and not nueva[f][c] and antes is not None:
                    if any(antes[fo][co] == pieza and not observacion.tablero[fo][co]
                           and (fo, co) not in self.dudosas for fo in range(8) for co in range(8)):
                        espera = self.espera_vacio
                minimo = self.minimo_muestras
                if pieza and procedencias is not None and procedencias.get(nombre(f, c)) != "1+2":
                    espera = max(espera, 1.5)
                    minimo = max(minimo, 5)
                if candidato[2] >= minimo and ahora-candidato[1] >= espera:
                    nueva[f][c] = pieza
                    self.confianzas_confirmadas[clave] = (observacion.confianzas[f][c]
                                                         if observacion.confianzas else observacion.confianza)
                    hubo_confirmacion = True
                    self.pendientes.pop(clave)
        # El filtro por fotograma no basta: piezas retenidas de observaciones
        # anteriores pueden sumarse a nuevas detecciones y superar los topes.
        def prioridad(celda):
            f, c = celda
            pieza = nueva[f][c]
            return (celda in self.dudosas or tipo(observacion.tablero[f][c]) != tipo(pieza),
                    -self.confianzas_confirmadas.get(celda, 0.),
                    not (antes is not None and tipo(antes[f][c]) == tipo(pieza)), celda)
        exceso = excedentes((((f, c), nueva[f][c]) for f in range(8) for c in range(8)
                             if nueva[f][c]), prioridad)
        sobrantes = sorted(exceso)
        self.descartadas = {nombre(f, c): motivo for (f, c), motivo in exceso.items()}
        self.torres_descartadas = sum(tipo(nueva[f][c]) == "T" for f, c in sobrantes)
        for f, c in sobrantes:
            nueva[f][c] = ""
            self.pendientes.pop((f, c), None)
        if sobrantes:
            self.dudosas = self.dudosas | frozenset(sobrantes)
            hubo_confirmacion = True
        despues = tuple(map(tuple, nueva))
        movimiento = None
        if hubo_confirmacion and despues != antes:
            self.posicion = despues
            if antes is None:
                self.ancla = despues
            else:
                if self.ancla is None:
                    self.ancla = antes
                movimiento = detectar_movimiento(self.ancla, despues, self.ultimo_movimiento) if not sobrantes else None
                if sobrantes:
                    self.ancla = despues
                    self.ultimo_movimiento = None
                if movimiento and not any(
                    celda in self.dudosas for celda in (indices(movimiento.origen), indices(movimiento.destino))
                ):
                    self.historial.append(movimiento)
                    self.ultimo_movimiento = movimiento
                    self.ancla = despues
                else:
                    movimiento = None
                if movimiento or sobrantes:
                    self.desde_cambio = None
                elif self.desde_cambio is None:
                    self.desde_cambio = ahora
        self.estado = (f"{len(self.dudosas)} casillas dudosas; el resto se actualiza" if self.dudosas
                       else ("Confirmando cambios por casilla" if self.pendientes else
                             "Esperando completar el movimiento" if self.desde_cambio is not None else "Posición confirmada"))
        return movimiento
