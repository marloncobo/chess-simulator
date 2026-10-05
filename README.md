# Chess Simulator

Detección de piezas de ajedrez mediante cámara y representación en Pygame.

## Iniciar

Desde la carpeta del proyecto, usando el entorno existente:

```powershell
.\.venv\Scripts\python.exe main.py --camara --source 1
```

Con el celular por WiFi, inicie el puente y use su dirección de vídeo:

```powershell
.\.venv\Scripts\python.exe puente_iphone.py
.\.venv\Scripts\python.exe main.py --camara --source http://127.0.0.1:5002/stream
```

Acepte la notificación del celular. Marque las esquinas del tablero o pulse **Cargar**
si la cámara no cambió de posición. La calibración existente se conserva en `config/`.
Si el programa estaba abierto durante la reorganización, ciérrelo y vuelva a iniciarlo.

Sin argumentos, `main.py` abre el selector de fotografías para el detector de torres.

## Estructura

```text
chess-simulator/
├── main.py                 # Entrada principal
├── chess_simulator/        # Cámara, detección, seguimiento y Pygame
│   └── rutas.py            # Rutas compartidas de modelos y datos
├── herramientas/           # Pruebas visuales HSV, grises y simulador JSON
├── tests/                  # Pruebas automáticas
├── modelos/                # bestnano.pt y best.pt
├── datos/
│   ├── imagenes/           # Fotografías de prueba
│   └── observacion.json    # Última observación local (no versionada)
├── config/                 # Calibraciones locales de cámara
├── resultados/
│   └── historicos/         # CSV e imágenes existentes, conservados
├── metricas/               # Métricas y archivos de entrenamiento existentes
├── docs/GUIA_USO.md         # Guía detallada y contrato de observaciones
├── requirements-ui.txt     # Dependencia de la interfaz
└── .venv/                  # Entorno local existente
```

Los módulos de la aplicación se importan como `chess_simulator.seguimiento`,
`chess_simulator.entrada`, etc. Las herramientas se ejecutan con `-m` desde la raíz;
no necesitan modificar manualmente las rutas de Python.

## Herramientas

Prueba de dos cámaras en tiempo real, lado a lado (sin detección de piezas):

```powershell
.\.venv\Scripts\python.exe -m herramientas.probar_dos_camaras --sources 0 1
```

Para una webcam y el iPhone, inicie primero el puente en otra terminal:

```powershell
.\.venv\Scripts\python.exe puente_iphone.py
```

Abra en Safari la dirección **HTTPS** que imprime el puente y acepte el acceso
a la cámara. Luego ejecute la prueba con la dirección **HTTP del vídeo**:

```powershell
.\.venv\Scripts\python.exe -m herramientas.probar_dos_camaras --sources 0 http://127.0.0.1:5002/stream
```

El puente requiere Flask y pyOpenSSL. Funciona con Safari en iPhone y con Chrome
en Android. Cada copia del puente atiende un teléfono; para usar dos teléfonos
como las dos cámaras, inicie dos copias con puertos distintos:

```powershell
.\.venv\Scripts\python.exe puente_iphone.py
.\.venv\Scripts\python.exe puente_iphone.py --puerto-celular 5003 --puerto-stream 5004
.\.venv\Scripts\python.exe -m herramientas.probar_dos_camaras --sources http://127.0.0.1:5002/stream http://127.0.0.1:5004/stream --detectar
```

Cada teléfono abre la dirección HTTPS de su copia (puerto 5001 y 5003).

La ventana muestra resolución real, FPS de lectura, antigüedad de cada imagen,
reinicios y desfase entre lecturas en el PC. **Q/Esc** cierra; **R** reconecta ambas
fuentes. Las imágenes antiguas se oscurecen. Cada captura se reinicia después de
8 segundos sin cuadros, incluso si la lectura se bloquea; ajuste con `--timeout 12`.
La otra fuente continúa durante la recuperación.

Opciones independientes para dos cámaras locales:

```powershell
.\.venv\Scripts\python.exe -m herramientas.probar_dos_camaras --sources 0 1 --backend-1 dshow --backend-2 msmf --resolucion-1 1280 720 --resolucion-2 640 480
```

`--backend`, `--ancho` y `--alto` siguen disponibles como valores comunes.
Las URLs usan `auto` y conservan la resolución enviada por el teléfono. El puente
del iPhone solicita **HD 720p** por defecto y permite elegir **1080p** o **480p**
desde Safari, sin reiniciar la prueba. Envía las dimensiones reales que entrega
la cámara y adapta el lienzo al girar el teléfono, sin estirar ni recortar.
Coloque el iPhone **horizontal** para aprovechar el ancho del panel como una
webcam; en vertical se conservan bandas laterales para mostrar todo el tablero.
Después de cambiar resolución u orientación, vuelva a calibrar esa cámara.
Si la red se vuelve lenta en 1080p, seleccione 720p o 480p. La resolución exacta
depende de lo que permita Safari y se muestra en el teléfono y en el PC.
El puente recupera automáticamente la cámara si el vídeo deja de avanzar o
la captura JPEG se bloquea, y vuelve a abrirla al regresar a Safari. También
incluye **Reconectar cámara** en el teléfono. Mantenga Safari visible: iOS puede
suspender la cámara al bloquear la pantalla o cambiar de aplicación. El puente
solicita mantener la pantalla encendida, aunque el sistema puede denegarlo.
Si el PC reconecta y pide calibración, use **L** solo si el teléfono no se movió.
Si una cámara local no abre, cierre otras aplicaciones que la usen o pruebe
`--backend-1 dshow` / `--backend-2 dshow` (Windows).

El aviso de desfase usa un umbral configurable (`--max-desfase-ms 250`). **Compara
tiempos de lectura, no momentos de exposición ni retraso real del iPhone**; las
cámaras no están sincronizadas. Sin `--detectar`, esta herramienta comprueba
únicamente vídeo y conexiones.

### Detección combinada de piezas

Con el puente activo y ambos dispositivos transmitiendo:

```powershell
.\.venv\Scripts\python.exe -m herramientas.probar_dos_camaras --sources 0 http://127.0.0.1:5002/stream --detectar
```

1. Pulse **1**: se congela la imagen de la primera cámara. Marque los cuatro
   vértices **exteriores** del tablero en orden **a8, h8, h1, a1**.
2. Pulse **2** y repita en la otra imagen. Identifique las mismas esquinas
   físicas, aunque aparezcan giradas por mirar desde el lado opuesto.
3. Retire las manos y espere a que las dos vistas estén estables. Verá las
   siluetas detectadas en cada cámara y un tablero combinado debajo.

Las calibraciones se guardan por fuente y resolución en `config/`. **L** las
carga en sesiones posteriores, solo si las cámaras siguen en la misma posición.
**1/2** permiten repetir la calibración. **S** reinicia la posición detectada;
**R** reconecta las fuentes y exige volver a calibrar o cargar. **Q/Esc** cierra.

El tablero usa T/C/A/D/R/P para torre/caballo/alfil/dama/rey/peón, con círculos
blancos o negros. La indicación **1**, **2** o **1+2** muestra qué cámara aporta
la detección. Un borde naranja indica duda y conserva el estado previo.

Se usa una sola instancia de `modelos/bestnano.pt` para las dos imágenes.
Puede elegir otro modelo de **segmentación** con `--modelo`. `--confianza` es el
filtro de YOLO (por defecto 0.25, rango 0.05 a 1): las detecciones entre ese valor
y 0.5 no afirman pieza, pero dejan su casilla en duda en esa vista en lugar de
darla por vacía, para que la otra cámara pueda confirmarla. El detector clasifica tipo por YOLO y color
mediante los umbrales HSV existentes; exposición e iluminación distintas pueden
producir colores dudosos.

La combinación distingue dudas de color, oclusión estimada por silueta,
movimiento local, fondo no verificable y apoyo próximo a un borde. El panel
indica la causa; una duda de color ya no cuenta como rescate por oclusión.
La letra **H** identifica una pieza conservada del historial sin observación
actual coincidente. Los contadores del panel describen propuestas, no precisión.

### Probar con dos fotos (sin cámaras)

Tome dos fotos del mismo tablero desde dos posiciones, sin mover nada entre
una y otra, y ejecute:

```powershell
.\.venv\Scripts\python.exe -m herramientas.probar_fotos fotoA.jpg fotoB.jpg
```

La primera vez se marcan las esquinas a8, h8, h1, a1 de cada foto (Enter
acepta, R repite); quedan guardadas para las siguientes ejecuciones. Corre la
misma cadena que en vivo y muestra el mismo panel, más los tableros de cada
foto y de la fusión en la terminal. Con `--guardar-par datos/verificacion/pares.json`
añade el par al archivo de verificación para corregir su posición y medirlo.

### Medir aciertos con fotos reales

`herramientas/evaluar_pares.py` corre el modelo y la fusión sobre pares de fotos
anotados a mano y cuenta, casilla por casilla, aciertos, dudas, falsas vacías y
errores afirmados para cada vista y para la fusión:

```powershell
.\.venv\Scripts\python.exe -m herramientas.evaluar_pares datos/verificacion/pares.json
.\.venv\Scripts\python.exe -m herramientas.evaluar_pares datos/verificacion/pares.json --confianza 0.5 --csv resultados/eval.csv
```

El formato está descrito en el propio script; `datos/verificacion/pares.json`
trae un par de ejemplo (foto1/foto2). Agregue pares tomados desde las posiciones
reales de las cámaras antes de ajustar umbrales.

Cada casilla se evalúa por separado: el movimiento en una vista no bloquea las
zonas estables de la otra. Las casillas afectadas por movimiento esperan 0.8 s
sin cambios. La apariencia de las casillas vacías se comprueba contra referencias
de color del tablero aprendidas en cada cámara; si no se puede verificar el fondo,
la ausencia queda dudosa incluso cuando el objeto que la tapa está inmóvil.
Para aprender las referencias, deje visibles varias casillas vacías de ambos
colores al calibrar. Los tableros muy texturados o los cambios de iluminación
pueden producir más dudas; recalibre para reiniciar las referencias.

Una coincidencia de ambas vistas conserva la confirmación normal (al menos
3 muestras y 0.6 s). Una pieza vista solo por una cámara exige confianza mínima
0.70, al menos 5 muestras y 1.5 s; las detecciones más débiles quedan pendientes.
Los conflictos de tipo/color conservan la última posición sin elegir un ganador.
Una casilla se da por vacía cuando una vista la ve vacía con el fondo verificado
y la otra también, o solo la tiene tapada por otra pieza. Si la otra vista ve
algo (fondo que no parece vacío, detección débil, movimiento), queda en duda.
Retirar una pieza confirmada requiere además 2 segundos de estabilidad.

Si una cámara se reconecta con la misma resolución, su calibración se conserva:
un corte del stream no implica que se haya movido. Solo se borra si la resolución
cambia; si la cámara se movió de verdad, recalibre con 1 o 2.

Los topes por clase de `chess_simulator/reglas_deteccion.py` (2 reyes, 2 damas,
4 torres, 4 alfiles, 4 caballos, 16 peones, y como máximo 1 rey por color) se
aplican por vista y sobre el estado acumulado; las detecciones sobrantes de menor
confianza quedan en duda con su motivo.

Los apoyos a menos de 0.12 casillas de un borde se consideran ambiguos junto
con las casillas vecinas. Si dos vistas asignan la misma clase a casillas
diferentes con apoyos a menos de 0.55 casillas, no se confirman como dos piezas.
Estas comprobaciones reducen decisiones arbitrarias; no corrigen automáticamente
una cámara movida. La calibración sigue siendo manual y debe repetirse si cambia
su posición. Tampoco hay garantía de detectar todas las manos u oclusiones: un
objeto parecido al fondo o errores coincidentes de las dos cámaras pueden fallar.

Solo se procesan pares nuevos con lecturas separadas por no más de
`--max-desfase-ms` (250 ms por defecto) y resultados de menos de 2 segundos.
Si una cámara falla o las vistas se desfasan, se conserva la posición. El
movimiento solo invalida las casillas afectadas por vista. El umbral se refiere
a la lectura en el PC, no a sincronización
real de los sensores. La base estimada de una pieza tapada también puede caer
en una casilla incorrecta: revise la cuadrícula sobre ambas imágenes.

Prueba HSV con cámara:

```powershell
.\.venv\Scripts\python.exe -m herramientas.probar_color_hsv --source 1
.\.venv\Scripts\python.exe -m herramientas.probar_color_hsv --source http://127.0.0.1:5002/stream
```

Prueba HSV con fotografía, sin cámara ni ventana:

```powershell
.\.venv\Scripts\python.exe -m herramientas.probar_color_hsv --imagen datos/imagenes/torres.jpeg --sin-ventana
```

Comparación visual de canales de color:

```powershell
.\.venv\Scripts\python.exe -m herramientas.testplotgray
```

Detector de torres con salida en `resultados/`:

```powershell
.\.venv\Scripts\python.exe -m chess_simulator.torres datos/imagenes
```

## Verificación

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Estas pruebas no abren la cámara. El entorno local existente se conserva; no es
necesario reinstalarlo por esta reorganización. `requirements-ui.txt` contiene solo
Pygame; el detector también utiliza OpenCV, NumPy y Ultralytics ya instalados.

Consulte [la guía de uso](docs/GUIA_USO.md) para calibración, ajustes HSV, seguimiento,
entrada JSON y limitaciones del detector.
