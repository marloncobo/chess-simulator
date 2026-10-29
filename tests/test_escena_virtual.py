import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import yaml

try:
    import rclpy
    from moveit_msgs.msg import CollisionObject
except ImportError:
    ROS = False
else:
    ROS = True
    spec = importlib.util.spec_from_file_location(
        'escena_virtual', Path(__file__).resolve().parents[1] / 'brazo_kinova/escena_virtual.py')
    escena = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(escena)


@unittest.skipUnless(ROS, 'Requiere ROS Humble')
class EscenaTest(unittest.TestCase):
    def setUp(self):
        self.config = escena.cargar_config(escena.CONFIG)
        # Geometría de referencia independiente de la ubicación elegida por el usuario.
        self.config['centro_x_m'] = .40
        self.config['centro_y_m'] = 0.0

    def test_medidas_y_contacto_tablero_pieza(self):
        tablero, pieza = escena.objetos(self.config)
        self.assertEqual(tablero.id, escena.TABLERO)
        self.assertEqual(pieza.id, escena.PIEZA)
        self.assertEqual(list(tablero.primitives[0].dimensions), [.44, .44, .02])
        self.assertEqual(list(pieza.primitives[0].dimensions), [.06, .015])
        self.assertAlmostEqual(tablero.primitive_poses[0].position.z + .01, 0)
        self.assertAlmostEqual(pieza.primitive_poses[0].position.z - .03, 0)
        self.assertEqual(pieza.operation, CollisionObject.ADD)

    def test_casillas_en_su_sistema_de_referencia(self):
        self.assertAlmostEqual(escena.centro_casilla(self.config, 'a1')[0], .2075)
        self.assertAlmostEqual(escena.centro_casilla(self.config, 'h8')[1], .1925)
        x, y = escena.centro_casilla(self.config, 'd4')
        self.assertAlmostEqual(x, .3725)
        self.assertAlmostEqual(y, -.0275)

    def test_marcas_coinciden_con_objeto_colision(self):
        marcas = escena.marcas(self.config).markers
        self.assertEqual(len(marcas), 69)
        self.assertEqual(len({m.id for m in marcas}), len(marcas))
        self.assertEqual(marcas[64].pose, escena.objetos(self.config)[1].primitive_poses[0])
        self.assertTrue(all(m.header.frame_id == 'base_link' for m in marcas))

    def test_rviz_escucha_el_tema_de_la_escena(self):
        archivo = escena.CONFIG.with_name('brazo.rviz')
        config = yaml.safe_load(archivo.read_text(encoding='utf-8'))
        displays = config['Visualization Manager']['Displays']
        marcador = next(d for d in displays if d['Class'] == 'rviz_default_plugins/MarkerArray')
        self.assertEqual(marcador['Topic']['Value'], '/semillero/escena_virtual')
        self.assertEqual(marcador['Topic']['Durability Policy'], 'Transient Local')

    def test_configuracion_invalida(self):
        for cambio in ({'casilla_pieza': 'j9'}, {'lado_tablero_m': -1},
                       {'altura_pieza_m': float('nan')}, {'diametro_pieza_m': .1}):
            with self.subTest(cambio=cambio), tempfile.TemporaryDirectory() as carpeta:
                archivo = Path(carpeta)/'escena.json'
                archivo.write_text(json.dumps({**self.config, **cambio}), encoding='utf-8')
                with self.assertRaises(ValueError):
                    escena.cargar_config(archivo)


if __name__ == '__main__':
    unittest.main()
