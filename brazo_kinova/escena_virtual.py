#!/usr/bin/env python3
"""Tablero y pieza provisional: geometría de colisión en MoveIt y marcas en RViz.

La pieza es un cilindro, no una simulación física de un caballo ni un agarre.
No envía órdenes al brazo ni a la pinza. Requiere move_group iniciado.
"""
import argparse
import json
import math
from pathlib import Path

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy
from geometry_msgs.msg import Pose
from moveit_msgs.msg import CollisionObject
from moveit_msgs.srv import ApplyPlanningScene
from shape_msgs.msg import SolidPrimitive
from visualization_msgs.msg import Marker, MarkerArray

FRAME = 'base_link'
TABLERO = 'semillero_tablero_virtual'
PIEZA = 'semillero_pieza_virtual'
CONFIG = Path(__file__).with_name('escena_virtual.json')


def cargar_config(ruta):
    config = json.loads(Path(ruta).read_text(encoding='utf-8'))
    for clave in ('lado_tablero_m', 'centro_x_m', 'centro_y_m', 'superficie_z_m',
                  'grosor_tablero_m', 'altura_pieza_m', 'diametro_pieza_m'):
        valor = config[clave]
        if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor):
            raise ValueError(f'{clave} debe ser un número finito en metros.')
    for clave in ('lado_tablero_m', 'grosor_tablero_m', 'altura_pieza_m', 'diametro_pieza_m'):
        if config[clave] <= 0:
            raise ValueError(f'{clave} debe ser mayor que cero.')
    if config['diametro_pieza_m'] >= config['lado_tablero_m']/8:
        raise ValueError('La pieza debe ser más estrecha que una casilla.')
    casilla = config['casilla_pieza']
    if not isinstance(casilla, str) or len(casilla) != 2 or casilla[0] not in 'abcdefgh' or casilla[1] not in '12345678':
        raise ValueError('casilla_pieza debe estar entre a1 y h8, en minúsculas.')
    return config


def centro_casilla(config, casilla):
    """Filas 1→8 avanzan en +X; columnas a→h avanzan en +Y de la base."""
    paso = config['lado_tablero_m']/8
    return (config['centro_x_m'] + (int(casilla[1])-4.5)*paso,
            config['centro_y_m'] + ('abcdefgh'.index(casilla[0])-3.5)*paso)


def pose(x, y, z):
    p = Pose()
    p.position.x, p.position.y, p.position.z = float(x), float(y), float(z)
    p.orientation.w = 1.0
    return p


def objetos(config):
    tablero = CollisionObject()
    tablero.id, tablero.header.frame_id = TABLERO, FRAME
    caja = SolidPrimitive()
    caja.type = SolidPrimitive.BOX
    caja.dimensions = [float(config['lado_tablero_m'])]*2 + [float(config['grosor_tablero_m'])]
    tablero.primitives = [caja]
    tablero.primitive_poses = [pose(config['centro_x_m'], config['centro_y_m'],
                                     config['superficie_z_m']-config['grosor_tablero_m']/2)]
    tablero.operation = CollisionObject.ADD
    pieza = CollisionObject()
    pieza.id, pieza.header.frame_id = PIEZA, FRAME
    cilindro = SolidPrimitive()
    cilindro.type = SolidPrimitive.CYLINDER
    cilindro.dimensions = [float(config['altura_pieza_m']), config['diametro_pieza_m']/2]
    x, y = centro_casilla(config, config['casilla_pieza'])
    pieza.primitives = [cilindro]
    pieza.primitive_poses = [pose(x, y, config['superficie_z_m']+config['altura_pieza_m']/2)]
    pieza.operation = CollisionObject.ADD
    return [tablero, pieza]


def marcas(config):
    resultado = MarkerArray()

    def agregar(tipo, posicion, escala, color):
        m = Marker()
        m.header.frame_id = FRAME
        m.ns, m.id, m.type = 'semillero_escena', len(resultado.markers), tipo
        m.action, m.pose = Marker.ADD, posicion
        m.scale.x, m.scale.y, m.scale.z = escala
        m.color.r, m.color.g, m.color.b, m.color.a = color
        resultado.markers.append(m)
        return m

    paso = config['lado_tablero_m']/8
    z = config['superficie_z_m']
    for fila in range(8):
        for columna in range(8):
            casilla = f"{'abcdefgh'[columna]}{fila+1}"
            x, y = centro_casilla(config, casilla)
            color = (0.83, 0.74, 0.58, 1.0) if (fila+columna)%2 else (0.22, 0.14, 0.09, 1.0)
            agregar(Marker.CUBE, pose(x, y, z-config['grosor_tablero_m']/2),
                    (paso, paso, float(config['grosor_tablero_m'])), color)
    x, y = centro_casilla(config, config['casilla_pieza'])
    agregar(Marker.CYLINDER, pose(x, y, z+config['altura_pieza_m']/2),
            (float(config['diametro_pieza_m']), float(config['diametro_pieza_m']),
             float(config['altura_pieza_m'])), (0.95, 0.95, 0.95, 1.0))
    for casilla in ('a1', 'h1', 'a8', 'h8'):
        x, y = centro_casilla(config, casilla)
        m = agregar(Marker.TEXT_VIEW_FACING, pose(x, y, z+0.006),
                    (0.0, 0.0, 0.018), (0.2, 0.7, 1.0, 1.0))
        m.text = casilla
    return resultado


class EscenaVirtual(Node):
    def __init__(self, config):
        super().__init__('escena_virtual_ajedrez')
        self.config = config
        self.aplicar = self.create_client(ApplyPlanningScene, '/apply_planning_scene')
        qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.publicador = self.create_publisher(MarkerArray, '/semillero/escena_virtual', qos)
        self.marcadores = marcas(config)

    def iniciar(self):
        if not self.aplicar.wait_for_service(timeout_sec=30):
            raise RuntimeError('MoveIt no ofrece /apply_planning_scene. Inicia la simulación primero.')
        solicitud = ApplyPlanningScene.Request()
        solicitud.scene.is_diff = True
        solicitud.scene.robot_state.is_diff = True
        solicitud.scene.world.collision_objects = objetos(self.config)
        futuro = self.aplicar.call_async(solicitud)
        rclpy.spin_until_future_complete(self, futuro, timeout_sec=10)
        if not futuro.done() or not futuro.result().success:
            raise RuntimeError('MoveIt no confirmó la incorporación de los objetos.')
        self.publicador.publish(self.marcadores)
        # Reenvía las marcas para suscriptores RViz que se conecten más tarde.
        self.create_timer(1.0, lambda: self.publicador.publish(self.marcadores))
        x, y = centro_casilla(self.config, self.config['casilla_pieza'])
        self.get_logger().info(
            f"Tablero y pieza añadidos a MoveIt. Pieza en {self.config['casilla_pieza']}: "
            f"x={x:.4f}, y={y:.4f}, base z={self.config['superficie_z_m']:.3f} m. "
            'Geometría provisional; aún no hay agarre ni física de contacto.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=CONFIG)
    args = parser.parse_args()
    config = cargar_config(args.config)
    rclpy.init()
    node = EscenaVirtual(config)
    try:
        node.iniciar()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
