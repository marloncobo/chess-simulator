#!/usr/bin/env python3
"""
GUI mínima: escribe x, y, z (metros) y el brazo va a ese punto con MoveIt 2.

Las coordenadas son metros en el frame `base_link` (la base del brazo):
    x → hacia adelante      y → hacia la izquierda      z → hacia arriba

Uso:
    Terminal 1 (simulación MoveIt + RViz):
        ./simular_brazo.sh

    Terminal 2:
        source /opt/ros/humble/setup.bash
        source ~/ros2_ws/install/setup.bash
        python3 ~/ros2_ws/mover_xyz.py
"""

import signal
import threading
import tkinter as tk
from tkinter import ttk

import rclpy
from geometry_msgs.msg import Pose
from moveit_msgs.action import MoveGroup
from moveit_msgs.msg import BoundingVolume, Constraints, PositionConstraint
from rclpy.action import ActionClient
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.signals import SignalHandlerOptions
from shape_msgs.msg import SolidPrimitive

GRUPO = "manipulator"        # grupo de planificación del gen3.srdf
EEF = "end_effector_link"    # link que se lleva a la coordenada
BASE = "base_link"           # frame en el que se interpretan x, y, z
TOLERANCIA = 0.01            # metros de margen para considerar alcanzado el punto
VELOCIDAD = 0.2              # fracción de la velocidad máxima
PASO = 0.01                  # cuánto suma o resta cada botón + / − (1 cm)
ESPERA_MAX = 60              # segundos sin respuesta de MoveIt antes de soltar el botón

# Códigos de moveit_msgs/MoveItErrorCodes, con el significado práctico.
MENSAJES = {
    1: "Listo: el brazo llegó al punto.",
    -1: "MoveIt no encontró trayectoria hasta ese punto.",
    -4: "El controlador falló al ejecutar el movimiento.",
    -10: "La posición actual del brazo está en colisión; muévelo antes.",
    -12: "El punto de destino está en colisión.",
    -31: "Ese punto no es alcanzable (sin cinemática inversa).",
    99999: "Punto fuera del alcance del brazo (llega a unos 0.9 m de la base).",
}


class Brazo(Node):
    """Manda la coordenada al action /move_action de MoveIt."""

    def __init__(self):
        super().__init__("mover_xyz")
        self.cliente = ActionClient(self, MoveGroup, "/move_action")

    def mover(self, x, y, z, al_terminar):
        """Envía (x, y, z) sin bloquear; llama al_terminar(codigo) al acabar."""
        destino = Pose()
        destino.position.x, destino.position.y, destino.position.z = x, y, z
        destino.orientation.w = 1.0

        esfera = SolidPrimitive()
        esfera.type = SolidPrimitive.SPHERE
        esfera.dimensions = [TOLERANCIA]
        region = BoundingVolume()
        region.primitives = [esfera]
        region.primitive_poses = [destino]

        # Solo se restringe la posición: la orientación queda libre, así que
        # MoveIt puede elegir cualquier giro del efector que alcance el punto.
        posicion = PositionConstraint()
        posicion.header.frame_id = BASE
        posicion.link_name = EEF
        posicion.constraint_region = region
        posicion.weight = 1.0
        restricciones = Constraints()
        restricciones.position_constraints = [posicion]

        goal = MoveGroup.Goal()
        goal.request.group_name = GRUPO
        goal.request.goal_constraints = [restricciones]
        goal.request.start_state.is_diff = True   # parte del estado actual del robot
        goal.request.num_planning_attempts = 10
        goal.request.allowed_planning_time = 5.0
        goal.request.max_velocity_scaling_factor = VELOCIDAD
        goal.request.max_acceleration_scaling_factor = VELOCIDAD
        goal.planning_options.plan_only = False

        def aceptada(futuro):
            handle = futuro.result()
            if handle is None or not handle.accepted:
                al_terminar(None)
                return
            handle.get_result_async().add_done_callback(
                lambda f: al_terminar(f.result().result.error_code.val))

        self.cliente.send_goal_async(goal).add_done_callback(aceptada)

    def listo(self):
        return self.cliente.wait_for_server(timeout_sec=2.0)


class App:
    def __init__(self, root, brazo):
        self.root, self.brazo = root, brazo
        root.title("Mover brazo a (x, y, z)")

        marco = ttk.Frame(root, padding=16)
        marco.grid()
        ttk.Label(marco, text="Coordenada del efector en metros",
                  font=("", 11, "bold")).grid(row=0, column=0, columnspan=4, pady=(0, 10))

        self.casillas = {}
        for i, (eje, inicial) in enumerate((("x", 0.45), ("y", 0.0), ("z", 0.45))):
            fila = i + 1
            ttk.Label(marco, text=f"{eje}:").grid(row=fila, column=0, sticky="e", padx=(0, 6))
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

        self.estado = ttk.Label(marco, text="Listo.", foreground="gray", wraplength=260)
        self.estado.grid(row=6, column=0, columnspan=4)

    def ajustar(self, eje, signo):
        """Cambia la casilla un paso. El brazo se mueve al pulsar Mover."""
        try:
            valor = float(self.casillas[eje].get())
        except ValueError:
            valor = 0.0
        self.casillas[eje].delete(0, tk.END)
        self.casillas[eje].insert(0, f"{valor + signo * PASO:.2f}")

    def mover(self):
        try:
            x, y, z = (float(self.casillas[eje].get()) for eje in "xyz")
        except ValueError:
            self.estado.config(text="Escribe números con punto decimal (0.45).",
                               foreground="#c62828")
            return
        if not self.brazo.listo():
            self.estado.config(text="MoveIt no responde. Lanza ./simular_brazo.sh",
                               foreground="#c62828")
            return
        self.boton.config(state="disabled")
        self.estado.config(text=f"Moviendo a ({x}, {y}, {z})…", foreground="#1565c0")
        # El resultado llega en el hilo de ROS: se devuelve al de Tkinter con after.
        self.brazo.mover(x, y, z, lambda codigo: self.root.after(0, self.terminado, codigo))
        # Si MoveIt nunca contesta, el botón no debe quedar bloqueado para siempre.
        self.espera = self.root.after(ESPERA_MAX * 1000, self.sin_respuesta)

    def sin_respuesta(self):
        self.boton.config(state="normal")
        self.estado.config(text="MoveIt no respondió a tiempo. Prueba de nuevo.",
                           foreground="#c62828")

    def terminado(self, codigo):
        self.root.after_cancel(self.espera)
        self.boton.config(state="normal")
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
        executor.shutdown()
        hilo.join(timeout=2.0)
        brazo.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
