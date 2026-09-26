# Tablero virtual y seguimiento

## Cámara en vivo: actualización por casilla

```powershell
.\.venv\Scripts\python.exe main.py --camara --source 1
```

El modo cámara procesa las seis clases sin distinguir color. Marque los cuatro
vértices o pulse Cargar si el celular y el tablero no se han movido desde la última
calibración. La captura usa source=1; no cambia automáticamente a la cámara 0.

Las detecciones se agrupan por casilla. Duplicados del mismo tipo y con apoyos muy
próximos se reducen a uno; una clasificación distinta solo se descarta si coincide
el apoyo y la diferencia de confianza es clara. Los conflictos restantes y las
detecciones con confianza menor de 0.5 se marcan como desconocidos para esa casilla.

Cada casilla se confirma independientemente: una duda ya no bloquea las otras 63.
La restricción del prototipo de **máximo cuatro torres** se comparte con el modo
fotografía. Se aplica después de agrupar duplicados por casilla y conserva las
cuatro detecciones de torre con mayor confianza. Las sobrantes se marcan como
dudosas, sin inventar que son peones u otra clase. El estado acumulado también
respeta el máximo, incluyendo piezas retenidas de fotogramas anteriores.
Un borde naranja señala una casilla dudosa; conserva su última pieza confirmada,
o queda sin pieza si todavía no tiene una. Los cambios requieren al menos tres
muestras nuevas y 0.6 segundos; las desapariciones esperan 1.5 segundos. La
oclusión general o pérdida de vídeo conserva la posición. El contador distingue
objetos detectados de piezas reflejadas; varias detecciones pueden ser duplicados.

No se rellenan posiciones por reglas ni se recolocan detecciones conflictivas en
casillas vecinas. Las oclusiones y errores de clasificación persistentes aún pueden
requerir ajustar la cámara/calibración. Para cargar cambios de código, cierre la
ventana anterior y vuelva a ejecutar el programa.

## Punto de entrada: main.py

Para conectar la detección de torres ya disponible con Pygame, ejecute:

```powershell
.\.venv\Scripts\python.exe main.py
```

Seleccione una fotografía. También puede pasarla directamente:

```powershell
.\.venv\Scripts\python.exe main.py --imagen pruebas/torres4.jpeg
```

Se carga `bestnano.pt` junto a main.py (o `--modelo ruta.pt`) y se reutilizan
`centros_de_masa` y `limitar_torres` de torres.py, sin sobrescribir imágenes ni CSV.
La inferencia se ejecuta en un trabajador para mantener la ventana receptiva.

En la fotografía, marque los cuatro vértices del área de las 64 casillas, en orden:
extremo de a8, extremo de h8, extremo de h1, extremo de a1. Son los vértices del
tablero, NO las posiciones de las torres. R borra la calibración para repetirla.
La transformación de perspectiva asigna los centroides existentes a casillas y las
dibuja a la derecha. Las piezas fuera del tablero se informan; las colisiones entre
dos detecciones en una casilla impiden presentar una distribución engañosa.

Esta vista muestra SOLO torres y usa gris para indicar que su color es desconocido.
No rellena el resto de piezas ni asume su posición inicial. El marcador `?` es local
a esta vista: no se publica como observación completa de una partida.

La homografía corrige la perspectiva del plano, pero no el desplazamiento del
centro de la silueta respecto al apoyo de una pieza alta. Con fotos inclinadas puede
asignar una casilla equivocada; esta vista permite comprobar ese problema antes de
integrar vídeo. El CSV antiguo de esquinas no se usa automáticamente.

Una fotografía se procesa una sola vez: no se repite como si fueran observaciones
independientes para cumplir la estabilidad temporal. El seguimiento real existente
se abre desde el mismo punto de entrada con:

```powershell
.\.venv\Scripts\python.exe main.py --entrada observacion.json
```

El modo imagen usa OpenCV, NumPy y Ultralytics del entorno del detector, además de
Pygame. Para vídeo use `--camara`; ambos modos muestran piezas sin determinar color.

También se conserva un modo de entrada JSON independiente: `tablero_pygame.py`
consume observaciones externas sin abrir cámara ni ejecutar YOLO. `main.py` coordina
los modos de imagen, cámara y entrada externa.

## Ejecución en Windows

Desde esta carpeta, con el entorno existente:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-ui.txt
.\.venv\Scripts\python.exe tablero_pygame.py
```

El tablero empieza sin piezas: no hay una posición inicial fija ni movimientos por
ratón. Espera `observacion.json` junto al programa, o la ruta indicada con `--entrada`.
La primera distribución proviene íntegramente del detector. Cada distribución completa
se confirma después de al menos 3 muestras nuevas y 0.4 segundos de estabilidad.
También se reflejan adiciones, retiradas y redistribuciones de piezas, sin exigir que
formen una jugada. Las observaciones parciales conservan la última posición confirmada.
`R` reinicia la sincronización y borra el historial; `Esc` cierra la ventana.

## Conectar el trabajo de extracción

Contrato provisional: **una fotografía lógica completa del tablero**, ya convertida
a casillas, por cada muestra. No se necesitan identificadores persistentes de piezas.

```json
{
  "secuencia": 1,
  "completa": true,
  "confianza": 0.95,
  "piezas": [
    {"casilla": "a1", "pieza": "T"},
    {"casilla": "h8", "pieza": "t"}
  ]
}
```

Este ejemplo representa un tablero con SOLO dos torres: las casillas omitidas se
consideran vacías. NO envíe solo las torres como observación completa si en el tablero
hay otras piezas que también deben representarse. Las mayúsculas indican blancas
y las minúsculas negras; el prefijo `?` indica color desconocido (por ejemplo `?T`).
Códigos: T torre, C caballo, A alfil, D dama, R rey, P peón. a8 corresponde a fila 0,
columna 0; a1 a fila 7, columna 0.

La secuencia debe aumentar en cada muestra nueva, incluso cuando no cambia ninguna
pieza. Releer el mismo archivo no cuenta como una muestra nueva. Use, por ejemplo,
`time.time_ns()` como secuencia al publicar; un contador que se reinicia requiere
resincronizar también el consumidor con R. La estabilidad usa tiempo monotónico local.
El productor debe publicar observaciones recientes; no reproduzca una cola atrasada.

Ante oclusión, cámara desconectada o detecciones parciales, publique `completa: false`.
Una ausencia de detección NO demuestra que una casilla esté vacía. Confianza inferior
a 0.6 también cancela la confirmación pendiente. Tras 1.5 segundos sin secuencias
nuevas se conserva la posición y se muestra la pérdida de datos.

El productor puede importar `entrada.publicar(ruta, datos)` para escribir de forma
atómica; `entrada.crear_observacion(matriz, secuencia)` convierte una matriz 8×8 al
contrato. Si ambos componentes comparten proceso, puede llamar directamente a
`Seguimiento(reflejar_observaciones=True)` y llamar a
`recibir(Observacion.desde_dict(datos), time.monotonic())` sobre esa instancia.

Un detector externo debe adaptar su salida a este contrato. El modo cámara integrado
ya convierte puntos a casillas con la calibración y usa códigos sin color. Para
observaciones parciales de vídeo, `desconocidas` identifica las casillas dudosas y
`confianzas` contiene la confianza de cada casilla; `SeguimientoPorCasilla` permite
actualizar las otras celdas sin bloquear el tablero completo.

## Prueba opcional con datos sintéticos (no conecta la cámara)

Abra primero el tablero:

```powershell
.\.venv\Scripts\python.exe tablero_pygame.py --entrada observacion.json
```

En otra terminal, en esta misma carpeta:

```powershell
.\.venv\Scripts\python.exe simular_entrada.py observacion.json
```

El productor publica durante seis segundos: posición inicial con dos torres,
movimiento a1 → a3 y movimiento h8 → h6. Después termina; la interfaz conserva
el resultado y avisa de que ya no recibe datos.

## Alcance y archivos

- `seguimiento.py`: validación, estado, estabilización y reconocimiento de cambios.
- `captura_vivo.py`: captura de cámara e inferencia en procesos separados.
- `vision_vivo.py`: máscaras, puntos de apoyo y asignación a casillas.
- `tiempo_real.py`: interfaz de vídeo y calibración interactiva.
- `reglas_deteccion.py`: restricción compartida de cuatro torres.
- `entrada.py`: contrato y lectura/publicación de la última observación JSON.
- `tablero_pygame.py`: consumo exclusivo de observaciones a 10 Hz; dibujo a 60 FPS.
- `simular_entrada.py`: productor de ejemplo sin cámara ni modelo.
- `test_seguimiento.py`: pruebas automatizadas con tiempos simulados.

Pygame refleja cada distribución completa y estable del detector. Adicionalmente,
reconoce movimientos simples, capturas, promociones, patrones de enroque y captura al
paso tras un avance doble confirmado. Esto no sustituye un motor de reglas de ajedrez.
Los cambios múltiples se muestran sin inventar una jugada para el historial. El
historial se conserva en memoria y cada movimiento reconocido se imprime en la terminal.
La clase Seguimiento conserva un modo conservador opcional (reflejar_observaciones=False)
para consumidores que prefieran rechazar cambios que no pueda identificar como jugadas.

El filtrado temporal no garantiza corregir una detección errónea que permanezca estable.
La precisión y las oclusiones deben verificarse con cada posición de cámara.

```powershell
.\.venv\Scripts\python.exe -B -m unittest -v test_seguimiento test_main test_vivo
```
