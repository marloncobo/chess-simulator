# Conectar el Kinova Gen3 Lite desde Windows y Ubuntu WSL

Guía para el workspace `~/kinova_revision/ros2_ws` y el proyecto ubicado en
`C:\Users\Usuario\Desktop\chess-simulator`. Requiere ROS 2 Humble, MoveIt 2
y el workspace Kortex compilado.

Los parámetros de lanzamiento se comprobaron contra los paquetes instalados.
La conexión y ejecución con el brazo físico todavía requieren validación.

## 1. Comprobar la conexión de red

Conecta y enciende el brazo según las instrucciones de su fabricante. Usa su IP
real: `192.168.1.10` es la dirección que se ha intentado, pero aún no se ha
confirmado que sea la del equipo.

En **PowerShell de Windows**, desde cualquier carpeta:

```powershell
ping 192.168.1.10
ipconfig
```

Comprueba la dirección IPv4 y la máscara de subred del adaptador Ethernet
conectado al brazo. La configuración del PC debe ser compatible con la red del
robot y tener una dirección diferente. No cambies la IP del robot ni del
adaptador sin confirmar primero sus valores actuales.

En **Ubuntu WSL**, desde cualquier carpeta:

```bash
export ROBOT_IP="192.168.1.10"
ping -c 4 "$ROBOT_IP"
ip -4 addr
ip route
```

- `Destination Host Unreachable` significa que no se consiguió comunicación;
  no confirma que el brazo esté conectado correctamente.
- Si Windows responde y WSL no, revisa la conectividad de WSL.
- Si ninguno responde, revisa cableado, encendido, IP del robot y subred del
  adaptador Ethernet. Un ping fallido también puede deberse a un filtro ICMP.
- Un ping correcto confirma respuesta de red, pero no garantiza que el driver
  pueda autenticarse y controlar el brazo.

Asignar `ROBOT_IP` guarda un valor; no establece una conexión.

## 2. Preparar la sesión

Cierra las sesiones ROS anteriores con **Ctrl+C en sus terminales**, incluida
la simulación y cualquier GUI anterior. Mantén despejado el recorrido del brazo
y disponible la parada de emergencia durante las pruebas físicas.

Los siguientes bloques se ejecutan en **tres terminales de Ubuntu WSL**, que
deben permanecer abiertas. Cada terminal necesita sus propios `source` y
variables. Estar situado dentro del workspace no lo carga automáticamente.

Se usa `ROS_DOMAIN_ID=74` en las tres terminales para separarlas de la simulación
habitual del proyecto. `ROS_LOCALHOST_ONLY=1` mantiene ROS local a esta instancia
de Ubuntu; el driver se comunica con la IP del robot mediante Kortex.

En los dos primeros bloques, sustituye `192.168.1.10` si la IP confirmada es otra.

## 3. Terminal 1: controlador del brazo real

```bash
cd ~/kinova_revision/ros2_ws

source /opt/ros/humble/setup.bash
source install/setup.bash

export ROS_DOMAIN_ID=74
export ROS_LOCALHOST_ONLY=1
export ROBOT_IP="192.168.1.10"

ros2 launch kortex_bringup gen3_lite.launch.py \
  robot_ip:="$ROBOT_IP" \
  use_fake_hardware:=false \
  launch_rviz:=false
```

`use_fake_hardware:=false` selecciona el hardware físico. `true` selecciona
hardware simulado. Si aparecen errores de conexión, autenticación o activación
del controlador, resuélvelos antes de continuar. Este lanzador instalado no
expone argumentos de usuario/contraseña; si falla la autenticación, revisa la
configuración de credenciales del driver sin publicarlas en el repositorio.

## 4. Terminal 2: comprobar estado e iniciar MoveIt

```bash
cd ~/kinova_revision/ros2_ws

source /opt/ros/humble/setup.bash
source install/setup.bash

export ROS_DOMAIN_ID=74
export ROS_LOCALHOST_ONLY=1
export ROBOT_IP="192.168.1.10"

ros2 pkg prefix kinova_gen3_lite_moveit_config
ros2 control list_controllers
ros2 topic echo /joint_states --once
```

El paquete debe encontrarse dentro del workspace, `joint_trajectory_controller`
debe aparecer como `active` y deben recibirse posiciones de las seis
articulaciones. Si la lectura queda esperando, interrúmpela con Ctrl+C y revisa
los mensajes de la terminal 1.

Si aparece `Package ... not found` y la búsqueda solo incluye `/opt/ros/humble`,
falta cargar `install/setup.bash` en esa terminal. Si ese archivo no existe,
revisa la ubicación y compilación del workspace.

Una vez comprobado el estado, inicia MoveIt en esta misma terminal:

```bash
ros2 launch kinova_gen3_lite_moveit_config robot.launch.py \
  robot_ip:="$ROBOT_IP" \
  use_fake_hardware:=false \
  use_sim_time:=false \
  launch_rviz:=false
```

En el workspace instalado este segundo lanzador inicia MoveIt; el controlador
y el publicador del estado del robot dependen de la terminal 1.

## 5. Terminal 3: RViz del proyecto y GUI

```bash
cd /mnt/c/Users/Usuario/Desktop/chess-simulator

source /opt/ros/humble/setup.bash
source ~/kinova_revision/ros2_ws/install/setup.bash

export ROS_DOMAIN_ID=74
export ROS_LOCALHOST_ONLY=1

rviz2 -d brazo_kinova/brazo.rviz &

python3 brazo_kinova/mover_xyz.py
```

RViz muestra el estado del brazo y la ventana «Kinova Gen3 Lite — Mover a…»
permite introducir coordenadas. Abrir RViz por sí solo no abre esta GUI.

Antes de enviar una orden, verifica que la postura mostrada coincide con la
física. Tanto **Mover** como **Preparar pinza hacia abajo** pueden mover el
brazo real: preparar también desplaza al XYZ escrito. Los valores iniciales de
la GUI no se obtienen de la posición física actual; no pulses los botones
simplemente para comprobar la conexión.

La primera prueba física debe ser un desplazamiento pequeño y supervisado desde
la postura real, después de comprobar el estado y el plan. El escalado de
velocidad de la GUI no constituye una función de seguridad del robot.

Coordenadas de la GUI, en metros:

| Campo | Dirección | Coordenada ROS |
|---|---|---|
| X | Adelante/atrás | x |
| Y | Altura | z |
| Z | Izquierda/derecha, positivo a la izquierda | y |

El destino corresponde a `end_effector_link`, el montaje de la pinza, no a las
puntas. Falta calibrar el punto de agarre y la posición del tablero físico antes
de reutilizar coordenadas de ajedrez. Esta guía no inicia el tablero virtual ni
implementa el agarre de piezas.

## 6. Cerrar y volver a la simulación

Cierra la GUI y RViz, y finaliza los lanzadores de las terminales 2 y 1 con
Ctrl+C. Cerrar una ventana o cancelar una orden no sustituye la parada de
emergencia física.

Para iniciar únicamente la simulación, en una terminal de Ubuntu WSL:

```bash
cd /mnt/c/Users/Usuario/Desktop/chess-simulator
bash brazo_kinova/simular_brazo_wsl.sh
```

El lanzador `simular_brazo_wsl.cmd` de Windows también sigue siendo exclusivo
de simulación.
