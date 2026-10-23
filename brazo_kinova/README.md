# Brazo Kinova: mover el efector a una coordenada (x, y, z)

Interfaz mínima para llevar el efector final del Kinova Gen3 (6 DoF + pinza
Robotiq 2F-85) a una coordenada con MoveIt 2, simulado en RViz.

| Archivo | Qué hace |
|---|---|
| `simular_brazo.sh` | Lanza MoveIt 2 con hardware falso y RViz con `brazo.rviz`. |
| `simular_brazo_wsl.cmd` | Inicia desde Windows la simulación y la GUI en Ubuntu WSL. |
| `simular_brazo_wsl.sh` | Carga el workspace configurable, espera MoveIt y administra los procesos de su sesión. |
| `brazo.rviz` | Vista de RViz que solo muestra el brazo moviéndose en tiempo real (sin la trayectoria planificada ni brazos fantasma) y los ejes de la base. |
| `mover_xyz.py` | Ventana con casillas x, y, z, botones − / + (1 cm) y botón **Mover**. |

## Requisitos

- ROS 2 Humble y MoveIt 2.
- Workspace `~/ros2_ws` compilado con `ros2_kortex`
  (paquete `kinova_gen3_6dof_robotiq_2f_85_moveit_config`).

## Windows + Ubuntu WSL

Abre `simular_brazo_wsl.cmd` con doble clic, o desde PowerShell en la raíz del
proyecto:

```powershell
.\brazo_kinova\simular_brazo_wsl.cmd
```

Solo necesitas tener Windows iniciado: el lanzador inicia Ubuntu por ti. Debes
tener previamente WSL2, Ubuntu-22.04, WSLg, ROS Humble, MoveIt 2, `python3-tk`
y el workspace Kortex compilado. No requiere abrir VS Code ni conectar el robot.
No instala dependencias ni compila el workspace.

Este flujo busca el workspace en `~/kinova_revision/ros2_ws` dentro de Ubuntu
(el flujo original descrito abajo sigue usando `~/ros2_ws`). Para otra ruta:

```powershell
.\brazo_kinova\simular_brazo_wsl.cmd --workspace /home/semillero/ros2_ws
```

Se abren MoveIt con hardware ficticio, RViz sin la animación de trayectoria y
la interfaz XYZ. Mantén abierta la terminal; cierra la GUI o pulsa **Ctrl+C**
para cerrar los procesos de esta sesión. Este lanzador no termina otras
sesiones por nombre y no modifica el lanzador original.

Consulta [WSL.md](WSL.md) para elegir distribución, dominio ROS u opciones
como `--sin-rviz` y `--sin-gui`.

## Uso original desde Ubuntu

Terminal 1 (simulación; dejarla abierta):

```bash
./simular_brazo.sh
```

Terminal 2 (interfaz):

```bash
source /opt/ros/humble/setup.bash && source ~/ros2_ws/install/setup.bash
python3 mover_xyz.py
```

Escribe la coordenada (o ajústala con − / +) y pulsa **Mover** o Enter. Las
coordenadas son metros en el frame `base_link`:

- **x** adelante (eje rojo en RViz)
- **y** izquierda (eje verde)
- **z** arriba (eje azul)

Cada movimiento tarda unos 5–15 s (planificación + ejecución al 20 % de
velocidad). La línea de estado indica en verde si llegó y en rojo el motivo si
no (fuera de alcance, sin trayectoria, colisión…). El brazo llega a unos
0.9 m de la base. Solo se fija la posición; la orientación de la pinza la elige
MoveIt.

La ventana se cierra con la X, `Ctrl + C` o `Ctrl + Z`. La simulación se cierra
con `Ctrl + C` en la terminal 1.
