#!/usr/bin/env python3
"""Compara posturas de las 64 casillas en ROS aislado, sin ejecutar movimientos.

Requiere cargar ROS Humble y el workspace Kortex antes de ejecutarlo.
Los resultados son búsquedas de IK con colisiones, no pruebas de agarre ni rutas.
"""
import argparse
import json
import math
import os
from pathlib import Path
import random
import signal
import subprocess
import time

import rclpy
from moveit_msgs.srv import ApplyPlanningScene, GetPositionIK, GetStateValidity, GetCartesianPath
from geometry_msgs.msg import Pose
from escena_virtual import cargar_config, centro_casilla, objetos, CONFIG
from mover_xyz import JOINTS, LIMITES_LITE, orientacion_abajo


class Evaluador:
    def __init__(self, node, intentos, tiempo):
        self.node, self.intentos, self.tiempo = node, intentos, tiempo
        self.ik = node.create_client(GetPositionIK, '/compute_ik')
        self.validar = node.create_client(GetStateValidity, '/check_state_validity')
        self.aplicar = node.create_client(ApplyPlanningScene, '/apply_planning_scene')
        self.cartesiano = node.create_client(GetCartesianPath, '/compute_cartesian_path')
        self.anterior = [0.0]*6
        rng = random.Random(73)
        self.semillas = [[0.0]*6] + [[rng.uniform(-v, v) for v in LIMITES_LITE] for _ in range(intentos)]

    def llamar(self, cliente, solicitud):
        futuro = cliente.call_async(solicitud)
        rclpy.spin_until_future_complete(self.node, futuro, timeout_sec=5)
        if not futuro.done():
            raise RuntimeError('Un servicio ROS no respondió; se detuvo la evaluación.')
        return futuro.result()

    def escena(self, config, sin_pieza=False):
        req = ApplyPlanningScene.Request()
        req.scene.is_diff = req.scene.robot_state.is_diff = True
        req.scene.world.collision_objects = objetos(config)
        if sin_pieza:
            # La sesión aislada inicia vacía y esta opción se mantiene en todo
            # el barrido; no se incorpora la pieza desde el principio.
            req.scene.world.collision_objects = req.scene.world.collision_objects[:1]
        if not self.llamar(self.aplicar, req).success:
            raise RuntimeError('MoveIt no confirmó la escena de prueba.')

    def postura(self, x, y, z):
        req = GetPositionIK.Request()
        r = req.ik_request
        r.group_name, r.ik_link_name = 'arm', 'end_effector_link'
        r.pose_stamped.header.frame_id = 'base_link'
        r.pose_stamped.pose.position.x, r.pose_stamped.pose.position.y, r.pose_stamped.pose.position.z = x, y, z
        r.pose_stamped.pose.orientation = orientacion_abajo().orientation
        r.robot_state.is_diff = True
        r.robot_state.joint_state.name = JOINTS
        # Primero resolver geometría y luego comprobar colisiones permite
        # distinguir búsquedas sin IK de posturas encontradas en colisión.
        # Ninguna solución se envía a un controlador.
        r.avoid_collisions = False
        r.timeout.nanosec = int(self.tiempo*1e9)
        contactos = set()
        encontro_ik = False
        semillas = []
        for s in [self.anterior] + self.semillas:
            if s not in semillas:
                semillas.append(s)
            if len(semillas) == self.intentos:
                break
        for semilla in semillas:
            r.robot_state.joint_state.position = semilla
            solucion = self.llamar(self.ik, req)
            if solucion.error_code.val == -31:
                continue
            if solucion.error_code.val != 1:
                raise RuntimeError(f'Error de servicio IK: {solucion.error_code.val}')
            encontro_ik = True
            check = GetStateValidity.Request()
            check.group_name, check.robot_state = 'arm', solucion.solution
            estado = self.llamar(self.validar, check)
            if estado.valid:
                valores = dict(zip(solucion.solution.joint_state.name, solucion.solution.joint_state.position))
                self.anterior = [valores[n] for n in JOINTS]
                return {'estado': 'valida', 'articulaciones': self.anterior.copy()}
            contactos.update(f'{c.contact_body_1} / {c.contact_body_2}' for c in estado.contacts)
        return {'estado': 'colision_o_restriccion' if encontro_ik else 'sin_ik_en_busqueda',
                'contactos': sorted(contactos)}

    def vertical(self, x, y, z, subida, articulaciones):
        req = GetCartesianPath.Request()
        req.group_name, req.link_name, req.header.frame_id = 'arm', 'end_effector_link', 'base_link'
        req.start_state.is_diff = True
        req.start_state.joint_state.name = JOINTS
        req.start_state.joint_state.position = articulaciones
        req.max_step, req.jump_threshold, req.revolute_jump_threshold = .002, 5.0, math.radians(20)
        req.avoid_collisions = True
        req.max_velocity_scaling_factor = req.max_acceleration_scaling_factor = .2
        req.path_constraints.orientation_constraints = [orientacion_abajo()]
        destino = Pose()
        destino.orientation = orientacion_abajo().orientation
        destino.position.x, destino.position.y, destino.position.z = x, y, z+subida
        req.waypoints = [destino]
        arriba = self.llamar(self.cartesiano, req)
        resultado = {'subida': float(arriba.fraction), 'bajada': 0.0, 'completa': False}
        if arriba.error_code.val != 1 or arriba.fraction < .999999 or not arriba.solution.joint_trajectory.points:
            return resultado
        req.start_state.joint_state.name = arriba.solution.joint_trajectory.joint_names
        req.start_state.joint_state.position = arriba.solution.joint_trajectory.points[-1].positions
        destino.position.z = z
        req.waypoints = [destino]
        abajo = self.llamar(self.cartesiano, req)
        resultado['bajada'] = float(abajo.fraction)
        resultado['completa'] = abajo.error_code.val == 1 and abajo.fraction >= .999999
        return resultado


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--centros', nargs='+', type=float, default=[.28, .30, .32, .34])
    parser.add_argument('--lados', nargs='+', type=float, default=[.44, .40])
    parser.add_argument('--altura', type=float, default=.18, help='Altura del montaje sobre el tablero, en metros')
    parser.add_argument('--subida', type=float, default=.05)
    parser.add_argument('--sin-pieza', action='store_true', help='Solo en la sesión aislada: mide el tablero vacío')
    parser.add_argument('--comprobar-vertical', action='store_true', help='Calcula subida y bajada rectas completas sin ejecutarlas')
    parser.add_argument('--intentos', type=int, default=6)
    parser.add_argument('--tiempo-ik', type=float, default=.025)
    parser.add_argument('--dominio', type=int, default=87)
    parser.add_argument('--workspace', default=str(Path.home()/'kinova_revision/ros2_ws'))
    parser.add_argument('--salida', type=Path, default=Path(__file__).resolve().parents[1]/'resultados/alcance_lite.json')
    args = parser.parse_args()
    if not (0 <= args.dominio <= 200 and 2 <= args.intentos <= 32 and 0 < args.tiempo_ik < 1):
        parser.error('Revisa dominio, intentos o tiempo IK.')
    if (not all(math.isfinite(v) for v in args.centros+args.lados+[args.altura, args.subida])
            or any(v <= 0 for v in args.lados) or args.altura <= 0 or args.subida <= 0):
        parser.error('Usa valores finitos y alturas y lados positivos.')
    if args.dominio == int(os.environ.get('ROS_DOMAIN_ID', '73')):
        parser.error('El dominio de evaluación debe ser diferente del de la sesión actual.')
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    log_path = args.salida.with_suffix('.log')
    os.environ['ROS_DOMAIN_ID'], os.environ['ROS_LOCALHOST_ONLY'] = str(args.dominio), '1'
    log = log_path.open('w', encoding='utf-8')
    proceso = subprocess.Popen(['bash', str(Path(__file__).with_name('simular_brazo_wsl.sh')),
        '--workspace', args.workspace, '--sin-gui', '--sin-rviz', '--sin-tablero'],
        stdout=log, stderr=log, start_new_session=True)
    rclpy.init()
    node = rclpy.create_node('evaluar_alcance_aislado')
    informe = {'altura_montaje_sobre_tablero_m': args.altura, 'subida_m': args.subida,
        'orientacion': 'Rx(pi), pinza abajo con giro fijo', 'intentos_ik': args.intentos,
        'tiempo_por_intento_s': args.tiempo_ik,
        'pieza_virtual_presente': not args.sin_pieza,
        'comprobacion_vertical': args.comprobar_vertical,
        'limitaciones': 'Solo posturas estáticas del montaje, sin rutas, sin pieza agarrada, sin física. No encontrar IK no demuestra imposibilidad.',
        'comparaciones': []}
    try:
        evaluador = Evaluador(node, args.intentos, args.tiempo_ik)
        for cliente in (evaluador.ik, evaluador.validar, evaluador.aplicar, evaluador.cartesiano):
            limite = time.monotonic()+60
            while not cliente.wait_for_service(timeout_sec=1):
                if proceso.poll() is not None or time.monotonic()>limite:
                    raise RuntimeError(f'No inició la sesión aislada. Consulta {log_path}')
        if proceso.poll() is not None:
            raise RuntimeError(f'El lanzador terminó. Consulta {log_path}')
        for lado in args.lados:
            for centro in args.centros:
                config = cargar_config(CONFIG)
                config['lado_tablero_m'], config['centro_x_m'] = lado, centro
                evaluador.escena(config, args.sin_pieza)
                evaluador.anterior = [0.0]*6
                comparacion = {'lado_m': lado, 'centro_x_m': centro, 'casillas': []}
                print(f'Evaluando tablero {lado:.2f} m, centro {centro:.3f} m...', flush=True)
                for fila in range(1, 9):
                    for letra in 'abcdefgh':
                        casilla = f'{letra}{fila}'
                        x, y = centro_casilla(config, casilla)
                        z = config['superficie_z_m']+args.altura
                        agarre = evaluador.postura(x, y, z)
                        arriba = evaluador.postura(x, y, z+args.subida)
                        dato = {'casilla': casilla, 'x_ros': x,
                            'y_ros': y, 'z_ros': z, 'agarre': agarre, 'aproximacion': arriba}
                        if args.comprobar_vertical and agarre['estado']=='valida':
                            dato['vertical'] = evaluador.vertical(x, y, z, args.subida, agarre['articulaciones'])
                        comparacion['casillas'].append(dato)
                    print(f'  fila {fila}/8', flush=True)
                    if proceso.poll() is not None:
                        raise RuntimeError('La simulación de evaluación terminó inesperadamente.')
                c = comparacion['casillas']
                comparacion['agarre_valido'] = sum(v['agarre']['estado']=='valida' for v in c)
                comparacion['ambas_posturas_validas'] = sum(v['agarre']['estado']==v['aproximacion']['estado']=='valida' for v in c)
                if args.comprobar_vertical:
                    comparacion['subida_bajada_recta'] = sum(v.get('vertical', {}).get('completa', False) for v in c)
                informe['comparaciones'].append(comparacion)
                args.salida.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding='utf-8')
                print(f"RESUMEN lado={lado:.2f} centro={centro:.3f}: agarre {comparacion['agarre_valido']}/64; ambas {comparacion['ambas_posturas_validas']}/64; vertical {comparacion.get('subida_bajada_recta', 'no comprobada')}", flush=True)
        print(f'Resultados guardados: {args.salida}', flush=True)
    finally:
        node.destroy_node()
        rclpy.shutdown()
        if proceso.poll() is None:
            os.killpg(proceso.pid, signal.SIGINT)
            try:
                proceso.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(proceso.pid, signal.SIGTERM)
                proceso.wait(timeout=8)
        log.close()


if __name__ == '__main__':
    main()
