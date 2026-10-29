import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

try:
    from moveit_msgs.srv import GetPositionIK, GetStateValidity, GetCartesianPath
except ImportError:
    ROS = False
else:
    ROS = True
    carpeta = Path(__file__).resolve().parents[1]/'brazo_kinova'
    sys.path.insert(0, str(carpeta))
    try:
        spec = importlib.util.spec_from_file_location('evaluar_alcance', carpeta/'evaluar_alcance.py')
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
    finally:
        sys.path.pop(0)


@unittest.skipUnless(ROS, 'Requiere ROS Humble')
class EvaluacionTest(unittest.TestCase):
    def setUp(self):
        self.e = modulo.Evaluador(Mock(), 4, .025)

    def test_no_ik_reintenta_semillas_sin_repetir_y_no_ejecuta(self):
        fallo = GetPositionIK.Response()
        fallo.error_code.val = -31
        semillas = []
        def llamar(cliente, req):
            semillas.append(tuple(req.ik_request.robot_state.joint_state.position))
            return fallo
        self.e.llamar = llamar
        resultado = self.e.postura(.09, 0., .18)
        self.assertEqual(resultado['estado'], 'sin_ik_en_busqueda')
        self.assertEqual(len(semillas), 4)
        self.assertEqual(len(set(semillas)), 4)

    def test_no_acepta_postura_sin_verificar_colision(self):
        solucion = GetPositionIK.Response()
        solucion.error_code.val = 1
        solucion.solution.joint_state.name = modulo.JOINTS
        solucion.solution.joint_state.position = [0.0]*6
        estado = GetStateValidity.Response()
        estado.valid = False
        self.e.llamar = Mock(side_effect=[solucion, estado]*4)
        self.assertEqual(self.e.postura(.27, 0., .18)['estado'], 'colision_o_restriccion')

    def test_tablero_vacio_conserva_colision_del_tablero(self):
        self.e.llamar = Mock(return_value=Mock(success=True))
        self.e.escena(modulo.cargar_config(modulo.CONFIG), sin_pieza=True)
        req = self.e.llamar.call_args.args[1]
        self.assertEqual(len(req.scene.world.collision_objects), 1)
        self.assertEqual(req.scene.world.collision_objects[0].id, 'semillero_tablero_virtual')

    def test_vertical_parcial_no_cuenta_como_subida_completa(self):
        respuesta = GetCartesianPath.Response()
        respuesta.error_code.val = 1
        respuesta.fraction = .75
        self.e.llamar = Mock(return_value=respuesta)
        resultado = self.e.vertical(.49, -.175, .18, .03, [0.0]*6)
        self.assertFalse(resultado['completa'])
        self.assertEqual(self.e.llamar.call_count, 1)
        req = self.e.llamar.call_args.args[1]
        self.assertTrue(req.avoid_collisions)
        self.assertEqual(req.waypoints[0].position.x, .49)
        self.assertEqual(req.waypoints[0].position.y, -.175)


if __name__ == '__main__':
    unittest.main()
