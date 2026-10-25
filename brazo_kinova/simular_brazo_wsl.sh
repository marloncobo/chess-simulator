#!/usr/bin/env bash
# Lanzador independiente para Ubuntu 22.04 en WSL. Siempre usa hardware ficticio.
set -eo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="${KINOVA_WS:-$HOME/kinova_revision/ros2_ws}"
CONFIG=kinova_gen3_lite_moveit_config
GUI=true
RVIZ=true
TABLERO=true
usage() {
  echo "Uso: bash simular_brazo_wsl.sh [--workspace RUTA] [--sin-rviz] [--sin-gui] [--sin-tablero]"
}
while (($#)); do
  case "$1" in
    --workspace) [[ $# -ge 2 ]] || { usage; exit 2; }; WORKSPACE="$2"; shift 2 ;;
    --sin-rviz) RVIZ=false; shift ;;
    --sin-gui) GUI=false; shift ;;
    --sin-tablero) TABLERO=false; shift ;;
    --help|-h) usage; exit 0 ;;
    *) usage; exit 2 ;;
  esac
done
for setup in /opt/ros/humble/setup.bash "$WORKSPACE/install/setup.bash"; do
  if [[ ! -f "$setup" ]]; then
    echo "No existe $setup. Instala ROS o compila el workspace indicado." >&2
    exit 1
  fi
  source "$setup"
done
for command in ros2 python3 setsid flock; do
  command -v "$command" >/dev/null || { echo "Falta $command" >&2; exit 1; }
done
ros2 pkg prefix "$CONFIG" >/dev/null || exit 1
if $GUI; then
  python3 -c 'import tkinter, rclpy; from moveit_msgs.action import MoveGroup' || exit 1
fi
if $GUI || $RVIZ; then
  [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]] || {
    echo "No hay pantalla disponible. Abre Ubuntu con WSLg habilitado." >&2; exit 1;
  }
fi
# Mismos valores para todos los procesos de esta sesión; no usa el daemon ROS.
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-73}"
export ROS_LOCALHOST_ONLY=1
exec 9>"/tmp/chess-kinova-${UID}-${ROS_DOMAIN_ID}.lock"
flock -n 9 || { echo "Ya hay una sesión de este lanzador en el dominio $ROS_DOMAIN_ID." >&2; exit 1; }
pids=()
cleanup() {
  trap - EXIT INT TERM
  for pid in "${pids[@]}"; do kill -INT -- "-$pid" 2>/dev/null || true; done
  for ((i=0; i<50; i++)); do
    alive=false
    for pid in "${pids[@]}"; do kill -0 -- "-$pid" 2>/dev/null && alive=true; done
    $alive || break
    sleep 0.1
  done
  for pid in "${pids[@]}"; do kill -TERM -- "-$pid" 2>/dev/null || true; done
  sleep 1
  for pid in "${pids[@]}"; do kill -KILL -- "-$pid" 2>/dev/null || true; done
  for pid in "${pids[@]}"; do wait "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
start() { setsid "$@" 9>&- & pids+=("$!"); }
echo "Iniciando Kinova Gen3 Lite con pinza Gen3 Lite 2F ficticios. Workspace: $WORKSPACE"
echo "Dominio ROS: $ROS_DOMAIN_ID. Para cerrar todo: cierra la GUI o pulsa Ctrl+C."
# En este paquete Lite, robot.launch.py solo inicia MoveIt: bringup publica
# el modelo y pone en marcha ros2_control y los controladores ficticios.
start ros2 launch kortex_bringup gen3_lite.launch.py robot_ip:=127.0.0.1 \
  use_fake_hardware:=true launch_rviz:=false
start ros2 launch "$CONFIG" robot.launch.py robot_ip:=127.0.0.1 \
  use_fake_hardware:=true launch_rviz:=false
# Espera el servidor de MoveIt antes de abrir la interfaz.
python3 - <<'PY'
import rclpy
from rclpy.action import ActionClient
from moveit_msgs.action import MoveGroup
rclpy.init()
node = rclpy.create_node('esperar_moveit_wsl')
client = ActionClient(node, MoveGroup, '/move_action')
try:
    if not client.wait_for_server(timeout_sec=60):
        raise SystemExit('MoveIt no estuvo disponible en 60 s. Revisa los errores anteriores.')
finally:
    client.destroy()
    node.destroy_node()
    rclpy.shutdown()
PY
$TABLERO && start python3 "$DIR/escena_virtual.py"
if $TABLERO; then
  # No habilitar la GUI hasta confirmar que MoveIt conoce los obstáculos.
  python3 - <<'PY'
import time
import rclpy
from moveit_msgs.srv import GetPlanningScene
from moveit_msgs.msg import PlanningSceneComponents
rclpy.init()
node = rclpy.create_node('esperar_tablero_virtual')
client = node.create_client(GetPlanningScene, '/get_planning_scene')
try:
    limite = time.monotonic() + 20
    listo = False
    while time.monotonic() < limite:
        if not client.wait_for_service(timeout_sec=1):
            continue
        request = GetPlanningScene.Request()
        request.components.components = PlanningSceneComponents.WORLD_OBJECT_NAMES
        future = client.call_async(request)
        rclpy.spin_until_future_complete(node, future, timeout_sec=1)
        if future.done():
            nombres = {o.id for o in future.result().scene.world.collision_objects}
            if {'semillero_tablero_virtual', 'semillero_pieza_virtual'} <= nombres:
                listo = True
                break
        else:
            client.remove_pending_request(future)
        time.sleep(0.1)
    if not listo:
        raise SystemExit('No se confirmó el tablero virtual en MoveIt. Revisa la configuración de la escena.')
finally:
    node.destroy_node()
    rclpy.shutdown()
PY
fi
$RVIZ && start rviz2 -d "$DIR/brazo.rviz"
$GUI && start python3 "$DIR/mover_xyz.py"
# Si termina cualquiera de los programas, cierra los restantes de esta sesión.
wait -n "${pids[@]}"
