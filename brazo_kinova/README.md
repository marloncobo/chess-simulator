# Brazo Kinova: mover el efector a una coordenada (x, y, z)

Interfaz mínima para llevar el efector final del Kinova Gen3 Lite (6 DoF + pinza
Gen3 Lite 2F) a una coordenada con MoveIt 2, simulado en RViz. Se usa el modelo
Kortex del Lite con sus dimensiones, límites y pinza, sin escalar el modelo Gen3.
El grupo de planificación es `arm`; el montaje sigue siendo `end_effector_link`.

| Archivo | Qué hace |
|---|---|
| `simular_brazo.sh` | Inicia el flujo completo Lite en Ubuntu con `~/ros2_ws` como workspace por defecto. |
| `simular_brazo_wsl.cmd` | Inicia desde Windows la simulación y la GUI en Ubuntu WSL. |
| `simular_brazo_wsl.sh` | Carga el workspace configurable, espera MoveIt y administra los procesos de su sesión. |
| `brazo.rviz` | Vista de RViz que solo muestra el brazo moviéndose en tiempo real (sin la trayectoria planificada ni brazos fantasma) y los ejes de la base. |
| `mover_xyz.py` | Ventana con casillas x, y, z, botones − / + (1 cm) y botón **Mover**. |
| `escena_virtual.py` | Añade tablero y pieza como obstáculos de MoveIt y marcas de RViz. |
| `escena_virtual.json` | Medidas, ubicación del tablero y casilla de la pieza, configurables en metros. |
| `evaluar_alcance.py` | Compara las 64 casillas en una sesión ROS aislada, sin ejecutar movimientos. |

Consulta el [informe de alcance](../docs/ALCANCE_KINOVA_LITE.md) para los mapas,
las ubicaciones comparadas y las limitaciones de la prueba a 18 cm.

## Requisitos

- ROS 2 Humble y MoveIt 2.
- Workspace `~/ros2_ws` compilado con `ros2_kortex`
  (paquetes `kinova_gen3_lite_moveit_config` y `kortex_bringup`).

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
la interfaz XYZ. El lanzador WSL también añade un tablero de 44 × 44 cm y una
pieza cilíndrica de 6 cm de alto en `d4`. Ajusta `escena_virtual.json` y reinicia
para cambiar la escena; usa `--sin-tablero` para probar únicamente el brazo.
La pieza aún no se agarra ni se mueve con la pinza. Consulta [WSL.md](WSL.md)
para el sistema de coordenadas y los tamaños provisionales.
Mantén abierta la terminal; cierra la GUI o pulsa **Ctrl+C**
para cerrar los procesos de esta sesión. Este lanzador no termina otras
sesiones por nombre. El lanzador de Ubuntu comparte la misma implementación.

Consulta [WSL.md](WSL.md) para elegir distribución, dominio ROS u opciones
como `--sin-rviz` y `--sin-gui`.

## Uso desde Ubuntu

Desde `brazo_kinova/`, una terminal inicia también RViz, la GUI y el tablero:

```bash
bash simular_brazo.sh
```

Para indicar otro workspace:

```bash
bash simular_brazo.sh --workspace "$HOME/kinova_revision/ros2_ws"
```

Primero introduce una coordenada despejada y pulsa **Preparar pinza hacia abajo**.
Este botón también mueve el montaje al XYZ escrito: no solo gira la muñeca.
Empieza con `(X=0.25, Y=0.30, Z=0)` en la GUI de la simulación Lite. Este primer movimiento orienta
la pinza y puede describir una curva. Después,
escribe la coordenada (o ajústala con − / +) y pulsa **Mover** o Enter. Las
coordenadas de la GUI están en metros respecto a la base:

- **X** adelante/atrás (positivo: adelante).
- **Y** altura (positivo: arriba).
- **Z** izquierda/derecha (positivo: izquierda).

La interfaz convierte `(X, Y, Z)` a `(X, Z, Y)` para ROS. Los ejes de RViz y
`escena_virtual.json` conservan la convención ROS: X adelante, Y izquierda,
Z arriba. Las coordenadas antiguas de la GUI requieren intercambiar Y y Z.

Los traslados usan una trayectoria cartesiana recta desde la postura actual,
conservando la orientación preparada y comprobando colisiones en la escena de
MoveIt. Se prueban hasta seis semillas de cinemática inversa dentro de los límites
del Lite y se priorizan las soluciones próximas a la postura actual. Son hipótesis
del solver, no posturas que se manden directamente al brazo. Si falla el primer
plan, se pueden probar hasta tres soluciones articulares de destino.

Si está marcada **Permitir ruta curva si falla la recta**, se comprueban primero
rutas completas por puntos intermedios: elevar/trasladar/bajar y rodeos alejados
de la base. Esos puntos se generan a partir del origen y destino; no están
prevalidados. MoveIt comprueba cada ruta con las colisiones y orientación activas.
Si ninguna ruta cartesiana completa funciona, se intenta planificación general
con orientación restringida. No se garantiza encontrar una ruta por existir
posturas válidas en ambos extremos.

Las órdenes de solo altura (misma X y Z lateral en la GUI, con margen de 2 mm)
siempre exigen una recta completa, aunque la opción de curvas esté marcada. No
se sustituye una bajada de agarre por un rodeo lateral.
No se ejecutan trayectorias parciales ni planes que MoveIt considere inválidos.
Desmarca esa opción para exigir una recta; el mensaje indica el porcentaje
calculado y pide un punto intermedio si no llega al 100 %.
Para el tablero, sube primero a una altura que
supere las piezas, trasládate y luego baja. El tablero y otros obstáculos deben
estar incorporados en la escena para que se comprueben sus colisiones.

Se fija el +Z del montaje hacia -Z de `base_link`, con giro de agarre fijo.
La preparación busca esa pose mediante IK y planifica a sus ángulos articulares;
los traslados mantienen una restricción de 5° por eje. XYZ se refiere a
`end_effector_link` (montaje de la pinza), no al
punto entre las puntas de los dedos; todavía falta calibrar ese punto de agarre.
Con altura `Y=0` en la GUI (`z=0` en ROS), las puntas quedan por debajo del plano de la base. La cuadrícula de
RViz es visual y no constituye un suelo ni un tablero de colisión.

El código de fallo general `99999` no significa necesariamente fuera de alcance.
`NO_IK_SOLUTION` indica que la búsqueda no encontró una postura válida con esa
orientación; no prueba por sí solo que sea imposible. El alcance no es una esfera
de radio fijo: depende de los ejes, límites, orientación y colisiones. En la prueba
del modelo Gen3 anterior, `(0.42, 0.11, 0.76)` no produjo una solución con la pinza
hacia abajo. Esos resultados y los antiguos puntos de trabajo no deben darse
por válidos para el Lite: hay que volver a comprobarlos.

Si ninguna semilla encuentra postura evitando colisiones, se hace una consulta
adicional sin filtro exclusivamente para diagnóstico y se comprueba su validez.
Esa postura jamás se ejecuta. Si se detectan contactos se muestran los objetos o
eslabones afectados. No se eliminan el tablero ni la pieza para permitir el paso.
Una colisión de esa postura de diagnóstico no demuestra que todas las soluciones
posibles estén en colisión.

El tablero mantiene sus 44 × 44 cm y su ubicación provisional. No se ha escalado
para adaptarlo al Lite ni se garantiza el acceso a las 64 casillas; puede requerir
reubicarlo en `escena_virtual.json` según las pruebas de alcance.

Antes de ejecutar se rechazan planes con más de 180° de recorrido acumulado
en cualquier articulación. Esto evita vueltas completas; no garantiza el mínimo
recorrido global. Se mantiene el 20 % de velocidad y aceleración. El alcance
depende también de la orientación y de las colisiones.

Durante una orden no se permite enviar otra, tampoco con Enter. Si se agota
la espera se solicita cancelar y se mantiene el bloqueo hasta recibir resultado.
Cerrar la interfaz solicita cancelar; no sustituye una parada de emergencia.

La ventana se cierra con la X, `Ctrl + C` o `Ctrl + Z`. La simulación se cierra
con `Ctrl + C` en la terminal 1.
