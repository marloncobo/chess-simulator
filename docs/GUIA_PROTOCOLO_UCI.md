# Guía del protocolo UCI para chess-simulator

**Idioma:** español. **Versión objetivo del motor:** Stockfish 19.  
**Referencias verificadas:** 5 de noviembre de 2026.  
**Entorno del proyecto:** Python, python-chess, Pygame, YOLO y Kinova Gen3 Lite.

Esta guía explica tanto el formato de las jugadas como la conversación entre la aplicación y el motor. Los ejemplos de integración con visión y robótica son propuestas para `chess-simulator`: no presuponen que esos módulos ya estén implementados. Los programas de terminal no accionan el robot.

## Índice

1. [Qué es UCI y qué componente lo utiliza](#1-qué-es-uci-y-qué-componente-lo-utiliza)
2. [Notación de movimientos](#2-notación-de-movimientos)
3. [UCI, SAN, FEN y PGN](#3-uci-san-fen-y-pgn)
4. [Comandos de la aplicación al motor](#4-comandos-de-la-aplicación-al-motor)
5. [Respuestas del motor](#5-respuestas-del-motor)
6. [Ciclo de una partida](#6-ciclo-de-una-partida)
7. [Prueba manual en la terminal](#7-prueba-manual-en-la-terminal)
8. [Configuración del entorno y del motor](#8-configuración-del-entorno-y-del-motor)
9. [Validación antes de enviar posiciones](#9-validación-antes-de-enviar-posiciones)
10. [Partida interactiva con python-chess](#10-partida-interactiva-con-python-chess)
11. [Comunicación directa con subprocess](#11-comunicación-directa-con-subprocess)
12. [Integración con Pygame, YOLO y Kinova](#12-integración-con-pygame-yolo-y-kinova)
13. [Casos límite, errores y recuperación](#13-casos-límite-errores-y-recuperación)
14. [Documentación verificada](#14-documentación-verificada)

## 1. Qué es UCI y qué componente lo utiliza

Universal Chess Interface es un protocolo textual entre una interfaz y un motor de ajedrez. La interfaz puede ser gráfica o un programa de terminal. Su especificación fue desarrollada por Rudolf Huber y Stefan Meyer-Kahlen. Véase la [página de los autores en Shredder](https://www.shredderchess.com/chess-features/uci-universal-chess-interface.html).

En este proyecto, la aplicación Python desempeña el papel de «GUI» del protocolo, aunque no haya una ventana abierta:

```text
Cámara → YOLO → reconciliación con jugadas legales ─┐
                                                  ↓
Entrada humana / Pygame ←→ controlador + chess.Board
                                      │         │
                                      │ UCI     │ plan físico
                                      ↓         ↓
                                 Stockfish    adaptador Kinova
                                                   │
                                           confirmación física
```

Se recomienda un único controlador propietario del estado confirmado. Stockfish propone jugadas; python-chess representa las reglas; Pygame muestra e introduce acciones; YOLO produce observaciones; el adaptador Kinova transforma acciones ajedrecísticas en movimientos físicos.

UCI no transmite imágenes, coordenadas cartesianas ni instrucciones de pinza. El proceso Stockfish recibe líneas por `stdin` y responde por `stdout`, terminadas en salto de línea. La aplicación debe continuar leyendo mientras el motor calcula. [Especificación UCI, edición de abril de 2006](https://backscattering.de/chess/uci/).

## 2. Notación de movimientos

### 2.1 Casillas y orientación

Las columnas son `a` a `h`; las filas, `1` a `8`. Cada casilla tiene dos caracteres: `a1`, `e4`, `h8`. Las coordenadas son absolutas: no cambian al rotar la cámara o mostrar el tablero desde el lado negro. Desde la perspectiva blanca, `a1` está abajo a la izquierda y es oscura.

```text
8  a8 b8 c8 d8 e8 f8 g8 h8
7  a7 b7 c7 d7 e7 f7 g7 h7
6  a6 b6 c6 d6 e6 f6 g6 h6
5  a5 b5 c5 d5 e5 f5 g5 h5
4  a4 b4 c4 d4 e4 f4 g4 h4
3  a3 b3 c3 d3 e3 f3 g3 h3
2  a2 b2 c2 d2 e2 f2 g2 h2
1  a1 b1 c1 d1 e1 f1 g1 h1
   a  b  c  d  e  f  g  h
```

### 2.2 Origen, destino y promoción

La forma habitual tiene cuatro caracteres: `<origen><destino>`. Una promoción añade un quinto: `q` dama, `r` torre, `b` alfil o `n` caballo. Se usan minúsculas para ambos colores. No se añade la inicial de la pieza, `x`, guion, `=`, `+` ni `#`. [Formato de movimientos en python-chess](https://python-chess.readthedocs.io/en/latest/core.html#moves).

| Acción | UCI | Lectura |
|---|---|---|
| Avance | `e2e4` | De e2 a e4 |
| Caballo | `g1f3` | De g1 a f3 |
| Captura | `e4d5` | De e4 a d5; la posición determina la captura |
| Promoción a dama | `a7a8q` | Peón de a7 a a8 y sustitución por dama |
| Subpromoción | `a7a8n` | Promoción a caballo |
| Captura y promoción | `b7a8r` | Captura en a8 y promoción a torre |
| Promoción negra | `a2a1q` | Peón negro que corona en a1 |

Los ejemplos de esta tabla son formatos: su legalidad depende de la posición. `e2e4` no es legal si juegan negras, e2 está vacía o e3 está ocupada.

El error del caso original se corrige así:

```text
Incorrecto: position startpos moves e2e4 e7e5 kg1kf3
Correcto:   position startpos moves e2e4 e7e5 g1f3
```

No hay prefijos de pieza en UCI. En las convenciones inglesas, `K` significa rey y `N` caballo; ninguna de esas letras precede una jugada UCI ordinaria.

### 2.3 Enroque en ajedrez estándar

| Enroque | UCI | Movimiento complementario de torre |
|---|---|---|
| Blanco corto | `e1g1` | h1 → f1 |
| Blanco largo | `e1c1` | a1 → d1 |
| Negro corto | `e8g8` | h8 → f8 |
| Negro largo | `e8c8` | a8 → d8 |

Se envía **una** jugada; no se agrega una segunda jugada de torre a `moves`. Deben existir los derechos correspondientes, estar libres las casillas necesarias y cumplirse las restricciones de jaque. Para el robot, una jugada se descompone en dos traslados físicos.

En **Chess960**, con `UCI_Chess960=true`, el enroque se codifica como rey hacia la casilla de origen de su torre: por ejemplo `e1h1` si esa torre comienza en h1. No reutilizar la tabla estándar para una configuración Chess960. Usar `board.uci(move)` y `board.parse_uci(texto)` con un tablero configurado para esa variante. [Implementación del formato en Stockfish 19](https://github.com/official-stockfish/Stockfish/blob/sf_19/src/uci.cpp).

### 2.4 Captura al paso

También se escribe origen-destino. Ejemplo completo:

```text
position startpos moves e2e4 a7a6 e4e5 d7d5 e5d6
```

En `e5d6`, el peón blanco termina en d6 y se retira el peón negro de **d5**, aunque d6 estaba vacía. Solo está disponible inmediatamente después del avance doble pertinente y si no deja al propio rey en jaque. La detección visual y la planificación física deben considerar tres casillas afectadas.

### 2.5 Movimiento nulo y ausencia de jugada

`0000` representa el movimiento nulo en UCI; no es una jugada legal de una partida ordinaria. Algunas salidas usan `bestmove (none)` cuando no hay movimientos disponibles. El adaptador debe aceptar ambos como ausencia de movimiento ejecutable, comprobar el estado final y nunca enviar esas cadenas al robot. Tampoco debe admitir `0000` como entrada humana. [Representación y salida en Stockfish 19](https://github.com/official-stockfish/Stockfish/blob/sf_19/src/uci.cpp).

## 3. UCI, SAN, FEN y PGN

| Formato | Qué expresa | Ejemplo | Uso en el proyecto |
|---|---|---|---|
| Jugada UCI | Origen y destino, promoción opcional | `g1f3` | Intercambio de jugadas con Stockfish |
| SAN | Jugada legible con contexto | `Nf3`, `exd5`, `O-O`, `e8=Q+` | Etiquetas en Pygame y registro humano |
| FEN | Una posición con metadatos | Véase abajo | Carga, diagnóstico y puntos de recuperación |
| PGN | Partida con cabeceras y secuencia SAN | `1. e4 e5 2. Nf3 *` | Guardar y revisar partidas |

SAN necesita la posición para resolver ambigüedades, capturas y jaques. No enviar `Nf3` dentro de `position ... moves`. Si la interfaz acepta SAN, convertirla primero:

```python
import chess

board = chess.Board()
board.push_uci("e2e4")
board.push_uci("e7e5")
move = board.parse_san("Nf3")
print(board.uci(move))  # g1f3
print(board.san(move))  # Nf3: calcular ANTES de aplicar la jugada
board.push(move)
```

Una FEN completa contiene seis campos separados por espacios:

```text
rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1
|                 piezas                | |  |   | | |
                                         turno   contadores
```

1. Piezas por filas, desde la 8 hasta la 1; `/` separa filas y los dígitos cuentan casillas vacías. Mayúsculas blancas y minúsculas negras: `P N B R Q K`.
2. Turno: `w` o `b`.
3. Derechos de enroque: `KQkq` o el subconjunto que permanezca; `-` si ninguno.
4. Casilla objetivo de captura al paso, o `-`.
5. Medias jugadas desde la última captura o movimiento de peón.
6. Número de jugada completa; empieza en 1 y aumenta después de negras.

La FEN clásica puede incluir el objetivo al paso tras un avance doble aunque no exista captura legal; `board.fen()` de python-chess usa por defecto el criterio de captura legal. `board.fen(en_passant="fen")` conserva la convención clásica. No concluir que hay un error por esa diferencia aislada. [API y serialización de posiciones](https://python-chess.readthedocs.io/en/latest/core.html#chess.Board.fen).

**Una FEN no conserva la secuencia que llevó a la posición.** No basta por sí sola para recuperar repeticiones anteriores. Para partidas iniciadas normalmente, mantener el historial desde `startpos`; para una posición inicial personalizada, conservar esa FEN raíz más todas las jugadas posteriores. PGN tampoco forma parte del transporte UCI.

## 4. Comandos de la aplicación al motor

Cada fila describe una línea. Los corchetes en las explicaciones significan «opcional»; no se escriben literalmente. Referencias: [especificación](https://backscattering.de/chess/uci/) e [implementación de Stockfish 19](https://github.com/official-stockfish/Stockfish/blob/sf_19/src/uci.cpp).

| Comando | Propósito / respuesta esperada |
|---|---|
| `uci` | Negociación inicial: `id`, `option`, finalmente `uciok` |
| `isready` | Barrera de preparación: esperar `readyok` |
| `setoption name Hash value 64` | Configura una opción anunciada; no tiene confirmación UCI dedicada |
| `setoption name Clear Hash` | Activa una opción de tipo botón, sin `value` |
| `ucinewgame` | Avisa de una nueva partida; después sincronizar con `isready` |
| `position startpos` | Establece posición inicial |
| `position startpos moves e2e4 e7e5` | Reconstruye desde el inicio y aplica esa lista |
| `position fen <FEN> moves <lista>` | Reconstruye desde FEN raíz y aplica una lista opcional |
| `go ...` | Inicia búsqueda en la posición enviada |
| `stop` | Pide terminar la búsqueda; consumir su `bestmove` |
| `ponderhit` | Convierte una búsqueda ponder en búsqueda del turno real |
| `quit` | Solicita terminar el proceso |
| `debug on` / `debug off` | Depuración prevista por UCI; no asumir soporte en Stockfish 19 |
| `register later` / `register name ... code ...` | Registro comercial previsto por UCI; no se requiere para Stockfish |

**`isready` no significa que terminó una búsqueda**: puede responder mientras calcula. Para cancelar, usar `stop` y esperar `bestmove`. No hay un «OK» por cada `position`. Evitar cambiar opciones o posición mientras existe una búsqueda pendiente.

`ucinewgame` no reemplaza `position`: informa de un cambio de partida y permite limpiar estado de búsqueda. El tablero que se desea analizar se envía explícitamente.

### Parámetros de `go`

| Parámetro | Significado |
|---|---|
| `movetime 1000` | Presupuesto de búsqueda de 1000 ms |
| `wtime 60000 btime 60000` | Tiempo restante por color, en ms |
| `winc 1000 binc 1000` | Incremento por color, en ms |
| `movestogo 20` | Jugadas propias restantes hasta el siguiente control |
| `depth 12` | Profundidad nominal en plies, o medias jugadas |
| `nodes 100000` | Límite de nodos |
| `mate 3` | Buscar mate dentro de tres jugadas |
| `infinite` | Análisis hasta recibir `stop` |
| `ponder` | Búsqueda especulativa durante el turno rival |
| `searchmoves e2e4 d2d4` | Restringe las jugadas raíz consideradas |

Colocar `searchmoves` **al final de la línea** en Stockfish 19, porque su lector consume como jugadas el resto de esa línea. Validar esas jugadas en la posición raíz. [Lector de límites de Stockfish 19](https://raw.githubusercontent.com/official-stockfish/Stockfish/sf_19/src/uci.cpp).

Ejemplos independientes:

```text
go movetime 1000
go depth 12
go nodes 100000
go wtime 60000 btime 58000 winc 1000 binc 1000
go movetime 1000 searchmoves e2e4 d2d4
go infinite
```

No ejecutar estas seis búsquedas simultáneamente: terminar y consumir el resultado de una antes de empezar otra. Para la primera integración, usar solo `movetime`. `depth` no equivale a un tiempo fijo; más profundidad puede tardar mucho. Los límites de búsqueda no son garantías de tiempo real estricto para controlar un robot.

### Ponder, si se incorpora más adelante

Si el resultado fue `bestmove e7e5 ponder g1f3`, después de confirmar e7e5 se puede buscar sobre una copia que ya incluya el supuesto g1f3, con `go ponder ...`. Si el humano juega g1f3, enviar `ponderhit`; si juega otra cosa, enviar `stop`, consumir el resultado descartado y buscar sobre la posición real. La jugada ponder nunca se confirma solo por ser predicha. En la integración inicial, mantener ponder desactivado.

### Extensiones de Stockfish

`d` muestra el tablero, `eval` sirve para diagnóstico de evaluación estática, `go perft N` cuenta nodos de movimientos y `bench` / `speedtest` realizan mediciones. No son comandos UCI portables ni sustituyen `go` para elegir una jugada. No mezclar su salida con un parser que espere exclusivamente mensajes UCI. [Comandos de Stockfish](https://official-stockfish.github.io/docs/stockfish-wiki/UCI-Protocol-and-Stockfish-Commands.html).

## 5. Respuestas del motor

| Respuesta | Interpretación |
|---|---|
| `id name Stockfish 19` | Identificación de versión |
| `id author ...` | Autoría |
| `option name ... type ...` | Declaración de una opción configurable |
| `uciok` | Final de negociación UCI |
| `readyok` | Respuesta a `isready` |
| `info ...` | Progreso, evaluación o diagnóstico |
| `bestmove e7e5` | Jugada elegida para la raíz enviada |
| `bestmove e7e5 ponder g1f3` | Además, predicción de respuesta rival |
| `copyprotection checking/ok/error` | Mensajes de protección previstos por UCI; ajenos al uso normal de Stockfish |
| `registration checking/ok/error` | Registro previsto por UCI; ajeno al uso normal de Stockfish |

`bestmove` es el resultado que se puede proponer al controlador. Una jugada que aparece en `pv` es parte de un análisis provisional; no desencadena una acción física. `ponder` tampoco indica una segunda jugada que deba ejecutarse.

### Lectura de `info`

Ejemplo ilustrativo, no salida garantizada de una ejecución:

```text
info depth 12 seldepth 18 multipv 1 score cp 35 nodes 140000 nps 280000 hashfull 20 tbhits 0 time 500 pv e2e4 e7e5 g1f3
```

| Campo | Lectura |
|---|---|
| `depth`, `seldepth` | Profundidad nominal y selectiva, en plies |
| `multipv` | Índice de variante; 1 corresponde a la principal |
| `score cp 35` | Evaluación en la escala de centipeones del motor |
| `score mate 3` | Mate en 3 jugadas; signo negativo indica sufrir mate |
| `lowerbound`, `upperbound` | La puntuación es una cota, no un valor exacto |
| `nodes`, `nps` | Nodos acumulados y nodos por segundo |
| `hashfull` | Ocupación de hash en milésimas: 20 representa aproximadamente 2 % |
| `tbhits` | Aciertos en tablas de finales |
| `time` | Tiempo de búsqueda, en ms |
| `pv` | Variante principal, jugadas UCI desde la raíz |
| `currmove`, `currmovenumber` | Jugada raíz explorada e índice |
| `string` | El resto de la línea es texto libre |

La especificación también contempla `refutation`, `currline`, `sbhits` y `cpuload`; no asumir que Stockfish los emite. Los campos pueden faltar, cambiar de orden o ampliarse. No analizar `info string` como si sus palabras fueran campos estructurados. [Campos de información UCI](https://backscattering.de/chess/uci/#info).

Stockfish expresa la puntuación desde el punto de vista del bando al turno en la **raíz**. Un valor positivo cuando juegan negras favorece a negras. La escala de Stockfish está normalizada: `cp 100` no garantiza una ventaja material de exactamente un peón. Con `UCI_ShowWDL`, `wdl W D L` añade estimaciones de victoria/tablas/derrota en milésimas; son estimaciones, no certezas. [Salida de evaluación de Stockfish 19](https://raw.githubusercontent.com/official-stockfish/Stockfish/sf_19/src/uci.cpp).

En python-chess, usar `info["score"].pov(chess.WHITE)` para mostrar siempre la perspectiva blanca. No comparar directamente una puntuación de mate con un número de centipeones.

## 6. Ciclo de una partida

1. Iniciar un proceso Stockfish persistente.
2. Enviar `uci`; leer hasta `uciok`, conservando identificación y opciones.
3. Aplicar opciones admitidas; enviar `isready` y esperar `readyok`.
4. Enviar `ucinewgame`; sincronizar de nuevo; enviar la posición inicial.
5. Recibir una acción humana o una observación visual estable.
6. Validar la jugada en el estado confirmado y aplicarla una vez confirmada.
7. Enviar raíz e historial; solicitar `go` si corresponde el turno del motor.
8. Leer todas las líneas hasta `bestmove`; validar ese resultado contra la misma raíz.
9. Mostrar la propuesta y, si existe tablero físico, planificar y ejecutar su acción.
10. Confirmar el resultado físico; actualizar el estado confirmado una sola vez.
11. Comprobar resultado, relojes y política de tablas; repetir o finalizar.
12. Enviar `quit` al cerrar; esperar al proceso y cerrar recursos.

**`position` reconstruye, no añade jugadas a la posición anterior.** Por eso, con `startpos`, cada lista debe contener ambos colores desde el inicio. Si se parte de una FEN raíz, la lista contiene solo las jugadas posteriores a esa raíz. [Gestión de posiciones recomendada por Stockfish](https://official-stockfish.github.io/docs/stockfish-wiki/UCI-Protocol-and-Stockfish-Commands.html#position).

La aplicación administra el resultado de partida, las reclamaciones de tablas y el reloj. UCI no incluye un comando estándar `result 1-0` para informar de un final.

## 7. Prueba manual en la terminal

### 7.1 Abrir el ejecutable

En PowerShell, sustituir la ruta por la del ejecutable real:

```powershell
& "C:\ruta\stockfish\stockfish-windows-x86-64-universal.exe"
```

En Linux:

```bash
/ruta/al/stockfish
```

Los comandos siguientes se escriben **dentro de Stockfish**, no en PowerShell ni en el intérprete Python. Abrirlo desde una terminal permite conservar los mensajes si termina con error.

### 7.2 Inicio y primera respuesta

Escribir por etapas, respetando cada espera:

```text
uci
```

Esperar `uciok`; después:

```text
setoption name Threads value 2
setoption name Hash value 64
setoption name Ponder value false
isready
```

Esperar `readyok`; después:

```text
ucinewgame
isready
```

Esperar `readyok`; el humano juega e4:

```text
position startpos moves e2e4
go movetime 1000
```

Esperar una línea `bestmove`. Si, por ejemplo, fue `c7c5`, el humano puede responder g1f3:

```text
position startpos moves e2e4 c7c5 g1f3
go movetime 1000
```

Si la respuesta siguiente fue `d7d6` y el humano juega d2d4:

```text
position startpos moves e2e4 c7c5 g1f3 d7d6 d2d4
go movetime 1000
```

**Esas respuestas son condicionales.** Sustituirlas por las que efectivamente devolvió el motor; no copiar el historial supuesto sobre una partida diferente.

### 7.3 Ejemplo cerrado y reproducible de enroque

Con el motor sin búsqueda pendiente, esta secuencia legal deja a negras al turno y registra el enroque blanco:

```text
ucinewgame
isready
```

Tras `readyok`:

```text
position startpos moves e2e4 e7e5 g1f3 b8c6 f1c4 g8f6 e1g1
go depth 8
```

Esperar `bestmove`. Para analizar indefinidamente esa misma posición:

```text
go infinite
```

Cuando se quiera terminar el análisis:

```text
stop
```

Consumir `bestmove` y cerrar:

```text
quit
```

### 7.4 Posición FEN con promoción

En una nueva partida y tras la sincronización:

```text
position fen 7k/P7/8/8/8/8/8/7K w - - 0 1 moves a7a8q
go movetime 500
```

Ya se aplicó la promoción blanca, por lo que el motor calcula una respuesta negra. Para que **el motor elija** la promoción blanca, enviar esa misma FEN sin `moves a7a8q`.

## 8. Configuración del entorno y del motor

### Instalación

Descargar [Stockfish 19 desde el sitio oficial](https://stockfishchess.org/download/) para el sistema y arquitectura adecuados, extraer el paquete y apuntar al ejecutable, no al ZIP ni a la carpeta. La versión de un gestor de paquetes puede ser distinta: verificar `id name` mediante `uci`.

En un entorno virtual del proyecto:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install chess
$env:STOCKFISH_PATH = "C:\ruta\stockfish\stockfish-windows-x86-64-universal.exe"
```

Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install chess
export STOCKFISH_PATH="/ruta/al/stockfish"
# Si el archivo necesita permiso de ejecución:
chmod +x "$STOCKFISH_PATH"
```

`chess` proporciona los módulos `chess` y `chess.engine` de python-chess. Los ejemplos no necesitan un paquete Python llamado `stockfish`. `STOCKFISH_PATH` es una convención de esta guía; no es un comando UCI. Una variable definida en una terminal afecta a los procesos iniciados desde ella. Un archivo `.env` no se carga automáticamente con `os.environ`: requiere un cargador explícito.

### Opciones útiles

Consultar siempre las líneas `option` del ejecutable instalado. Los nombres, límites y valores predeterminados pueden cambiar. Esta tabla propone un punto de partida, no una configuración universal:

| Opción | Propuesta / finalidad |
|---|---|
| `Threads` | 2 para comenzar; ajustar dejando recursos a visión e interfaz |
| `Hash` | 64 MiB para una prueba pequeña; ajustar a la memoria disponible |
| `Ponder` | `false` durante la integración inicial |
| `MultiPV` | 1 para jugar; varias variantes para mostrar alternativas |
| `Skill Level` | 0–20; menor nivel reduce fuerza |
| `UCI_LimitStrength`, `UCI_Elo` | Activar límite de fuerza y elegir Elo dentro del intervalo anunciado |
| `UCI_ShowWDL` | Activa salida WDL |
| `UCI_Chess960` | `false` para ajedrez estándar |
| `Move Overhead` | Reserva temporal para sobrecostes; no controla el tiempo del robot |
| `SyzygyPath` y opciones `Syzygy*` | Tablas de finales instaladas por separado |
| `EvalFile` | Archivo de red NNUE; conservar la configuración distribuida salvo necesidad concreta |
| `NumaPolicy` | Afinidad/memoria en equipos NUMA; empezar por configuración automática |
| `nodestime` | Contabilidad basada en nodos; dejar 0 para uso normal con reloj |
| `Debug Log File` | Registro del intercambio para diagnóstico |
| `Clear Hash` | Botón para limpiar caché |

Stockfish aplica `UCI_Elo` cuando está activo `UCI_LimitStrength`, que tiene prioridad sobre el ajuste de habilidad. No suponer que el Elo equivale exactamente a una clasificación humana en cualquier ritmo. [Definición de opciones en Stockfish 19](https://raw.githubusercontent.com/official-stockfish/Stockfish/sf_19/src/engine.cpp) y [búsqueda y selección por habilidad](https://raw.githubusercontent.com/official-stockfish/Stockfish/sf_19/src/search.cpp).

Las opciones tienen tipos: `spin` entero con límites; `check` booleano; `combo` una alternativa anunciada; `string` texto; `button` acción sin valor. No introducir comillas de shell en los valores UCI por costumbre. Los nombres pueden contener espacios. [Tratamiento de opciones](https://raw.githubusercontent.com/official-stockfish/Stockfish/sf_19/src/ucioption.cpp).

Con python-chess, `Ponder`, `MultiPV` y `UCI_Chess960` se administran mediante su API y el tablero; no pasarlas a `configure()`. Usar `play(..., ponder=False)`, `analyse(..., multipv=3)` y `chess.Board(..., chess960=True)` según corresponda. [Opciones administradas por python-chess](https://raw.githubusercontent.com/niklasf/python-chess/master/chess/engine.py).

## 9. Validación antes de enviar posiciones

Aplicar tres controles: **formato**, **legalidad en el turno actual** y **coherencia del estado físico/lógico**. Una expresión regular solo resuelve el primero.

Stockfish 19 valida las posiciones de forma más estricta y puede emitir `info string CRITICAL ERROR` y terminar ante una entrada inválida. La corrección de `kg1kf3` es `g1f3`, pero incluso una cadena bien formada puede describir una jugada ilegal. [Validación documentada para Stockfish 19](https://official-stockfish.github.io/docs/stockfish-wiki/UCI-Protocol-and-Stockfish-Commands.html#position).

Validador para ajedrez estándar, incluyendo promociones y excluyendo jugadas nulas:

```python
import re
import chess

UCI_NORMAL = re.compile(r"[a-h][1-8][a-h][1-8][qrbn]?")

def validar_uci(board: chess.Board, texto: str) -> chess.Move:
    texto = texto.strip()
    if UCI_NORMAL.fullmatch(texto) is None:
        raise ValueError("Usa origen-destino y promoción opcional: g1f3, a7a8q")
    if not board.is_valid():
        raise ValueError(f"Posición inconsistente: status={board.status()}")
    move = board.parse_uci(texto)  # También comprueba legalidad en este tablero.
    if not move or move not in board.legal_moves:
        raise ValueError("Jugada nula o ilegal")
    return move

board = chess.Board()
for texto in ["e2e4", "e7e5", "g1f3"]:
    move = validar_uci(board, texto)
    board.push(move)
print(board.fen())
```

`chess.Move.from_uci()` interpreta un formato, pero no comprueba la legalidad sobre un tablero. `board.push()` tampoco es un validador de legalidad. Usar `board.parse_uci()` o comprobar pertenencia a `board.legal_moves` antes de `push()`. Las subclases de error de movimiento heredan de `ValueError`. [API de validación](https://python-chess.readthedocs.io/en/latest/core.html#chess.Board.parse_uci).

Para una FEN externa, construir `chess.Board(fen)` dentro de un `try/except ValueError` y comprobar `board.is_valid()`. Esa comprobación detecta inconsistencias básicas; no demuestra que la posición sea históricamente alcanzable ni reproduce exactamente todas las restricciones de Stockfish. Priorizar estados derivados de una raíz válida mediante jugadas legales. [Comprobaciones implementadas en python-chess](https://raw.githubusercontent.com/niklasf/python-chess/master/chess/__init__.py).

## 10. Partida interactiva con python-chess

Guardar el siguiente bloque como `jugar_terminal.py`. Humano con blancas, Stockfish con negras; entrada UCI. La política elegida acepta automáticamente tablas reclamables: para un torneo o interfaz con reclamaciones explícitas habría que cambiar esa política.

```python
import asyncio
import os
import chess
import chess.engine

def main():
    path = os.environ.get("STOCKFISH_PATH")
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
```

Ejecución después de configurar `STOCKFISH_PATH`:

```powershell
.\.venv\Scripts\python.exe jugar_terminal.py
```

```bash
.venv/bin/python jugar_terminal.py
```

`popen_uci()` realiza la negociación. `play()` transmite la posición y su pila de movimientos, espera el resultado y lo interpreta; `game` permite informar de cambios de partida automáticamente. No escribir comandos manuales en las tuberías del mismo proceso administrado por python-chess. [API de comunicación con motores](https://python-chess.readthedocs.io/en/latest/engine.html).

En la comprobación de esta guía, `chess` 1.11.2 mostró ocasionalmente `Unexpected engine output: 'info string Using 2 threads'` al configurar Stockfish 19. La partida continuó correctamente: ese mensaje informativo aislado no equivale a un error crítico. Conservar el registro para distinguirlo de un EOF o una excepción real.

Para análisis, dentro de una sesión con `engine` y `board`:

```python
info = engine.analyse(board.copy(stack=True), chess.engine.Limit(time=0.5))
score = info.get("score")
if score is not None:
    print("Perspectiva blanca:", score.pov(chess.WHITE))
print("Variante UCI:", [m.uci() for m in info.get("pv", [])])
```

No aplicar todas las jugadas de esa variante a la partida real. En Chess960, serializar cada movimiento con el tablero correspondiente al punto de la variante.

## 11. Comunicación directa con subprocess

Esta alternativa sirve para estudiar las líneas del protocolo. Para la aplicación completa, se recomienda el adaptador de python-chess. Guardar como `uci_subprocess.py`; requiere `chess` para validar la posición y `STOCKFISH_PATH` para localizar el motor.

El ejemplo mantiene un lector de salida, usa límites de espera y registra `stderr` por separado. El plazo local incluye inicialización y carga del equipo; no es el presupuesto de búsqueda del motor. [Documentación de subprocess](https://docs.python.org/3/library/subprocess.html).

```python
import os
import queue
import subprocess
import threading
import time
import chess

def main():
    path = os.environ["STOCKFISH_PATH"]
    board = chess.Board()
    history = ["e2e4", "e7e5", "g1f3"]
    for text in history:
        move = board.parse_uci(text)
        if not move or move not in board.legal_moves:
            raise ValueError(f"Movimiento rechazado: {text}")
        board.push(move)
    if not board.is_valid():
        raise ValueError("Posición inválida")

    with open("stockfish-stderr.log", "w", encoding="utf-8") as errors:
        process = subprocess.Popen(
            [path], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=errors, text=True, encoding="utf-8", errors="replace",
            bufsize=1, shell=False,
        )
        lines = queue.Queue()

        def reader():
            try:
                for line in process.stdout:
                    lines.put(line.rstrip("\r\n"))
            finally:
                lines.put(None)  # EOF: nunca interpretarlo como respuesta vacía.

        thread = threading.Thread(target=reader, daemon=True)
        thread.start()

        def send(command):
            if "\n" in command or "\r" in command:
                raise ValueError("Un comando debe ocupar una sola línea")
            if process.poll() is not None:
                raise RuntimeError("Stockfish ya terminó")
            print("GUI >", command)
            process.stdin.write(command + "\n")
            process.stdin.flush()

        def receive_until(predicate, seconds=15.0):
            deadline = time.monotonic() + seconds
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Plazo agotado esperando a Stockfish")
                try:
                    line = lines.get(timeout=remaining)
                except queue.Empty as exc:
                    raise TimeoutError("Sin respuesta de Stockfish") from exc
                if line is None:
                    raise RuntimeError("EOF del motor; revisar salida y registro")
                print("MOTOR >", line)
                if line.startswith("info string CRITICAL ERROR"):
                    raise RuntimeError(line)
                if predicate(line):
                    return line

        try:
            send("uci")
            receive_until(lambda s: s == "uciok")
            # Se usan opciones conocidas de Stockfish 19.
            send("setoption name Threads value 2")
            send("setoption name Hash value 64")
            send("isready")
            receive_until(lambda s: s == "readyok")
            send("ucinewgame")
            send("isready")
            receive_until(lambda s: s == "readyok")
            send("position startpos moves " + " ".join(history))
            send("go movetime 1000")
            line = receive_until(lambda s: s.startswith("bestmove "))
            parts = line.split()
            if len(parts) < 2:
                raise RuntimeError("Respuesta bestmove incompleta")
            text = parts[1]
            if text in {"0000", "(none)"}:
                print("Sin movimiento; estado local:", board.outcome())
                return
            move = board.parse_uci(text)
            if not move or move not in board.legal_moves:
                raise RuntimeError("Resultado ilegal o desactualizado")
            print("Jugada validada:", board.uci(move), board.san(move))
            board.push(move)  # Solo simulación lógica, sin robot.
        finally:
            if process.poll() is None:
                try:
                    send("quit")
                    process.wait(timeout=5)
                except (OSError, RuntimeError, subprocess.TimeoutExpired):
                    if process.poll() is None:
                        process.kill()
                    process.wait()
            process.stdin.close()
            thread.join(timeout=2)
            if not thread.is_alive():
                process.stdout.close()

if __name__ == "__main__":
    main()
```

Este programa hace una sola búsqueda limitada. Un cliente general necesitaría además gestionar cancelaciones, negociación dinámica de opciones, ponder y enrutamiento de solicitudes. La cola no está acotada: para análisis prolongados, consumirla continuamente o condensar solo los mensajes de progreso, preservando las respuestas de control.

Reglas prácticas al extenderlo:

- Usar una lista de argumentos con `shell=False`; una ruta con espacios sigue siendo un solo argumento.
- Escribir `\n` y hacer `flush()`. `bufsize=1` no sustituye el vaciado de entrada.
- Leer en paralelo: esperar al proceso sin drenar su salida puede bloquearlo.
- No usar un `stderr=PIPE` que nadie lea. Aquí se dirige a un archivo.
- Reservar `communicate()` para intercambios que terminan; envía entrada y cierra el flujo, por lo que no mantiene esta sesión interactiva.
- Una búsqueda cancelada sigue produciendo un resultado que se debe consumir y descartar si su raíz dejó de ser válida.

## 12. Integración con Pygame, YOLO y Kinova

### 12.1 Contrato de estado propuesto

Separar `board_confirmado`, una copia candidata y una propuesta pendiente. Asociar cada búsqueda a `game_id` y `position_version`. Solo aceptar el resultado si ambos coinciden con el estado vigente.

```text
ESPERANDO_HUMANO
    → VALIDANDO_OBSERVACIÓN
    → JUGADA_HUMANA_CONFIRMADA
    → CALCULANDO_MOTOR
    → PROPUESTA_VALIDADA
    → EJECUTANDO_ROBOT
    → VERIFICANDO_TABLERO
    → JUGADA_MOTOR_CONFIRMADA
    → ESPERANDO_HUMANO
```

Una discrepancia pasa a revisión del estado. No producir una nueva búsqueda sobre una escena a medio movimiento. Un resultado ajedrecístico legal no demuestra que el robot haya completado la acción.

### 12.2 Pygame

Mantener procesamiento de eventos y dibujo en el hilo principal. Ejecutar las llamadas bloqueantes a `SimpleEngine.play()` / `analyse()` en un trabajador y devolver resultados por una cola. Pygame exige atender su cola de eventos con regularidad para evitar perder eventos o aparentar bloqueo. [Documentación de eventos](https://www.pygame.org/docs/ref/event.html).

Propuesta de trabajo: entregar al trabajador una copia `board.copy(stack=True)` junto a su versión; al volver, comprobar la versión y la legalidad en el hilo del controlador. Deshabilitar nuevas entradas de jugada mientras se confirma una acción, aunque la ventana siga respondiendo. Mostrar promoción como elección explícita y mantener la orientación visual separada de las coordenadas UCI.

### 12.3 YOLO

YOLO genera detecciones; no conoce por sí solo turno, derechos de enroque ni historial. Si se usa Ultralytics, su API devuelve objetos `Results` con resultados según la tarea, por ejemplo cajas en `boxes`. El modelo debe estar entrenado para las piezas que se quieran distinguir. [Documentación de predicción](https://docs.ultralytics.com/modes/predict/).

Algoritmo propuesto para convertir una observación en jugada:

1. Calibrar imagen → plano del tablero → casillas; fijar inequívocamente a1 y h8.
2. Esperar una observación estable, sin mano o brazo tapando piezas.
3. Estimar mapa de piezas por casilla con incertidumbre, sin inventar metadatos FEN.
4. Enumerar `board_confirmado.legal_moves`; aplicar cada una sobre una copia.
5. Comparar cada mapa resultante con la observación, incluyendo enroque, captura al paso y promoción.
6. Confirmar solo si hay una coincidencia suficientemente clara. Si hay varias, pedir resolución; si no hay ninguna, conservar el estado y volver a observar.
7. Registrar la jugada UCI, versión anterior y nueva, evidencia visual y confirmación.

La regla «dos casillas cambiaron» falla para capturas, enroques y captura al paso. Una promoción requiere reconocer o seleccionar la pieza elegida. Si la cámara perdió varias jugadas, no inferir una única jugada arbitraria: reconstruir el historial con intervención del usuario.

### 12.4 Kinova Gen3 Lite

Antes de aplicar la jugada al tablero confirmado, consultar sobre el estado previo: `board.is_castling(move)`, `board.is_en_passant(move)`, `board.is_capture(move)` y `move.promotion`. Crear un plan semántico que el adaptador convierta a poses calibradas.

| Tipo | Acciones físicas que debe contemplar el plan |
|---|---|
| Normal | Recoger en origen y colocar en destino |
| Captura ordinaria | Retirar pieza de destino; después trasladar atacante |
| Al paso | Retirar peón de la casilla real capturada; trasladar atacante |
| Enroque | Trasladar rey y torre, verificando ambas piezas |
| Promoción | Trasladar peón y sustituirlo por la pieza seleccionada; gestionar reserva |

Para al paso en ajedrez estándar, la casilla capturada es `move.to_square - 8` si juega blanco y `move.to_square + 8` si juega negro. Calcularlo **antes** de `push()`, porque entonces `board.turn` sigue identificando al capturador.

UCI no determina alturas, marcos de referencia, velocidades, agarre, colisiones ni confirmación de trayectoria. Esas decisiones pertenecen al adaptador y a la configuración real. Usar las [API y ejemplos oficiales KORTEX para Gen3/Gen3 Lite](https://github.com/Kinovarobotics/Kinova-kortex2_Gen3_G3L) que correspondan al modelo y firmware; no asumir compatibilidad de cualquier driver ROS 2 con cualquier brazo.

Propuesta de confirmación: reservar una acción con identificador único, ejecutarla, recibir fin o error del controlador y verificar la disposición final con visión. Solo entonces hacer `push()` en `board_confirmado`. Si hay fallo parcial, retener el plan y reconciliar la escena; no volver a ejecutar toda la captura automáticamente. Mantener una parada accesible y límites de movimiento configurados en el sistema físico.

## 13. Casos límite, errores y recuperación

| Síntoma / entrada | Causa probable y tratamiento |
|---|---|
| `kg1kf3`, `Ng1f3` | Prefijos de pieza; rechazar y usar `g1f3` |
| `g1-f3`, `e4xd5`, `e7e8=Q` | Separadores SAN/no UCI; usar `g1f3`, `e4d5`, `e7e8q` si son legales |
| `e2e5` desde el inicio | Formato correcto, movimiento ilegal |
| `e7e5` como primera jugada | Bando incorrecto |
| `a7a8` para un peón que corona | Falta pieza de promoción |
| `a7a8k` / `a7a8p` | No se puede promover a rey ni peón |
| `e1g1` desde el inicio | Enroque bloqueado; tampoco basta con que la cadena sea correcta |
| `position moves ...` | Falta raíz: `startpos` o `fen <FEN>` |
| Enviar solo la última jugada con `startpos` | Se reconstruye un estado distinto; enviar historial desde la raíz |
| Se cierra la ventana | Revisar error crítico, ruta, arquitectura, red NNUE, permisos o final de entrada |
| `BrokenPipeError` / `EngineTerminatedError` | El proceso terminó; conservar diagnóstico y reconstruir tras corregir la causa |
| Ventana Pygame congelada | Operación bloqueante en el hilo de interfaz |
| No llega `bestmove` | Falta `go`, `flush`, lector, o se usó `infinite`/ponder sin finalización |
| `readyok` pero sigue pensando | Comportamiento previsto; no es final de búsqueda |
| Respuesta ilegal aunque el motor funciona | Raíz equivocada, historial incompleto o resultado de una búsqueda anterior |
| Resultado diferente entre ejecuciones | Tiempo, concurrencia, caché, opciones y versión pueden influir |
| Captura detectada como movimiento normal | La detección usa diferencias de ocupación insuficientes |

### Finales de partida y tablas

- **Jaque mate y ahogado:** ambos pueden dejar sin jugadas legales; distinguir con el tablero, no con `bestmove` solamente.
- **Repeticiones:** conservar historial; tres repeticiones permiten reclamar y cinco producen tablas automáticas según las reglas contempladas por python-chess.
- **Reglas de 50/75 movimientos:** son medias jugadas sin captura ni avance de peón; el umbral de reclamación de 50 movimientos equivale a 100 plies. La regla automática de 75 equivale a 150, con precedencia del mate cuando corresponde.
- **Material insuficiente:** la biblioteca detecta casos de material insuficiente; no usar una evaluación `cp 0` como prueba de tablas reglamentarias ni asumir que resuelve toda posición muerta posible.
- **Reloj, abandono y acuerdo:** los administra la aplicación. Una búsqueda puede devolver una jugada aun cuando la aplicación ya declaró pérdida por tiempo.

Usar `board.outcome(claim_draw=False)` para finales automáticos y funciones de reclamación para una política explícita. `claim_draw=True` también considera las tablas que pueden reclamarse con la siguiente jugada pertinente; por eso el programa de terminal puede finalizar antes de que se ejecute esa jugada. [Detección de finales en python-chess](https://raw.githubusercontent.com/niklasf/python-chess/master/chess/__init__.py).

### Estado válido frente a estado observado

Una escena que carece de un rey porque está oculto no es una nueva posición válida. No eliminar piezas del estado confirmado por una sola imagen. Los derechos de enroque no se recuperan por ver al rey y la torre en sus casillas originales; pueden haberse movido antes. La posibilidad al paso tampoco se deduce solo de la disposición actual.

### Reinicio y recuperación

Ante error crítico o EOF: detener el avance lógico y físico, conservar la raíz e historial confirmados y guardar comando enviado, salida reciente y código de retorno. Corregir la entrada o configuración; después iniciar otro proceso, renegociar, reconfigurar, enviar `ucinewgame`, sincronizar y reconstruir la posición. Un proceso muerto no se recupera con `isready`.

No repetir automáticamente una orden de robot por un fallo del motor. Stockfish puede reiniciarse sin que eso implique que el tablero físico volvió atrás. Mantener separados el registro UCI y el registro de acciones físicas.

### Comprobaciones antes de integrar hardware

1. Probar movimientos legales y rechazar `kg1kf3`, `e2e5`, `0000` y un movimiento de color incorrecto.
2. Verificar enroque, al paso y las cuatro promociones sobre posiciones preparadas.
3. Comprobar que mate y ahogado no generan una acción física.
4. Cancelar una búsqueda y descartar su respuesta al cambiar de partida.
5. Reiniciar Stockfish y reconstruir exactamente el estado confirmado.
6. Probar primero simulación; verificar después capturas, enroque y promoción como planes físicos separados.

## 14. Documentación verificada

Los enlaces siguientes fueron consultados el **5 de noviembre de 2026**. Los documentos `latest` pueden cambiar; los enlaces `sf_19` fijan la versión del código de Stockfish. La copia HTML de la especificación identifica a sus autores y enlaza el original: no es una norma publicada por FIDE.

| Fuente | Para qué consultar |
|---|---|
| [Shredder: Universal Chess Interface](https://www.shredderchess.com/chess-features/uci-universal-chess-interface.html) | Página de los autores y acceso a la especificación original |
| [Especificación UCI de abril de 2006, copia HTML](https://backscattering.de/chess/uci/) | Comandos y respuestas del protocolo general |
| [Stockfish: protocolo UCI y comandos](https://official-stockfish.github.io/docs/stockfish-wiki/UCI-Protocol-and-Stockfish-Commands.html) | Comportamiento documentado, opciones y validación estricta |
| [Stockfish 19: uci.cpp](https://github.com/official-stockfish/Stockfish/blob/sf_19/src/uci.cpp) | Lectura efectiva de comandos, formatos y errores |
| [Stockfish 19: engine.cpp](https://github.com/official-stockfish/Stockfish/blob/sf_19/src/engine.cpp) | Opciones disponibles y configuración del motor |
| [Stockfish 19: search.cpp](https://github.com/official-stockfish/Stockfish/blob/sf_19/src/search.cpp) | Búsqueda, selección de jugada y niveles de habilidad |
| [Stockfish 19: ucioption.cpp](https://github.com/official-stockfish/Stockfish/blob/sf_19/src/ucioption.cpp) | Tipos y lectura de opciones |
| [Descarga oficial de Stockfish](https://stockfishchess.org/download/) | Binarios por sistema y código fuente |
| [python-chess: núcleo](https://python-chess.readthedocs.io/en/latest/core.html) | Tableros, FEN, SAN, legalidad y finales |
| [python-chess: motores UCI/XBoard](https://python-chess.readthedocs.io/en/latest/engine.html) | `SimpleEngine`, `Limit`, `play`, análisis y puntuaciones |
| [python-chess: implementación del núcleo](https://github.com/niklasf/python-chess/blob/master/chess/__init__.py) | Alcance de validación y finales |
| [python-chess: implementación de motores](https://github.com/niklasf/python-chess/blob/master/chess/engine.py) | Opciones administradas y comunicación |
| [Python: subprocess](https://docs.python.org/3/library/subprocess.html) | Procesos, tuberías, plazos y cierre |
| [Pygame: event](https://www.pygame.org/docs/ref/event.html) | Procesamiento continuo de eventos |
| [Ultralytics YOLO: predict](https://docs.ultralytics.com/modes/predict/) | Inferencia y estructura de resultados, si se usa esta implementación |
| [Kinova: KORTEX Gen3/Gen3 Lite](https://github.com/Kinovarobotics/Kinova-kortex2_Gen3_G3L) | API y ejemplos del fabricante |

Para reproducir una prueba, registrar identificación del motor, plataforma, versión instalada de `chess`, opciones, raíz, historial y límite de búsqueda. No fijar como resultado esperado una jugada concreta de un ejemplo ilustrativo.

### Verificación de los ejemplos entregados

Se comprobaron con Python 3.13.5, `chess` 1.11.2 y el binario oficial Windows x86-64 universal identificado como **Stockfish 19**: sintaxis de los cinco bloques Python, partida de terminal con una respuesta del motor, rechazo de `kg1kf3`, búsqueda por `subprocess`, análisis y legalidad de las secuencias de ejemplo. También se comprobaron las cuatro promociones, posiciones terminales de mate y ahogado, el rechazo de entradas nulas, ilegales o de color incorrecto y la terminación con error crítico de Stockfish 19 ante `kg1kf3`. Pygame, YOLO y Kinova se describen como arquitectura de integración; esta verificación no incluye cámara ni hardware robótico.
