"""Ejecutar con Python de ROS Humble; se omiten sin las dependencias ROS."""
import importlib.util
import math
import queue
from pathlib import Path
import unittest
import time
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import Mock

try:
    import rclpy
    from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
    import tf2_ros
    from moveit_msgs.action import ExecuteTrajectory
    from moveit_msgs.srv import GetPositionIK, GetCartesianPath
    from moveit_msgs.srv import GetStateValidity
    from moveit_msgs.msg import ContactInformation
except ImportError:
    ROS = False
else:
    ROS = True
    spec = importlib.util.spec_from_file_location(
        "mover_xyz", Path(__file__).resolve().parents[1] / "brazo_kinova/mover_xyz.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)


@unittest.skipUnless(ROS, "Requiere entorno ROS Humble")
class TrayectoriaTest(unittest.TestCase):
    def test_semillas_no_superan_limites_del_lite(self):
        inicial = {n: 2.5 for n in modulo.JOINTS}
        semillas = modulo.semillas_ik(inicial)
        self.assertGreater(len(semillas), 1)
        self.assertLessEqual(len(semillas), 6)
        for s in semillas:
            self.assertTrue(all(abs(s[n]) <= limite for n, limite in zip(modulo.JOINTS, modulo.LIMITES_LITE)))
        self.assertEqual(inicial, {n: 2.5 for n in modulo.JOINTS})

    def test_puntos_intermedios_conservan_destino_y_no_desvian_vertical(self):
        destino = modulo.Pose()
        destino.position.x, destino.position.y, destino.position.z = .09, .20, .18
        destino.orientation = modulo.orientacion_abajo().orientation
        rutas = modulo.rutas_intermedias((.09, -.20, .18), destino)
        self.assertEqual(len(rutas), 3)
        self.assertTrue(all(r[-1] == destino for r in rutas))
        self.assertTrue(all(p.orientation == destino.orientation for r in rutas for p in r))
        self.assertEqual(modulo.rutas_intermedias((.09, .20, .30), destino), [])

    def test_gui_y_altura_se_convierte_a_z_ros(self):
        app = modulo.App.__new__(modulo.App)
        app.en_movimiento = False
        app.casillas = {eje: Mock() for eje in 'xyz'}
        for eje, valor in zip('xyz', ('0.25', '0.30', '-0.10')):
            app.casillas[eje].get.return_value = valor
        app.brazo = Mock()
        app.brazo.listo.return_value = True
        app.boton, app.preparar, app.estado, app.root = Mock(), Mock(), Mock(), Mock()
        app.resultados = queue.Queue()
        app.permitir_curva = Mock()
        app.permitir_curva.get.return_value = False
        app.mover(preparar=True)
        llamada = app.brazo.mover.call_args
        self.assertEqual(llamada.args[:3], (.25, -.10, .30))
        self.assertTrue(llamada.kwargs['preparar'])

    def trayectoria(self, valores):
        t = JointTrajectory()
        t.joint_names = modulo.JOINTS
        for valor in valores:
            p = JointTrajectoryPoint()
            p.positions = [float(valor)] + [0.0] * 5
            t.points.append(p)
        return t

    def test_detecta_vuelta_completa_sin_envolver_angulos(self):
        inicial = dict.fromkeys(modulo.JOINTS, 0.0)
        recorrido = modulo.recorrido_articular(self.trayectoria([0, math.pi, 2*math.pi]), inicial)
        self.assertAlmostEqual(recorrido, 2*math.pi)
        self.assertGreater(recorrido, modulo.MAX_RECORRIDO_JOINT)

    def test_detecta_ida_y_vuelta_aunque_destino_sea_cercano(self):
        inicial = dict.fromkeys(modulo.JOINTS, 0.0)
        self.assertAlmostEqual(modulo.recorrido_articular(self.trayectoria([0, 2, 0]), inicial), 4)

    def test_acepta_desplazamiento_pequeno(self):
        inicial = dict.fromkeys(modulo.JOINTS, 0.0)
        self.assertLess(modulo.recorrido_articular(self.trayectoria([0, .05, .1]), inicial), .2)

    def test_rechaza_nan_y_trayectoria_vacia(self):
        for valores in ([], [float('nan')]):
            with self.assertRaises(ValueError):
                modulo.recorrido_articular(self.trayectoria(valores), dict.fromkeys(modulo.JOINTS, 0.0))

    def test_rotacion_invierte_z_del_efector(self):
        q = modulo.orientacion_abajo().orientation
        z_rotado = (2*(q.x*q.z+q.w*q.y), 2*(q.y*q.z-q.w*q.x), 1-2*(q.x*q.x+q.y*q.y))
        self.assertEqual(z_rotado, (0.0, 0.0, -1.0))

    def test_grupo_y_lanzadores_corresponden_a_gen3_lite(self):
        self.assertEqual(modulo.GRUPO, 'arm')
        self.assertEqual(modulo.EEF, 'end_effector_link')
        carpeta = Path(modulo.__file__).parent
        lanzador = (carpeta/'simular_brazo_wsl.sh').read_text(encoding='utf-8')
        self.assertIn('CONFIG=kinova_gen3_lite_moveit_config', lanzador)
        self.assertIn('kortex_bringup gen3_lite.launch.py', lanzador)
        self.assertNotIn('robotiq_2f_85_moveit_config', lanzador)


@unittest.skipUnless(ROS, "Requiere entorno ROS Humble")
class SolicitudTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rclpy.init()

    @classmethod
    def tearDownClass(cls):
        rclpy.shutdown()

    def listo(self, resultado):
        futuro = Future()
        futuro.set_result(resultado)
        return futuro

    def setUp(self):
        self.node = modulo.Brazo()
        self.node.cliente.destroy()
        self.node.ejecutor.destroy()
        self.node.destroy_client(self.node.ik)
        self.node.destroy_client(self.node.cartesiano)
        self.node.destroy_client(self.node.validez)
        self.node.posiciones = dict.fromkeys(modulo.JOINTS, 0.0)
        self.node.ultima_lectura = time.monotonic()
        self.node.tf = Mock()
        self.node.tf.lookup_transform.return_value = SimpleNamespace(
            transform=SimpleNamespace(rotation=modulo.orientacion_abajo().orientation,
                                      translation=SimpleNamespace(x=.25, y=0., z=.35)))
        self.node.ik = Mock()
        self.node.cartesiano = Mock()
        self.node.validez = Mock()
        self.node.cliente = Mock()
        self.node.ejecutor = Mock()
        self.node.cliente.send_goal_async.return_value = Future()
        ik = GetPositionIK.Response()
        ik.error_code.val = 1
        ik.solution.joint_state.name = modulo.JOINTS
        ik.solution.joint_state.position = [0.0]*6
        self.node.ik.call_async.return_value = self.listo(ik)
        parcial = GetCartesianPath.Response()
        parcial.error_code.val = 1
        parcial.fraction = .25
        self.node.cartesiano.call_async.return_value = self.listo(parcial)
        self.resultados = []

    def tearDown(self):
        self.node.listener.unregister()
        self.node.destroy_node()

    def test_parcial_no_ejecuta_si_curva_desactivada(self):
        self.node.mover(.35, 0., .35, self.resultados.append, permitir_curva=False)
        self.node.ejecutor.send_goal_async.assert_not_called()
        self.node.cliente.send_goal_async.assert_not_called()
        self.assertIn('25%', self.resultados[0])

    def test_alternativa_conserva_orientacion_y_solo_planifica(self):
        self.node.mover(.35, 0., .35, self.resultados.append)
        goal = self.node.cliente.send_goal_async.call_args.args[0]
        self.assertTrue(goal.planning_options.plan_only)
        self.assertEqual(len(goal.request.goal_constraints[0].joint_constraints), 6)
        self.assertEqual(goal.request.path_constraints.orientation_constraints[0].link_name, modulo.EEF)
        self.node.ejecutor.send_goal_async.assert_not_called()

    def test_solo_ejecuta_ruta_intermedia_completa(self):
        parcial = self.node.cartesiano.call_async.return_value
        completo = GetCartesianPath.Response()
        completo.error_code.val, completo.fraction = 1, 1.0
        completo.solution.joint_trajectory.joint_names = modulo.JOINTS
        p = JointTrajectoryPoint()
        p.positions = [.1]*6
        completo.solution.joint_trajectory.points = [p]
        self.node.cartesiano.call_async.side_effect = [parcial, parcial, self.listo(completo)]
        self.node.ejecutor.send_goal_async.return_value = Future()
        self.node.mover(.35, 0., .35, self.resultados.append)
        self.assertEqual(self.node.cartesiano.call_async.call_count, 3)
        peticiones = [c.args[0] for c in self.node.cartesiano.call_async.call_args_list]
        self.assertEqual(len(peticiones[0].waypoints), 1)
        self.assertGreater(len(peticiones[-1].waypoints), 1)
        self.assertTrue(all(p.avoid_collisions for p in peticiones))
        self.node.ejecutor.send_goal_async.assert_called_once()
        self.assertEqual(self.node.ejecutor.send_goal_async.call_args.args[0].trajectory, completo.solution)
        self.node.cliente.send_goal_async.assert_not_called()

    def test_sin_ik_no_intenta_planificar_ni_ejecutar(self):
        ik = GetPositionIK.Response()
        ik.error_code.val = -31
        self.node.ik.call_async.return_value = self.listo(ik)
        self.node.mover(.42, .11, .76, self.resultados.append, preparar=True)
        self.assertIn('varias semillas', self.resultados[0])
        self.node.cartesiano.call_async.assert_not_called()
        self.node.cliente.send_goal_async.assert_not_called()

    def test_reintenta_ik_con_semillas_distintas(self):
        correcto = self.node.ik.call_async.return_value
        fallo = GetPositionIK.Response()
        fallo.error_code.val = -31
        self.node.ik.call_async.side_effect = [self.listo(fallo)] + [correcto]*8
        self.node.mover(.35, 0., .35, self.resultados.append, permitir_curva=False)
        self.assertGreater(self.node.ik.call_async.call_count, 1)
        llamadas = self.node.ik.call_async.call_args_list
        self.assertNotEqual(list(llamadas[0].args[0].ik_request.robot_state.joint_state.position),
                            list(llamadas[1].args[0].ik_request.robot_state.joint_state.position))
        self.assertTrue(all(c.args[0].ik_request.avoid_collisions for c in llamadas))

    def test_orden_vertical_no_permite_rodeo(self):
        self.node.mover(.25, 0., .25, self.resultados.append, permitir_curva=True)
        self.assertEqual(self.node.cartesiano.call_async.call_count, 1)
        self.node.cliente.send_goal_async.assert_not_called()
        self.assertIn('debe ser recta', self.resultados[0])

    def test_diagnostico_colision_no_ejecuta_solucion_sin_filtro(self):
        correcto = self.node.ik.call_async.return_value
        fallo = GetPositionIK.Response()
        fallo.error_code.val = -31
        cantidad = len(modulo.semillas_ik(self.node.posiciones))
        self.node.ik.call_async.side_effect = [self.listo(fallo)]*cantidad + [correcto]
        estado = GetStateValidity.Response()
        contacto = ContactInformation()
        contacto.contact_body_1 = 'semillero_pieza_virtual'
        contacto.contact_body_2 = 'left_finger_dist_link'
        estado.contacts = [contacto]
        self.node.validez.call_async.return_value = self.listo(estado)
        self.node.mover(.27, 0., .18, self.resultados.append)
        self.assertIn('semillero_pieza_virtual', self.resultados[0])
        self.assertFalse(self.node.ik.call_async.call_args.args[0].ik_request.avoid_collisions)
        self.node.ejecutor.send_goal_async.assert_not_called()
        self.node.cartesiano.call_async.assert_not_called()
        self.node.ejecutor.send_goal_async.assert_not_called()

    def test_cancelar_ik_pendiente_impide_ejecucion_tardia(self):
        pendiente = Future()
        self.node.ik.call_async.return_value = pendiente
        self.node.mover(.35, 0., .35, self.resultados.append)
        self.node.cancelar()
        ik = GetPositionIK.Response()
        ik.error_code.val = 1
        pendiente.set_result(ik)
        self.assertIn('cancelada', self.resultados[0])
        self.node.cartesiano.call_async.assert_not_called()
        self.node.cliente.send_goal_async.assert_not_called()


if __name__ == '__main__':
    unittest.main()
