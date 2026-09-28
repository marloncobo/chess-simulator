# Chess Simulator

Detección de piezas de ajedrez mediante cámara y representación en Pygame.

## Iniciar

Desde la carpeta del proyecto, usando el entorno existente:

```powershell
.\.venv\Scripts\python.exe main.py --camara --source 1
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

El puente requiere Flask y pyOpenSSL. Su canal actual admite un solo teléfono;
dos teléfonos necesitan canales o instancias separados. La prueba admite dos
URLs distintas, pero no separa teléfonos que envían al mismo canal del puente.

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
Las URLs usan `auto` y conservan la resolución enviada por el teléfono: cambie
`ANCHO`/`ALTO` en el puente y vuelva a abrir su página para solicitar otra.
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
Puede elegir otro modelo de **segmentación** con `--modelo` y aumentar el umbral
con `--confianza 0.6` (mínimo 0.5). El detector clasifica tipo por YOLO y color
mediante los umbrales HSV existentes; exposición e iluminación distintas pueden
producir colores dudosos.

La combinación acepta una pieza visible en una cámara aunque la otra no la
detecte, agrupa coincidencias y deja sin confirmar los conflictos de tipo/color.
Para retirar una pieza confirmada requiere ausencia fiable en ambas vistas y al
menos 2 segundos de estabilidad. Las siluetas que se proyectan sobre casillas vecinas
marcan esas ausencias como dudosas. Es una aproximación: una mano inmóvil o una
pieza omitida por ambas cámaras todavía puede causar errores; no hay garantía
de eliminar todos los puntos ciegos.

Solo se procesan pares nuevos con lecturas separadas por no más de
`--max-desfase-ms` (250 ms por defecto) y resultados de menos de 2 segundos.
Si una cámara falla, las vistas se desfasaron o la escena se mueve, se conserva
la posición. El umbral se refiere a la lectura en el PC, no a sincronización
real de los sensores. La base estimada de una pieza tapada también puede caer
en una casilla incorrecta: revise la cuadrícula sobre ambas imágenes.

Prueba HSV con cámara:

```powershell
.\.venv\Scripts\python.exe -m herramientas.probar_color_hsv --source 1
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
