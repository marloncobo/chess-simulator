import unittest
from chess_simulator.seguimiento import Observacion, SeguimientoPorCasilla


def obs(piezas, secuencia):
    return Observacion.desde_dict({'secuencia':secuencia, 'completa':True,
        'piezas':[{'casilla':c,'pieza':p} for c,p in piezas.items()]})


class PruebasMovimientoVivo(unittest.TestCase):
    def setUp(self):
        self.motor = SeguimientoPorCasilla()
        self.t = 0.
        self.seq = 0

    def mostrar(self, piezas, segundos=2.):
        for _ in range(round(segundos/.25)):
            self.motor.recibir(obs(piezas,self.seq), self.t)
            self.t += .25
            self.seq += 1

    def test_levantar_pieza_varios_segundos_registra_traslado(self):
        self.mostrar({'a8':'T'})
        self.mostrar({}, 5.)
        self.mostrar({'a6':'T'})
        self.assertEqual(len(self.motor.historial), 1)
        self.assertEqual(self.motor.historial[0].destino, 'a6')

    def test_movimiento_de_mano_entre_salida_y_llegada(self):
        self.mostrar({'a8':'T'})
        self.mostrar({})
        self.motor.invalidar('Mano', conservar_movimiento=True)
        self.mostrar({'a6':'T'})
        self.assertEqual(len(self.motor.historial), 1)

    def test_todos_los_tipos_y_colores_con_levantamiento(self):
        for pieza in 'TCARDP tcardp'.replace(' ', ''):
            with self.subTest(pieza=pieza):
                self.setUp()
                self.mostrar({'c6':pieza})
                self.mostrar({}, 4.)
                self.mostrar({'d5':pieza})
                self.assertEqual([(m.origen,m.destino,m.pieza) for m in self.motor.historial],
                                 [('c6','d5',pieza)])

    def test_mano_visible_varios_segundos_no_parece_desconexion(self):
        self.mostrar({'a8':'T'})
        self.mostrar({})
        for _ in range(20):
            self.motor.invalidar('Mano', conservar_movimiento=True, ahora=self.t)
            self.t += .25
        self.mostrar({'a6':'T'})
        self.assertEqual(len(self.motor.historial), 1)

    def test_desconexion_real_no_enlaza_movimientos(self):
        self.mostrar({'a8':'T'})
        self.mostrar({})
        self.t += 5.
        self.mostrar({'a6':'T'})
        self.assertEqual(self.motor.historial, [])

    def test_recalibracion_no_enlaza_posiciones(self):
        self.mostrar({'a8':'T'})
        self.mostrar({})
        self.motor.invalidar('Recalibrando')
        self.mostrar({'a6':'T'})
        self.assertEqual(self.motor.historial, [])

    def test_retirada_antigua_no_se_asocia_a_pieza_nueva(self):
        self.mostrar({'a8':'T'})
        self.mostrar({}, 15.)
        self.mostrar({'a6':'T'})
        self.assertEqual(self.motor.historial, [])

    def test_captura_con_llegada_confirmada_antes_que_vaciado(self):
        self.mostrar({'a8':'T','a6':'p'})
        self.mostrar({'a6':'T'}, 3.)
        self.assertEqual(len(self.motor.historial), 1)
        self.assertEqual(self.motor.historial[0].tipo, 'captura')

    def test_dos_movimientos_seguidos_no_se_duplican(self):
        self.mostrar({'a8':'T'})
        self.mostrar({'a6':'T'},3.)
        self.mostrar({'c6':'T'},3.)
        self.assertEqual([(m.origen,m.destino) for m in self.motor.historial], [('a8','a6'),('a6','c6')])

    def test_captura_al_paso_conserva_ultimo_avance(self):
        self.mostrar({'e5':'P','d7':'p'})
        self.mostrar({'e5':'P','d5':'p'},3.)
        self.mostrar({'d6':'P'},3.)
        self.assertEqual([m.tipo for m in self.motor.historial], ['movimiento','captura al paso'])

if __name__ == '__main__':
    unittest.main()
