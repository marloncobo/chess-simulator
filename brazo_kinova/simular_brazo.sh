#!/usr/bin/env bash
#
# simular_brazo.sh — Simula el Kinova Gen3 (6 DoF + Robotiq 2F-85) con MoveIt 2 y RViz.
#
# No necesita el robot físico: usa `use_fake_hardware:=true`, que crea un
# ros2_control falso que simplemente obedece las trayectorias. Es lo que
# permite probar la GUI cartesiana (mover_xyz.py) sin el brazo conectado.
#
# RViz se abre con brazo.rviz, que solo muestra el brazo moviéndose en tiempo
# real (sin la trayectoria planificada ni los brazos fantasma de MoveIt).
#
# Uso:
#   ./simular_brazo.sh             # MoveIt + RViz
#   ./simular_brazo.sh --sin-rviz  # solo MoveIt (para pruebas sin ventanas)
#
# Después, en otra terminal:
#   python3 ~/ros2_ws/mover_xyz.py

set -u

# brazo.rviz vive junto a este script.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CONFIG="kinova_gen3_6dof_robotiq_2f_85_moveit_config"

LAUNCH_RVIZ="true"
if [[ "${1:-}" == "--sin-rviz" ]]; then
  LAUNCH_RVIZ="false"
fi

echo "==> [1/3] Cerrando simulaciones anteriores..."
pkill -9 -f "robot.launch.py"       2>/dev/null
pkill -9 -f "move_group"            2>/dev/null
pkill -9 -f "ros2_control_node"     2>/dev/null
pkill -9 -f "robot_state_publisher" 2>/dev/null
pkill -9 -f "rviz2"                 2>/dev/null
sleep 2

echo "==> [2/3] Cargando ROS 2 y el workspace..."
# Los setup.bash de ROS leen variables sin definir: hay que soltar `set -u`
# mientras se cargan, o el script muere con "AMENT_TRACE_SETUP_FILES: unbound".
set +u
source /opt/ros/humble/setup.bash
source "$HOME/ros2_ws/install/setup.bash"
set -u

echo "==> [3/3] Lanzando MoveIt 2 con hardware falso..."
echo "    Deja esta terminal abierta. Para cerrar: Ctrl + C"
echo "    En otra terminal:  python3 ~/ros2_ws/mover_xyz.py"
# RViz propio en segundo plano: comparte el grupo de procesos con esta
# terminal, así que Ctrl + C también lo cierra.
if [[ "$LAUNCH_RVIZ" == "true" ]]; then
  rviz2 -d "$DIR/brazo.rviz" > /dev/null 2>&1 &
fi
# robot_ip es obligatorio aunque no se use: con hardware falso no se conecta a nada.
# launch_rviz:=false porque el RViz del paquete trae el plugin MotionPlanning.
exec ros2 launch "$CONFIG" robot.launch.py \
  robot_ip:=yyy.yyy.yyy.yyy \
  use_fake_hardware:=true \
  launch_rviz:=false
