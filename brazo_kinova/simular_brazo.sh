#!/usr/bin/env bash
# Gen3 Lite en Ubuntu: comparte la implementación con el lanzador de WSL.
# KINOVA_WS o --workspace permiten elegir el workspace de cada colaborador.
set -eo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$DIR/simular_brazo_wsl.sh" --workspace "${KINOVA_WS:-$HOME/ros2_ws}" "$@"
