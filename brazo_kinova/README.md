# Brazo Kinova: mover el efector a una coordenada (x, y, z)

Interfaz mínima para llevar el efector final del Kinova Gen3 (6 DoF + pinza
Robotiq 2F-85) a una coordenada con MoveIt 2, simulado en RViz.

| Archivo | Qué hace |
|---|---|
| `simular_brazo.sh` | Lanza MoveIt 2 con hardware falso y RViz con `brazo.rviz`. |
| `brazo.rviz` | Vista de RViz que solo muestra el brazo moviéndose en tiempo real (sin la trayectoria planificada ni brazos fantasma) y los ejes de la base. |
| `mover_xyz.py` | Ventana con casillas x, y, z, botones − / + (1 cm) y botón **Mover**. |

## Requisitos

- ROS 2 Humble y MoveIt 2.
- Workspace `~/ros2_ws` compilado con `ros2_kortex`
  (paquete `kinova_gen3_6dof_robotiq_2f_85_moveit_config`).

## Uso

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
