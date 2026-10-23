# Simulación desde Windows + Ubuntu WSL

Este lanzador es independiente de `simular_brazo.sh`; el flujo de los demás
colaboradores se conserva. Requiere Ubuntu-22.04 con ROS Humble, MoveIt,
`python3-tk`, WSLg y el workspace Kortex ya compilado.

Desde Windows, abre `simular_brazo_wsl.cmd` con doble clic. Inicia MoveIt con
hardware ficticio, espera hasta 60 segundos por `/move_action`, abre RViz sin
la animación de trayectoria y abre la interfaz XYZ. No instala ni compila nada.
El destino sigue siendo Gen3 de seis articulaciones con Robotiq 2F-85.

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
