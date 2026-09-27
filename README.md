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
