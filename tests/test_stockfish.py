
import chess
import chess.engine

# Sustituir por la ruta real de Stockfish
STOCKFISH_PATH = r"C:\Users\Usuario\Downloads\stockfish\stockfish-windows-x86-64-universal.exe"

board = chess.Board()

with chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH) as engine:
    engine.configure({
        "Threads": 2,
        "Hash": 64
    })

    print("Motor:", engine.id.get("name"))
    print("FEN inicial:", board.fen())

    # Simulamos un movimiento detectado por YOLO
    human_move = chess.Move.from_uci("e2e4")

    if human_move not in board.legal_moves:
        raise ValueError("Movimiento humano ilegal")

    board.push(human_move)

    print("\nFEN enviado al motor:", board.fen())

    # Solicitar la respuesta de Stockfish
    result = engine.play(
        board,
        chess.engine.Limit(time=0.5)
    )

    move = result.move

    if move is None:
        print("No hay movimiento disponible.")
    else:
        print("\n--- RESPUESTA DEL MOTOR ---")
        print("Movimiento UCI:", move.uci())
        print("Origen:", chess.square_name(move.from_square))
        print("Destino:", chess.square_name(move.to_square))
        print("Pieza:", board.piece_at(move.from_square))
        print("Movimiento legal:", move in board.legal_moves)

        board.push(move)

        print("\nFEN después del movimiento:", board.fen())
        print("\nTablero actualizado:")
        print(board)
