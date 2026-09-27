# Tablero virtual y seguimiento

## Prueba de color HSV con cámara

Ejecute los comandos desde la raíz del proyecto (la carpeta que contiene `main.py`):

```powershell
.\.venv\Scripts\python.exe -m herramientas.probar_color_hsv --source 1
```

Muestra la imagen original ampliada con las máscaras del detector. Pulse V para
alternar entre original, canal V y comparación lado a lado. Las etiquetas se
dibujan después de escalar la imagen, con mayor tamaño y fondo oscuro. Cada pieza lleva
una etiqueta BLANCA (verde), NEGRA (azul) o DUDOSA (naranja), y las medianas S/V
de su máscara interior. No requiere marcar esquinas. Usa la cámara indicada;
no cambia automáticamente a otra. Cierre otras pruebas que estén usando la cámara.

Los deslizadores usan escala 0–255: `V negra max` fija el máximo para negras,
`V blanca min` el mínimo para blancas y `S blanca max` la saturación máxima
para blancas (incluye piezas de color crema). Entre ambos umbrales V, o si una
pieza clara supera el límite S, queda dudosa. H no se usa para distinguir blanco
y negro. Los valores iniciales son orientativos: ajuste con ambas clases visibles.
El umbral negro debe ser menor que el blanco; la ventana avisa si se cruzan.

`Erosion px` reduce la máscara para excluir bordes y fondo; si quedan menos de
20 píxeles, la pieza queda dudosa. Espacio pausa la imagen para ajustar controles,
R restablece los valores iniciales y Esc/Q cierra. Los ajustes duran esta sesión.
Se solicita captura de 1920×1080; la cabecera indica la resolución realmente
recibida, que depende de la cámara. Puede solicitar otra con `--ancho 1280 --alto 720`.
Se muestra el fotograma procesado, con su antigüedad, para que las máscaras
correspondan a la imagen. La precisión depende de la segmentación y la luz;
esta prueba no publica colores al tablero ni modifica el seguimiento.

También puede probar una fotografía con los mismos controles:

```powershell
.\.venv\Scripts\python.exe -m herramientas.probar_color_hsv --imagen datos/imagenes/torres.jpeg
```

Para verificar sin abrir ventana, añada `--sin-ventana`; opcionalmente,
`--salida comparacion_hsv.jpg` guarda la comparación con los umbrales iniciales.

## Cámara en vivo: actualización por casilla

```powershell
.\.venv\Scripts\python.exe main.py --camara --source 1
```

El modo cámara procesa las seis clases y distingue piezas blancas y negras mediante HSV. Marque los cuatro
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
.\.venv\Scripts\python.exe main.py --imagen datos/imagenes/torres4.jpeg
```

Se carga `modelos/bestnano.pt` (o `--modelo ruta.pt`) y se reutilizan
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
.\.venv\Scripts\python.exe main.py --entrada datos/observacion.json
```

El modo imagen usa OpenCV, NumPy y Ultralytics del entorno del detector, además de
Pygame. Para vídeo use `--camara`, que incorpora clasificación HSV del color de las piezas.

También se conserva un modo de entrada JSON independiente: `tablero_pygame.py`
consume observaciones externas sin abrir cámara ni ejecutar YOLO. `main.py` coordina
los modos de imagen, cámara y entrada externa.

## Ejecución en Windows

Desde esta carpeta, con el entorno existente:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-ui.txt
.\.venv\Scripts\python.exe -m chess_simulator.tablero_pygame
```

El tablero empieza sin piezas: no hay una posición inicial fija ni movimientos por
ratón. Espera `datos/observacion.json`, o la ruta indicada con `--entrada`.
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

El productor puede importar `chess_simulator.entrada.publicar(ruta, datos)` para escribir de forma
atómica; `chess_simulator.entrada.crear_observacion(matriz, secuencia)` convierte una matriz 8×8 al
contrato. Si ambos componentes comparten proceso, puede llamar directamente a
`Seguimiento(reflejar_observaciones=True)` y llamar a
`recibir(Observacion.desde_dict(datos), time.monotonic())` sobre esa instancia.

Un detector externo debe adaptar su salida a este contrato. El modo cámara integrado
ya convierte puntos a casillas con la calibración y usa mayúsculas para blancas y minúsculas para negras. Para
observaciones parciales de vídeo, `desconocidas` identifica las casillas dudosas y
`confianzas` contiene la confianza de cada casilla; `SeguimientoPorCasilla` permite
actualizar las otras celdas sin bloquear el tablero completo.

## Prueba opcional con datos sintéticos (no conecta la cámara)

Abra primero el tablero:

```powershell
.\.venv\Scripts\python.exe -m chess_simulator.tablero_pygame --entrada datos/observacion.json
```

En otra terminal, en esta misma carpeta:

```powershell
.\.venv\Scripts\python.exe -m herramientas.simular_entrada datos/observacion.json
```

El productor publica durante seis segundos: posición inicial con dos torres,
movimiento a1 → a3 y movimiento h8 → h6. Después termina; la interfaz conserva
el resultado y avisa de que ya no recibe datos.

## Alcance y archivos

- `seguimiento.py`: validación, estado, estabilización y reconocimiento de cambios.
- `captura_vivo.py`: captura de cámara e inferencia en procesos separados.
- `vision_vivo.py`: máscaras, puntos de apoyo y asignación a casillas.
- `color_hsv.py`: clasificación compartida del color sobre el interior de las máscaras.
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
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```


## Colores de las piezas en el tablero en vivo

El modo `main.py --camara --source 1` clasifica el color de cada pieza sobre
su máscara de segmentación, en el mismo fotograma usado por YOLO. Usa el mismo
clasificador que `probar_color_hsv.py`: erosiona 3 píxeles del borde y calcula
las medianas HSV. V <= 85 indica negra; V >= 150 y S <= 110 indica blanca.
No utiliza el lado del tablero ni una posición inicial predefinida para asignar color.

En Pygame se dibujan blancas y negras. En la cámara, los marcadores verdes con B
indican blanca, los azules con N negra y los naranjas con ? color dudoso.
Una casilla con color dudoso conserva su estado anterior y recibe borde naranja;
si nunca se confirmó, permanece vacía hasta obtener muestras fiables.
Las demás casillas continúan actualizándose. El filtro temporal también estabiliza
el color; el límite sigue siendo cuatro torres en total, contando ambos colores.

Los ajustes realizados con los deslizadores de la prueba no se guardan automáticamente.
Para usar esos valores en el modo cámara, páselos al iniciar, por ejemplo:

```powershell
.\.venv\Scripts\python.exe main.py --camara --source 1 --hsv-negra-max 85 --hsv-blanca-min 150 --hsv-saturacion-max 110 --hsv-erosion 3
```

La iluminación, las sombras y una máscara que incluya parte de otra pieza pueden
alterar el resultado. Ajuste los umbrales con la prueba HSV bajo la misma iluminación.
Esta integración corresponde al modo cámara; la vista estática de torres conserva
su comportamiento anterior. Los colores de las casillas de Pygame no se modifican.


### Registro de movimientos con levantamiento de piezas

El seguimiento en vivo conserva durante un máximo de 10 segundos la posición
anterior al primer cambio confirmado. Así puede unir la salida de una pieza y
su llegada aunque se confirmen en momentos distintos. Los fotogramas recientes
rechazados por movimiento u oclusión reinician las muestras de estabilidad,
pero conservan esa referencia. No se rebaja la exigencia de confirmar las casillas.

Una recalibración, pausa, desconexión o resincronización descarta la comparación
pendiente. Una retirada que exceda el intervalo se trata como cambio de distribución,
sin inventar una jugada posterior. El reconocimiento sigue dependiendo de que
el detector mantenga el tipo, color y casilla correctos; no valida la legalidad.
La interfaz indica «Esperando completar el movimiento» cuando hay un cambio pendiente.

Pruebas del registro temporal: `python -B -m unittest -v tests.test_movimiento_vivo`.
