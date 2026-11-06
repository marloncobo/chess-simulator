# Calibración física del tablero

La cámara estima apoyos sobre el plano del tablero. El origen es el vértice
exterior junto a **a8**, X crece hacia **h8** e Y hacia **a1**. Marque siempre
los cuatro vértices **a8 → h8 → h1 → a1**, excluyendo el marco decorativo.
Mida el ancho y el alto del área de las 64 casillas, en metros.

## Perfil del tablero

Cree `config/tablero.json` con sus medidas. Este ejemplo corresponde a un
tablero de 40 × 40 cm; sustitúyalas por las medidas reales:

```json
{
  "identificador": "tablero-principal",
  "ancho_m": 0.40,
  "alto_m": 0.40,
  "ejes": {"origen": "a8", "x": "h8", "y": "a1"}
}
```

No hay tamaño físico predeterminado. Sin `--tablero`, la aplicación reconoce
casillas sin publicar metros. La conversión conserva el apoyo continuo antes
de asignar una casilla: `X = x * ancho_m / 8`, `Y = y * alto_m / 8`.
Por ejemplo, `(4.3, 3.6)` en un tablero de 0.40 × 0.40 m da `(0.215, 0.180) m`.
`TableroFisico.centro("e4")` calcula el centro para colocar una pieza; el apoyo
detectado sirve para estimar dónde agarrarla. Son posiciones distintas.

## Una cámara

Desde la raíz del repositorio, con el entorno virtual activo:

```powershell
python main.py --camara --source 1 --tablero config/tablero.json --contexto-calibracion montaje-v1
```

Marque los vértices sobre la imagen. La calibración se guarda automáticamente;
G guarda, L carga y R permite repetirla. La cámara muestra casilla y X/Y en
metros sobre los apoyos aceptados en imágenes estables y recientes. Conflictos,
descartes por límites de piezas y detecciones dudosas no aportan coordenadas.
Las etiquetas son observaciones actuales; el seguimiento de casillas puede
conservar una posición anterior cuando la imagen deja de ser fiable.

La fotografía reutiliza ahora la misma homografía que el vídeo, pero sigue
mostrando solo casillas a partir de centroides; no acepta `--tablero`.

## Perfiles de cámara y compatibilidad

Ambas interfaces usan `config/calibracion_<huella-de-source>.json`, con versión,
fecha UTC, fuente, resolución real, esquinas, copia del perfil físico y contexto.
La huella distingue un índice numérico de una URL. Una calibración guardada
desde una interfaz puede cargarse desde la otra.

Se rechazan otra fuente, resolución, tablero, dimensiones, ejes, versión o
contexto. Cambie `--contexto-calibracion` y vuelva a marcar los vértices si cambia
posición, orientación, lente, zoom o recorte. Los cambios físicos con la misma
resolución **no se detectan automáticamente**; requieren intervención del operador.
Si un perfil común existe y es incompatible, no se intenta otro antiguo.

Cuando aún no existe un perfil común, se buscan los archivos antiguos de la
interfaz usada. Estos siguen sirviendo para casillas. Para publicar metros con
ellos hay que recalibrar y guardar con `--tablero`; no se inventan dimensiones.
Los JSON de `config/` contienen configuración local y no se versionan.

## Dos cámaras

```powershell
python probar_dos_camaras.py --detectar --sources 0 1 --tablero config/tablero.json --contexto-calibracion montaje-v1
```

Calibre cada cámara con 1 y 2, identificando los mismos vértices del mismo tablero.
L carga ambos perfiles. La fusión conserva apoyos continuos aceptados y, con un
perfil físico, `Vista.posiciones_fisicas[(fila, columna)]` contiene:

- `xy_m`: media de los apoyos disponibles, sin redondear al centro de casilla.
- `muestras`: posición en metros, confianza y número de vista de cada contribución.
- `discrepancia_m`: distancia entre ambas mediciones, o `null` con una sola vista.
- `dentro_tolerancia`: comparación con `--max-discrepancia-m`, o `null` si falta
  una segunda vista o no se definió tolerancia.

Las etiquetas muestran X/Y y discrepancia, o indican que la medida es unilateral.
Se puede añadir, por ejemplo, `--max-discrepancia-m 0.005` para marcar discrepancias
superiores a 5 mm. Es solo un ejemplo, no una tolerancia validada. Superar la
tolerancia marca la medida física y conserva el reconocimiento de tipo y casilla.
El acuerdo entre cámaras no prueba exactitud absoluta: pueden compartir un sesgo.

## Validación física independiente

Use puntos distintos de los cuatro vértices usados para ajustar: centro, bordes,
zonas próximas a esquinas y piezas desplazadas dentro de casillas. Mida X/Y con
respecto al origen y registre el píxel correspondiente al apoyo. Repita capturas
del mismo punto sin moverlo, conservando su `id`; identifique cada captura.
Si mueve la pieza a otra posición medida, use otro `id`.

Guarde un JSON como `config/medidas.json`. Este es únicamente un ejemplo del
formato, no un resultado medido:

```json
{
  "source": 1,
  "resolucion": [800, 800],
  "muestras": [
    {"id": "centro", "captura": "01", "pixel": [400, 400], "xy_m": [0.20, 0.20]},
    {"id": "centro", "captura": "02", "pixel": [401, 400], "xy_m": [0.20, 0.20]}
  ]
}
```

```powershell
python -m herramientas.verificar_calibracion --tablero config/tablero.json --calibracion config/calibracion_HUELLA.json --medidas config/medidas.json --contexto-calibracion montaje-v1
```

Sustituya `HUELLA` por el nombre guardado en `config/`. La herramienta verifica
fuente, resolución y asociación física y escribe `resultados/precision_calibracion.json`
(o `--salida`). Registra errores por muestra, media, máximo y RMSE en milímetros,
además de la separación máxima entre capturas repetidas de cada punto. Rechaza
los cuatro píxeles utilizados para ajustar. Añada `--tolerancia-mm` únicamente
cuando haya establecido la tolerancia de su montaje, piezas y pinza.

**Estado de validación:** hay pruebas automatizadas con geometría sintética y
errores conocidos. No se han aportado medidas físicas del montaje, por lo que
no hay un informe de precisión real ni una tolerancia de agarre validada.
La repetibilidad requiere varias capturas por punto y la cobertura espacial
debe comprobarse al preparar las muestras; un informe con pocos puntos no
demuestra precisión en todo el tablero.

La homografía describe un plano. La altura de la pieza, el estimador de su base,
la distorsión de lente y la selección de vértices pueden introducir sesgo.
La transformación a la base del robot (`R p + t`), alturas de agarre y compensación
de pinza requieren otra calibración y quedan como trabajo posterior.

## Pruebas

```powershell
python -m unittest discover -s tests -q
```
