# Simulación desde Windows + Ubuntu WSL

Este lanzador comparte la implementación con `simular_brazo.sh`; cada
colaborador puede elegir su workspace. Requiere Ubuntu-22.04 con ROS Humble, MoveIt,
`python3-tk`, WSLg y el workspace Kortex ya compilado.

Desde Windows, abre `simular_brazo_wsl.cmd` con doble clic. Inicia MoveIt con
hardware ficticio, espera hasta 60 segundos por `/move_action`, abre RViz sin
la animación de trayectoria y abre la interfaz XYZ. No instala ni compila nada.
El modelo es Kinova Gen3 Lite de seis articulaciones con su pinza Gen3 Lite 2F.
Requiere `kinova_gen3_lite_moveit_config`. Se inicia `kortex_bringup
gen3_lite.launch.py` con hardware ficticio y después MoveIt del Lite. El grupo
de planificación es `arm`; no se usa el modelo Gen3 con Robotiq.

También inicia el tablero virtual y una pieza provisional. Antes de abrir la GUI
confirma que ambos obstáculos estén registrados en MoveIt. Para iniciar solo el
brazo, usa `simular_brazo_wsl.cmd --sin-tablero`.

Edita `escena_virtual.json` y reinicia para cambiar medidas y ubicación. Los
valores están en metros: tablero de 0.44 m, grosor supuesto de 0.02 m, centro
en `(0.40, 0, 0)` de `base_link` y superficie a z=0. El caballo se representa
con un cilindro de 0.06 m de altura y diámetro supuesto de 0.03 m, en `d4`.
Las filas 1→8 avanzan en +X y las columnas a→h en +Y. Esa ubicación es de prueba,
no una calibración real ni una garantía de alcance de las 64 casillas.

RViz muestra la escena mediante **Tablero y pieza virtual**. No necesitas activar
MotionPlanning ni la animación de trayectorias. Los obstáculos limitan los
movimientos: no intentes bajar el montaje a z=0, pues los dedos penetrarían
el tablero. Todavía no hay apertura/cierre, agarre ni unión de la pieza al brazo.

Para añadir la escena a una sesión ROS iniciada manualmente, carga sus entornos
y el mismo `ROS_DOMAIN_ID` en Ubuntu, y ejecuta `python3 brazo_kinova/escena_virtual.py`
desde la raíz del proyecto. Puedes elegir otro JSON con `--config RUTA`.
Cerrar ese programa detiene la publicación de marcas; RViz puede conservar
las que ya recibió. Los obstáculos permanecen en MoveIt hasta reiniciarlo.
Volver a ejecutarlo actualiza únicamente los dos objetos
con identificadores `semillero_tablero_virtual` y `semillero_pieza_virtual`.

La ruta por defecto es `~/kinova_revision/ros2_ws`. Para cambiarla, desde Ubuntu:

```bash
cd /mnt/c/Users/Usuario/Desktop/chess-simulator
bash brazo_kinova/simular_brazo_wsl.sh --workspace "$HOME/ros2_ws"
```

También admite `KINOVA_WS` como variable de entorno Linux, `--sin-rviz`,
`--sin-gui` y `--help`. Por ejemplo, desde PowerShell:

```powershell
.\brazo_kinova\simular_brazo_wsl.cmd --workspace /home/semillero/ros2_ws
```

Para usar otra distribución, define `KINOVA_WSL_DISTRO` en Windows. La GUI y ROS
usan Python de Ubuntu, no la `.venv` de Windows. No se requiere abrir VS Code en
WSL para iniciar el archivo `.cmd`.

Cierra la GUI o pulsa Ctrl+C en la terminal para terminar la sesión. El lanzador
solo envía señales a los grupos de procesos que creó; no cierra otras aplicaciones
ROS por nombre. Mantén la terminal abierta mientras lo usas.

Usa comunicación ROS local y dominio 73 por defecto. Puedes elegir otro dominio
con `ROS_DOMAIN_ID` en Ubuntu. No ejecutes otros controladores en ese mismo dominio;
el bloqueo evita duplicados de este lanzador, pero no detecta lanzamientos manuales.
La espera inicial comprueba MoveIt, no garantiza que todos los controladores estén
listos: ante un error de ejecución revisa la salida de la terminal.

Si falta el workspace o un paquete, el error aparece en la terminal; el lanzador
de Windows mantiene visible el mensaje al fallar.
