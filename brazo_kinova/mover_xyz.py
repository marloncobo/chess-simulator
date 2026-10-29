#!/usr/bin/env python3
"""
GUI mínima: escribe x, y, z (metros) y el brazo va a ese punto con MoveIt 2.

La GUI usa metros: X adelante, Y altura, Z izquierda/derecha.
Se convierte al frame ROS `base_link`: (X, Z, Y). El cliente Brazo mantiene
las coordenadas ROS (x adelante, y izquierda, z arriba).

Uso:
    Terminal 1 (simulación MoveIt + RViz):
        ./simular_brazo.sh

    Terminal 2:
        source /opt/ros/humble/setup.bash
        source ~/ros2_ws/install/setup.bash
        python3 ~/ros2_ws/mover_xyz.py
"""

import math
import copy
import queue
import signal
import threading
import time
import tkinter as tk
from tkinter import ttk

import rclpy
from geometry_msgs.msg import Pose
from moveit_msgs.action import MoveGroup, ExecuteTrajectory
from moveit_msgs.srv import GetCartesianPath, GetPositionIK, GetStateValidity
from moveit_msgs.msg import Constraints, JointConstraint, OrientationConstraint
from sensor_msgs.msg import JointState
from tf2_ros import Buffer, TransformListener, TransformException
from rclpy.action import ActionClient
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.signals import SignalHandlerOptions

GRUPO = "arm"                # grupo de planificación de gen3_lite.srdf
EEF = "end_effector_link"    # link que se lleva a la coordenada
BASE = "base_link"           # frame en el que se interpretan x, y, z
VELOCIDAD = 0.2              # fracción de la velocidad máxima
PASO = 0.01                  # cuánto suma o resta cada botón + / − (1 cm)
ESPERA_MAX = 60              # solicita cancelar; no habilita otra orden hasta recibir resultado
TOL_ORIENTACION = math.radians(5)
MAX_RECORRIDO_JOINT = math.pi  # rechaza planes con más de 180° acumulados por articulación
JOINTS = [f"joint_{i}" for i in range(1, 7)]
# Límites del URDF Gen3 Lite de Kortex. Solo se usan para las semillas de IK.
LIMITES_LITE = (2.68, 2.61, 2.61, 2.60, 2.53, 2.60)


def semillas_ik(inicial):
    """Hipótesis de búsqueda, nunca órdenes ni posturas intermedias ejecutadas."""
    actual = [inicial[n] for n in JOINTS]
    variantes = [actual, [0.0]*6]
    for signo in (-1, 1):
        valores = actual.copy()
        valores[1] += signo * 0.7
        valores[2] -= signo * 1.0
        variantes.append(valores)
        valores = actual.copy()
        valores[3] += signo * 1.0
        valores[5] -= signo * 1.0
        variantes.append(valores)
    resultado = []
    for valores in variantes:
        semilla = inicial.copy()
        semilla.update({n: max(-limite, min(limite, v))
                        for n, v, limite in zip(JOINTS, valores, LIMITES_LITE)})
        if semilla not in resultado:
            resultado.append(semilla)
    return resultado


def rutas_intermedias(origen, destino):
    """Candidatas cartesianas; MoveIt debe validar cada ruta completa."""
    def punto(x, y, z):
        p = copy.deepcopy(destino)
        p.position.x, p.position.y, p.position.z = float(x), float(y), float(z)
        return p

    sx, sy, sz = origen
    dx, dy, dz = destino.position.x, destino.position.y, destino.position.z
    # Una orden exclusivamente vertical nunca se convierte en un rodeo.
    if math.hypot(dx-sx, dy-sy) < 0.002:
        return []
    altura = max(sz, dz) + 0.05
    exterior = max(sx, dx, 0.18) + 0.055
    nivel = max(sz, dz)
    return [
        [punto(sx, sy, altura), punto(dx, dy, altura), destino],
        [punto(exterior, sy, nivel), punto(exterior, dy, nivel),
         punto(dx, dy, nivel), destino],
        [punto(sx, sy, altura), punto(exterior, sy, altura),
         punto(exterior, dy, altura), punto(dx, dy, altura), destino],
    ]


def orientacion_abajo(tolerancia=TOL_ORIENTACION):
    """El +Z del montaje de la pinza Gen3 Lite 2F apunta a los dedos; Rx(pi) lo baja."""
    restriccion = OrientationConstraint()
    restriccion.header.frame_id = BASE
    restriccion.link_name = EEF
    restriccion.orientation.x = 1.0
    restriccion.orientation.w = 0.0
    restriccion.absolute_x_axis_tolerance = tolerancia
    restriccion.absolute_y_axis_tolerance = tolerancia
    restriccion.absolute_z_axis_tolerance = tolerancia
    restriccion.parameterization = OrientationConstraint.ROTATION_VECTOR
    restriccion.weight = 1.0
    return restriccion


def recorrido_articular(trayectoria, inicial):
    """Suma diferencias sin envolver ángulos: una vuelta de 2π debe detectarse."""
    nombres = list(trayectoria.joint_names)
    if set(nombres) != set(JOINTS) or not trayectoria.points:
        raise ValueError("La trayectoria no contiene las seis articulaciones esperadas.")
    anterior = [inicial[n] for n in nombres]
    recorrido = [0.0] * len(nombres)
    for punto in trayectoria.points:
        if len(punto.positions) != len(nombres) or not all(map(math.isfinite, punto.positions)):
            raise ValueError("MoveIt devolvió una trayectoria inválida.")
        for i, valor in enumerate(punto.positions):
            recorrido[i] += abs(valor - anterior[i])
        anterior = punto.positions
    return max(recorrido)

# Códigos de moveit_msgs/MoveItErrorCodes, con el significado práctico.
MENSAJES = {
    1: "Listo: el brazo llegó al punto.",
    -1: "MoveIt no encontró trayectoria hasta ese punto.",
    -4: "El controlador falló al ejecutar el movimiento.",
    -10: "La posición actual del brazo está en colisión; muévelo antes.",
    -12: "El punto de destino está en colisión.",
    -2: "MoveIt descartó el plan por incumplir restricciones. No se ejecutó.",
    -6: "La planificación agotó el tiempo disponible.",
    -7: "Movimiento cancelado.",
    -11: "La postura inicial no cumple la orientación. Prepara primero la pinza.",
    -31: "No se encontró una postura válida del Gen3 Lite con la pinza hacia abajo. Prueba un punto más cercano; el alcance depende también de la orientación y las colisiones.",
    99999: "MoveIt no pudo resolver la solicitud. Este fallo general no confirma que el punto esté fuera de alcance.",
}


class Brazo(Node):
    """Manda la coordenada al action /move_action de MoveIt."""

    def __init__(self):
        super().__init__("mover_xyz")
        self.cliente = ActionClient(self, MoveGroup, "/move_action")
        self.ejecutor = ActionClient(self, ExecuteTrajectory, "/execute_trajectory")
        self.cartesiano = self.create_client(GetCartesianPath, "/compute_cartesian_path")
        self.ik = self.create_client(GetPositionIK, "/compute_ik")
        self.validez = self.create_client(GetStateValidity, "/check_state_validity")
        self.tf = Buffer()
        self.listener = TransformListener(self.tf, self)
        self.posiciones = {}
        self.ultima_lectura = 0.0
        self.create_subscription(JointState, "/joint_states", self.leer_estado, 10)
        self.ocupado = False
        self.goal_handle = None
        self.cerrando = False
        self.cancelado = False

    def leer_estado(self, msg):
        self.posiciones = dict(zip(msg.name, msg.position))
        self.ultima_lectura = time.monotonic()

    def mover(self, x, y, z, al_terminar, preparar=False, permitir_curva=True):
        """Envía (x, y, z) sin bloquear; llama al_terminar(codigo) al acabar."""
        if self.ocupado:
            return
        inicial = self.posiciones.copy()
        if time.monotonic() - self.ultima_lectura > 2 or not all(n in inicial for n in JOINTS):
            al_terminar("No hay un estado reciente de las seis articulaciones.")
            return
        if not preparar:
            try:
                transformacion = self.tf.lookup_transform(BASE, EEF, rclpy.time.Time()).transform
                q = transformacion.rotation
                # Distancia a Rx(pi), independiente del signo del cuaternión.
                error = 2 * math.acos(min(1.0, abs(q.x)))
                if error > TOL_ORIENTACION:
                    al_terminar("Primero pulsa Preparar pinza: la postura actual no apunta hacia abajo.")
                    return
            except TransformException:
                al_terminar("Aún no hay transformación de la pinza. Espera y vuelve a intentar.")
                return
        self.ocupado = True
        self.cancelado = False
        destino = Pose()
        destino.position.x, destino.position.y, destino.position.z = x, y, z
        destino.orientation = orientacion_abajo().orientation
        if not preparar:
            destino.orientation = q  # conserva la orientación ya preparada, sin reajustar la muñeca

        vertical = False
        rutas = []
        if not preparar:
            t = transformacion.translation
            vertical = math.hypot(x-t.x, y-t.y) < 0.002
            if permitir_curva:
                rutas = rutas_intermedias((t.x, t.y, t.z), destino)
        candidatos = []
        seleccion = 0

        goal = MoveGroup.Goal()
        goal.request.group_name = GRUPO
        goal.request.start_state.is_diff = True
        # Incluye también el estado de la pinza para comprobar colisiones en IK.
        goal.request.start_state.joint_state.name = list(inicial)
        goal.request.start_state.joint_state.position = list(inicial.values())
        if not preparar:
            goal.request.path_constraints.orientation_constraints = [orientacion_abajo()]
        goal.request.num_planning_attempts = 10
        goal.request.allowed_planning_time = 5.0
        goal.request.max_velocity_scaling_factor = VELOCIDAD
        goal.request.max_acceleration_scaling_factor = VELOCIDAD
        goal.planning_options.plan_only = True

        def terminar(codigo):
            self.ocupado = False
            self.goal_handle = None
            al_terminar(codigo)

        def ejecutado(futuro):
            try:
                terminar(futuro.result().result.error_code.val)
            except Exception as exc:
                terminar(f"Error de ejecución: {exc}")

        def planificado(futuro):
            try:
                resultado = futuro.result().result
                if resultado.error_code.val in (-1, -2, -31, 99999) and siguiente_postura():
                    return
                ejecutar_plan(resultado.error_code.val, resultado.planned_trajectory)
            except Exception as exc:
                terminar(f"Error al revisar el plan: {exc}")

        def ejecutar_plan(codigo, trayectoria):
            try:
                if codigo != 1:
                    terminar(codigo)
                    return
                recorrido = recorrido_articular(trayectoria.joint_trajectory, inicial)
                if recorrido > MAX_RECORRIDO_JOINT:
                    if (preparar or (permitir_curva and not vertical)) and siguiente_postura():
                        return
                    terminar(f"Plan rechazado: una articulación recorrería {math.degrees(recorrido):.0f}°. Prueba un punto intermedio.")
                    return
                if self.cerrando or self.cancelado:
                    terminar("Sesión cerrada; no se ejecutó el plan.")
                    return
                orden = ExecuteTrajectory.Goal()
                orden.trajectory = trayectoria
                self.ejecutor.send_goal_async(orden).add_done_callback(aceptar_ejecucion)
            except Exception as exc:
                terminar(f"Error al revisar el plan: {exc}")

        def aceptar_ejecucion(futuro):
            try:
                self.goal_handle = futuro.result()
                if self.goal_handle is None or not self.goal_handle.accepted:
                    terminar("MoveIt rechazó la ejecución.")
                    return
                if self.cerrando or self.cancelado:
                    self.goal_handle.cancel_goal_async()
                self.goal_handle.get_result_async().add_done_callback(ejecutado)
            except Exception as exc:
                terminar(f"Error al iniciar ejecución: {exc}")

        def aceptada(futuro):
            try:
                self.goal_handle = futuro.result()
                if self.goal_handle is None or not self.goal_handle.accepted:
                    terminar(None)
                    return
                if self.cerrando or self.cancelado:
                    self.goal_handle.cancel_goal_async()
                self.goal_handle.get_result_async().add_done_callback(planificado)
            except Exception as exc:
                terminar(f"Error de planificación: {exc}")

        def plan_curvo():
            if self.cerrando or self.cancelado:
                terminar("Solicitud cancelada; no se ejecutó el plan.")
            else:
                self.cliente.send_goal_async(goal).add_done_callback(aceptada)

        def seleccionar_postura():
            restricciones = Constraints()
            for nombre in JOINTS:
                joint = JointConstraint()
                joint.joint_name = nombre
                joint.position = candidatos[seleccion][nombre]
                joint.tolerance_above = joint.tolerance_below = 0.001
                joint.weight = 1.0
                restricciones.joint_constraints.append(joint)
            goal.request.goal_constraints = [restricciones]

        def siguiente_postura():
            nonlocal seleccion
            if self.cancelado or self.cerrando or seleccion+1 >= min(3, len(candidatos)):
                return False
            seleccion += 1
            seleccionar_postura()
            self.get_logger().info('Probando otra solución articular del destino.')
            plan_curvo()
            return True

        def plan_recto(waypoints=None):
            if self.cancelado or self.cerrando:
                terminar('Solicitud cancelada; no se ejecutó el plan.')
                return
            # IK incremental desde la postura actual: evita cambiar de rama por
            # una solución aleatoria de OMPL. Nunca ejecuta una ruta parcial.
            peticion = GetCartesianPath.Request()
            peticion.header.frame_id = BASE
            peticion.start_state = goal.request.start_state
            peticion.group_name = GRUPO
            peticion.link_name = EEF
            peticion.waypoints = waypoints if waypoints is not None else [destino]
            peticion.max_step = 0.005
            peticion.jump_threshold = 5.0
            peticion.revolute_jump_threshold = math.radians(20)
            peticion.avoid_collisions = True
            peticion.path_constraints = goal.request.path_constraints
            peticion.max_velocity_scaling_factor = VELOCIDAD
            peticion.max_acceleration_scaling_factor = VELOCIDAD

            def calculado(futuro):
                try:
                    resultado = futuro.result()
                    if self.cancelado or self.cerrando:
                        terminar('Solicitud cancelada; no se ejecutó el plan.')
                    elif resultado.error_code.val == 1 and resultado.fraction >= 0.999999:
                        ejecutar_plan(1, resultado.solution)
                    elif resultado.error_code.val not in (1, -1, -31):
                        terminar(resultado.error_code.val)
                    else:
                        if rutas:
                            self.get_logger().info('Recta incompleta; comprobando una ruta por puntos intermedios.')
                            plan_recto(rutas.pop(0))
                        elif permitir_curva and not vertical:
                            self.get_logger().info("Recta incompleta; buscando ruta curva con orientación restringida.")
                            plan_curvo()
                        else:
                            detalle = 'La subida/bajada debe ser recta; no se permite un desvío lateral.' if vertical else 'Activa Permitir ruta curva o elige un punto intermedio.'
                            terminar(f"La postura de destino tiene solución, pero solo se calculó el {100*resultado.fraction:.0f}% de la recta. No se ejecutó. {detalle}")
                except Exception as exc:
                    terminar(f"Error de trayectoria cartesiana: {exc}")

            self.cartesiano.call_async(peticion).add_done_callback(calculado)

        # Distingue la existencia de una postura de destino de la existencia
        # de una ruta hasta ella. La búsqueda usa la postura actual como semilla.
        consulta = GetPositionIK.Request()
        consulta.ik_request.group_name = GRUPO
        consulta.ik_request.ik_link_name = EEF
        consulta.ik_request.robot_state = goal.request.start_state
        consulta.ik_request.pose_stamped.header.frame_id = BASE
        consulta.ik_request.pose_stamped.pose = destino
        consulta.ik_request.avoid_collisions = True
        consulta.ik_request.timeout.sec = 1

        semillas = semillas_ik(inicial)

        def consultar_semilla():
            peticion = copy.deepcopy(consulta)
            semilla = semillas.pop(0)
            peticion.ik_request.robot_state.joint_state.name = list(semilla)
            peticion.ik_request.robot_state.joint_state.position = list(semilla.values())
            peticion.ik_request.timeout.sec = 0
            peticion.ik_request.timeout.nanosec = 400000000
            self.ik.call_async(peticion).add_done_callback(postura_calculada)

        def diagnosticar():
            # Solo diagnóstico: esta solución SIN filtro de colisión jamás se ejecuta.
            peticion = copy.deepcopy(consulta)
            peticion.ik_request.avoid_collisions = False

            def sin_filtro(futuro):
                try:
                    resultado = futuro.result()
                    if self.cancelado or self.cerrando:
                        terminar('Solicitud cancelada.')
                    elif resultado.error_code.val != 1:
                        terminar('No se encontró postura tras probar varias semillas con la pinza hacia abajo. Puede depender de límites, orientación o singularidad; no hay un límite impuesto en el centro del tablero.')
                    else:
                        validacion = GetStateValidity.Request()
                        validacion.robot_state = resultado.solution
                        validacion.group_name = GRUPO
                        self.validez.call_async(validacion).add_done_callback(colisiones)
                except Exception as exc:
                    terminar(f'No se pudo completar el diagnóstico de IK: {exc}')

            def colisiones(futuro):
                try:
                    resultado = futuro.result()
                    if self.cancelado or self.cerrando:
                        terminar('Solicitud cancelada.')
                    elif resultado.contacts:
                        pares = sorted({f'{c.contact_body_1} ↔ {c.contact_body_2}' for c in resultado.contacts})
                        terminar('La postura de diagnóstico está en colisión: ' + '; '.join(pares[:3]) + '. No se movió el brazo. Prueba más altura o separación.')
                    else:
                        terminar('La búsqueda con colisiones activadas no encontró solución. No se movió el brazo; prueba otra altura o un punto intermedio.')
                except Exception as exc:
                    terminar(f'No se pudo verificar la colisión: {exc}')

            self.ik.call_async(peticion).add_done_callback(sin_filtro)

        def postura_calculada(futuro):
            try:
                resultado = futuro.result()
                if self.cerrando or self.cancelado:
                    terminar("Solicitud cancelada; no se ejecutó el plan.")
                    return
                if resultado.error_code.val not in (1, -31):
                    terminar(resultado.error_code.val)
                    return
                if resultado.error_code.val == 1:
                    solucion = dict(zip(resultado.solution.joint_state.name,
                                        resultado.solution.joint_state.position))
                    if not all(n in solucion and math.isfinite(solucion[n]) for n in JOINTS):
                        raise ValueError('La respuesta IK no contiene seis ángulos válidos.')
                    if not any(all(abs(s[n]-solucion[n]) < 0.001 for n in JOINTS) for s in candidatos):
                        candidatos.append(solucion)
                if semillas:
                    consultar_semilla()
                    return
                if not candidatos:
                    diagnosticar()
                    return
                candidatos.sort(key=lambda s: sum((s[n]-inicial[n])**2 for n in JOINTS))
                seleccionar_postura()
                if preparar:
                    plan_curvo()
                else:
                    plan_recto()
            except Exception as exc:
                terminar(f"Error al calcular la postura de destino: {exc}")

        consultar_semilla()

    def listo(self):
        return (self.cliente.server_is_ready() and self.ejecutor.server_is_ready()
                and self.cartesiano.service_is_ready() and self.ik.service_is_ready()
                and self.validez.service_is_ready())

    def cancelar(self):
        self.cancelado = True
        if self.goal_handle is not None:
            self.goal_handle.cancel_goal_async()


class App:
    def __init__(self, root, brazo):
        self.root, self.brazo = root, brazo
        self.resultados = queue.Queue()
        self.en_movimiento = False
        self.espera = None
        root.title("Kinova Gen3 Lite — Mover a (x, y, z)")

        marco = ttk.Frame(root, padding=16)
        marco.grid()
        ttk.Label(marco, text="Coordenada del efector en metros",
                  font=("", 11, "bold")).grid(row=0, column=0, columnspan=4, pady=(0, 10))

        self.casillas = {}
        for i, (eje, inicial, etiqueta) in enumerate((
                ("x", 0.25, "X · Adelante/atrás"),
                ("y", 0.30, "Y · Altura"),
                ("z", 0.0, "Z · Izquierda/derecha"))):
            fila = i + 1
            ttk.Label(marco, text=f"{etiqueta}:").grid(row=fila, column=0, sticky="e", padx=(0, 6))
            tk.Button(marco, text="−", width=2,
                      command=lambda e=eje: self.ajustar(e, -1)).grid(row=fila, column=1)
            entrada = ttk.Entry(marco, width=10, justify="right")
            entrada.insert(0, f"{inicial:.2f}")
            entrada.grid(row=fila, column=2, padx=4, pady=3)
            entrada.bind("<Return>", lambda _evento: self.mover())
            tk.Button(marco, text="+", width=2,
                      command=lambda e=eje: self.ajustar(e, +1)).grid(row=fila, column=3)
            self.casillas[eje] = entrada

        ttk.Label(marco, text=f"+ / − suman o restan {PASO * 100:.0f} cm",
                  foreground="gray").grid(row=4, column=0, columnspan=4, pady=(4, 0))

        self.boton = tk.Button(marco, text="Mover", bg="#1565c0", fg="white",
                               font=("", 10, "bold"), width=16, command=self.mover)
        self.boton.grid(row=5, column=0, columnspan=4, pady=12)

        self.preparar = ttk.Button(marco, text="Preparar pinza hacia abajo",
                                  command=lambda: self.mover(preparar=True))
        self.preparar.grid(row=6, column=0, columnspan=4)
        self.permitir_curva = tk.BooleanVar(value=True)
        ttk.Checkbutton(marco, text="Permitir ruta curva si falla la recta",
                        variable=self.permitir_curva).grid(row=7, column=0, columnspan=4)
        self.estado = ttk.Label(marco, text="Gen3 Lite: preparar también se mueve al XYZ indicado. XYZ es el montaje de la pinza, no las puntas.", foreground="gray", wraplength=320)
        self.estado.grid(row=8, column=0, columnspan=4)
        self.root.after(100, self.recibir)

    def recibir(self):
        while not self.resultados.empty():
            self.terminado(self.resultados.get_nowait())
        self.root.after(100, self.recibir)

    def ajustar(self, eje, signo):
        """Cambia la casilla un paso. El brazo se mueve al pulsar Mover."""
        try:
            valor = float(self.casillas[eje].get())
        except ValueError:
            valor = 0.0
        self.casillas[eje].delete(0, tk.END)
        self.casillas[eje].insert(0, f"{valor + signo * PASO:.2f}")

    def mover(self, preparar=False):
        if self.en_movimiento:
            return
        try:
            x, y, z = (float(self.casillas[eje].get()) for eje in "xyz")
            if not all(map(math.isfinite, (x, y, z))):
                raise ValueError
        except ValueError:
            self.estado.config(text="Escribe números con punto decimal (0.45).",
                               foreground="#c62828")
            return
        if not self.brazo.listo():
            self.estado.config(text="MoveIt no responde. Lanza ./simular_brazo.sh",
                               foreground="#c62828")
            return
        self.boton.config(state="disabled")
        self.preparar.config(state="disabled")
        self.en_movimiento = True
        self.estado.config(text=f"Moviendo a ({x}, {y}, {z})…", foreground="#1565c0")
        # Una cola evita manipular Tkinter desde el hilo de ROS.
        self.brazo.mover(x, z, y, self.resultados.put, preparar=preparar,
                         permitir_curva=self.permitir_curva.get())
        # Al agotar el tiempo se cancela sin permitir ejecuciones superpuestas.
        self.espera = self.root.after(ESPERA_MAX * 1000, self.sin_respuesta)

    def sin_respuesta(self):
        self.brazo.cancelar()
        self.estado.config(text="Tiempo agotado: cancelación solicitada; esperando confirmación. No se enviarán otras órdenes.",
                           foreground="#c62828")

    def terminado(self, codigo):
        if self.espera is not None:
            self.root.after_cancel(self.espera)
            self.espera = None
        self.en_movimiento = False
        self.boton.config(state="normal")
        self.preparar.config(state="normal")
        if isinstance(codigo, str):
            self.estado.config(text=codigo, foreground="#c62828")
            return
        if codigo is None:
            self.estado.config(text="MoveIt rechazó la orden.", foreground="#c62828")
            return
        mensaje = MENSAJES.get(codigo, f"MoveIt devolvió el código {codigo}.")
        self.estado.config(text=mensaje, foreground="#2e7d32" if codigo == 1 else "#c62828")


def main():
    # Ctrl + C lo gestiona la ventana (cerrándola); el manejador de rclpy solo
    # apagaría ROS y dejaría la ventana abierta y sin respuesta.
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    brazo = Brazo()
    # Hay que poder parar el executor antes de destruir el nodo, o rclpy
    # aborta el proceso al salir ("terminate called without an active exception").
    executor = SingleThreadedExecutor()
    executor.add_node(brazo)
    hilo = threading.Thread(target=executor.spin, daemon=True)
    hilo.start()
    try:
        root = tk.Tk()
        App(root, brazo)
        root.protocol("WM_DELETE_WINDOW", root.destroy)   # la X cierra el programa
        # Ctrl + C y Ctrl + Z (en la terminal o en la ventana) cierran la
        # interfaz, igual que la X. Ctrl + Z normalmente solo pausa el
        # proceso y deja la ventana congelada; aquí se reemplaza por cerrar.
        signal.signal(signal.SIGINT, lambda *_: root.destroy())
        signal.signal(signal.SIGTSTP, lambda *_: root.destroy())
        root.bind_all("<Control-z>", lambda _evento: root.destroy())
        root.bind_all("<Control-Z>", lambda _evento: root.destroy())

        # Python solo atiende señales cuando corre código Python; mientras Tk
        # espera eventos no lo hace, así que se le da un turno cada 200 ms.
        def latido():
            root.after(200, latido)
        latido()
        root.mainloop()
    finally:
        brazo.cerrando = True
        brazo.cancelar()
        executor.shutdown()
        hilo.join(timeout=2.0)
        brazo.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
