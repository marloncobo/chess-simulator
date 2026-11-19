import asyncio
import os
import chess
import chess.engine

def main():
    path = r"C:\Users\Usuario\Downloads\stockfish\stockfish-windows-x86-64-universal.exe"
    if not path:
        raise RuntimeError("Define STOCKFISH_PATH con la ruta del ejecutable")

    board = chess.Board()
    game_id = object()  # Conservar durante esta partida; cambiar para otra.
    engine = chess.engine.SimpleEngine.popen_uci([path], timeout=15.0)
    try:
        print("Motor:", engine.id)
        for name in ("Threads", "Hash", "Skill Level", "UCI_Elo"):
            if name in engine.options:
                print(name, engine.options[name])
        engine.configure({"Threads": 2, "Hash": 64})
        engine.ping()

        while not board.is_game_over(claim_draw=True):
            print("\n", board, sep="")
            if board.turn == chess.WHITE:
                text = input("Blancas UCI (o salir): ").strip()
                if text.lower() in {"salir", "quit"}:
                    return
                try:
                    move = board.parse_uci(text)
                    if not move or move not in board.legal_moves:
                        raise ValueError("No se permiten movimientos nulos")
                except ValueError as exc:
                    print("Jugada rechazada:", exc)
                    continue
            else:
                if not board.is_valid():
                    raise RuntimeError("Posición inválida; búsqueda cancelada")
                result = engine.play(
                    board.copy(stack=True),
                    chess.engine.Limit(time=1.0),  # Segundos en esta API.
                    game=game_id,
                    ponder=False,
                )
                move = result.move
                if move is None or not move or move not in board.legal_moves:
                    raise RuntimeError("El motor no devolvió una jugada legal")
                print("Stockfish:", board.uci(move), "SAN:", board.san(move))
            board.push(move)

        print("\n", board, sep="")
        outcome = board.outcome(claim_draw=True)
        print("Resultado:", outcome.result(), "Motivo:", outcome.termination.name)
    finally:
        try:
            engine.quit()
        except (chess.engine.EngineError, asyncio.TimeoutError):
            engine.close()

if __name__ == "__main__":
    try:
        main()
    except (EOFError, KeyboardInterrupt):
        print("\nSesión cerrada")
    except (OSError, RuntimeError, asyncio.TimeoutError) as exc:
        print("No se pudo continuar:", exc)
        raise SystemExit(1)
