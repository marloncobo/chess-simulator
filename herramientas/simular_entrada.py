"""Ejemplo de productor externo: publica una secuencia completa y sale."""
import argparse
import time

from chess_simulator.entrada import crear_observacion, publicar


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ruta", help="Archivo JSON de salida")
    args = parser.parse_args()
    tablero = [[""] * 8 for _ in range(8)]
    tablero[7][0], tablero[0][7] = "T", "t"
    secuencia = time.time_ns()
    for paso in range(60):
        if paso == 20:
            tablero[5][0], tablero[7][0] = "T", ""
        if paso == 40:
            tablero[2][7], tablero[0][7] = "t", ""
        publicar(args.ruta, crear_observacion(tablero, secuencia + paso))
        time.sleep(0.1)


if __name__ == "__main__":
    main()
