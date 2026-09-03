# ps2-znt-gamedev-tools

SDK de ingeniería inversa para el engine de **Zero no Tsukaima: Koakuma to
Harukaze no Concerto** (PS2, `SLPS-25709`, Marvelous Interactive, 2006). Abre los
datos del juego, expone sus sistemas de forma tipada y documenta la API que el
motor da a los scripts — la base para reimplementar el engine fuera de la consola.

Todo es **Python de stdlib, sin dependencias**. Cada módulo trae un self-check
sintético que no depende de tener el juego: `python3 -m znt demo`.

> **Legal.** Herramientas y notas de formato para interoperabilidad. No se
> distribuye ningún asset del juego; el `.gitignore` los excluye. Cualquier
> resultado se publica como parche binario, nunca como ISO.

---

## El roadmap: capa 2 → 1 → 3

El engine se saca en tres capas apiladas. Este repo cubre la **2** y la **2b**.

```
┌───────────────────────────────────────────────┐
│  3. Autoría   crear una VN nueva sobre el engine│  (pendiente)
├───────────────────────────────────────────────┤
│  1. Runtime   correr las escenas en la PC       │  ✅ MVP: escena real
│     VM Squirrel + render TIM2/fuente            │     transpilada y dibujada
├───────────────────────────────────────────────┤
│  2. Acceso    abrir/inspeccionar/modificar/repack│  ✅
│     contenedor, codec, TIM2, fuente             │
└───────────────────────────────────────────────┘
```

- **Capa 2** — librería `znt` de acceso a datos. Lee y escribe todos los formatos,
  no ejecuta la lógica del juego.
- **Capa 2b** — la API del engine hacia los scripts, mapeada en
  [`docs/engine_api.md`](docs/engine_api.md). Es el insumo de la capa 1.
- **Capa 1** — runtime off-console. La fuente Squirrel se **transpila a Python**
  (`sqparse` → `sqtranspile`) y corre sobre `sqrt` (modelo de objetos, corrutinas
  stackful); `render` dibuja capas TIM2 + texto con la fuente; `sqrun` implementa
  los comandos de escena (`set`/`talk`/`reset`/`next`...) y compone frames.
  **1920/1920 escenas transpilan y compilan**; una escena real corre y se dibuja:

  ```sh
  python3 -m znt sqrun iso 1000 frame.png     # transpila+ejecuta+dibuja la escena 1000
  ```

  Falta para runtime completo: animación (módulos Layer), audio, flujo entre
  escenas por corrutina, entrada y ventana en vivo. El núcleo está probado.

## Uso como librería

```python
import znt
disc = znt.open("iso")           # dir con los pares .HD/.BIN extraidos del disco
src  = disc.scenes[1]            # fuente Squirrel de la escena (str, CP932)
tex  = disc.textures[12]         # Texture -> tex.png("bg.png")
font = disc.font                 # atlas de glifos + mapeo caracter->indice

disc.scenes.set(1, nuevo.encode("cp932"))
disc.scenes.repack()             # reescribe SCENE_ID.HD/.BIN
```

## CLI

```sh
python3 -m znt demo                                       # self-check de todo
python3 -m znt container info  SCENE_ID.HD SCENE_ID.BIN   # par crudo .HD/.BIN
python3 -m znt extract         SCENE_ID.HD SCENE_ID.BIN out/ .nut   # descomprime
python3 -m znt tim2 png        0012.tm2 nombres.png
python3 -m znt font widths     0006.bmp 0005.txt          # anchos de tinta (VWF)
python3 -m znt scan            scripts/ --elf SLPS_257.09  # API del engine
```

Los pares se sacan del ISO con `7z` (ISO9660 plano, sin contenedores anidados):

```sh
7z e -y 'Zero no Tsukaima KtHC.iso' -oiso '*.HD' '*.BIN' 'SLPS_257.09'
```

---

## Formatos (referencia)

### Contenedor `.HD` / `.BIN` — `znt/container.py`
Cada sistema es un par. **`.HD`** es un array plano de `uint32` little-endian con
los tamaños de cada entrada (sin header ni magic; `len(HD)/4` = cantidad).
**`.BIN`** son las entradas concatenadas, cada una rellenada a **2048 bytes** (un
sector de DVD). Verificado byte-exacto en los cinco pares del disco.

| Par | Entradas | Contenido |
|---|---:|---|
| `SCENE_ID` | 1921 | los scripts (fuente Squirrel) |
| `SCENEDAT` | 1184 | texturas TIM2 (CGs, sprites) |
| `NORMAL`   | 360  | texturas TIM2 (UI, fuente) |
| `VOICE_ID` | 16192| voces |
| `SOUND_ID` | 106  | música y SFX |

### Codec — `znt/codec.py`
Portado de la rutina en `0x0011c264`-`0x0011c5e8` del ELF. **No es un LZ sobre la
salida**: los opcodes de match referencian una lista move-to-front de las 6
posiciones de token más recientes del *stream de entrada*.

| token | opcode |
|---|---|
| `0xE0`-`0xFF` | corrida de `(T & 0x1F) + 1` literales |
| `0xC0`-`0xDF` | RLE: el byte siguiente, `(T & 0x1F) + 2` veces |
| `0x00`-`0xBF` | replay del token en `recent[T >> 5]` |

El diccionario viene cebado con seis buffers de un RLE de cero, así un replay
contra un slot no usado emite ceros. Tras la pasada LZ hay un de-interleave de
`cnt` planos. Validado: 3365/3365 entradas del disco descomprimen con `usize`
exacto. **`compress_store`** hace la inversa mínima (codifica como corridas de
literales) para reinsertar entradas modificadas sin reimplementar el compresor
original.

### Fuente — `znt/font.py`
`NORMAL` #0006 es un BMP monocromo 1bpp de 1024x1380 con celdas de **24x26**, 42
glifos por fila. #0005 es el mapeo carácter→glifo: texto plano CP932, 42 caracteres
por línea, la línea N es la fila N del atlas. El renderer es **monoespaciado** (no
hay tabla de anchos en el ELF); `font.py` mide el ancho de tinta real de cada glifo
para un futuro VWF.

### TIM2 — `znt/tim2.py`
Lector mínimo de TIM2 (4bpp/8bpp indexado) con volcado a PNG en escala de grises,
solo stdlib.

### El motor — `docs/engine_api.md`
Los scripts son **fuente Squirrel** (bindings SqPlus, confirmado en el ELF).
`znt/scriptscan.py` mapea la API: separa definiciones de llamadas sobre las 1920
escenas y cruza los nativos candidatos con los strings del ELF. Resultado: 36
nativos globales (35 confirmados), clases `Layer`/`MessageWindow`, y toda la
biblioteca de animación que corre script-side. Ver el catálogo completo.

## Estructura

```
znt/            el SDK (paquete importable, stdlib)
  container.py  par .HD/.BIN  + clase Container (repack)
  codec.py      decompress (del ELF) + compress_store
  tim2.py       lector TIM2 -> PNG   + clase Texture
  font.py       atlas BMP + mapeo    + clase Font
  scriptscan.py escaner de la API Squirrel del engine
  __init__.py   znt.open() -> Disc.scenes / .textures / .font
  __main__.py   CLI unificada
docs/engine_api.md   catálogo de la API del engine (capa 2b)
research/codec_search.py   búsqueda automatizada del codec (resultado negativo)
```
