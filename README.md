# ps2-znt-gamedev-tools

SDK de ingeniería inversa para el engine de **Zero no Tsukaima: Koakuma to
Harukaze no Concerto** (PS2, `SLPS-25709`, Marvelous Interactive, 2006). Abre los
datos del juego, expone sus sistemas de forma tipada y documenta la API que el
motor da a los scripts — la base para reimplementar el engine fuera de la consola.

Todo es **Python de stdlib, sin dependencias**. Cada módulo trae un self-check
sintético que no depende de tener el juego: `python3 -m znt demo`.

**Instalación** (opcional; deja el comando `znt` en el PATH):

```sh
pip install -e .          # editable; requiere Python 3.9+ (tkinter para el editor)
znt demo                  # desde cualquier carpeta
znt studio               # abre VN Studio
```
Sin instalar: `python3 -m znt <grupo> ...` desde la raíz del repo.

> **Legal.** Herramientas y notas de formato para interoperabilidad. No se
> distribuye ningún asset del juego; el `.gitignore` los excluye. Cualquier
> resultado se publica como parche binario, nunca como ISO.

---

## El roadmap: capa 2 → 1 → 3

El engine se saca en tres capas apiladas. Este repo cubre la **2** y la **2b**.

```
┌───────────────────────────────────────────────┐
│  3. Autoría   crear una VN nueva (player PC)     │  ✅ DSL .vn -> player HTML
├───────────────────────────────────────────────┤
│  1. Runtime   correr las escenas en la PC       │  ✅ ventana en vivo +
│     VM Squirrel + render TIM2/fuente + animación│     animación (frontend aparte)
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

  **Runtime en vivo, con frontend desacoplado:** el core `engine` es headless
  (estado de capas con **animación por tween**, cuadro de diálogo, corrutina de
  escena que suspende en cada `talk`) y no sabe nada de la pantalla; los
  frontends de `frontends` lo consumen — `TkWindow` (ventana en vivo, tkinter) y
  un export **APNG** a todo color. La animación sale de las props de `set`
  (`xFrom`→`x` en `moveTime`, `opacityFrom`→`opacity`), y las escenas encadenan
  solas por `next`.

  ```sh
  python3 -m znt play   iso 1000              # ventana en vivo (click/espacio avanza)
  python3 -m znt record iso 1000 out.apng     # graba la corrida a un PNG animado
  python3 -m znt testbench iso 1000           # banco de pruebas: anima capas en vivo
  ```

  El **banco de pruebas** (`testbench`) corre el engine real y deja inyectar
  animaciones en vivo sobre las capas de la escena (elegís capa + curva o acción +
  parámetros y lo ves moverse), con un inspector del estado de cada capa. Su núcleo
  `Bench` es headless y guionable (sin tkinter).

  Falta para runtime completo: los módulos de animación `LayerModule` (curvas
  accel/decel/wave, no solo tween lineal), audio, y entrada más allá de avanzar.
- **Capa 3** — autoría de una VN nueva. Formato de texto `.vn` (personajes,
  escenas, `bg`/`show`/`say`/`choice`/`goto`) que `vn` compila a un player HTML
  autocontenido y compartible. Ver [`docs/authoring.md`](docs/authoring.md).

  ```sh
  python3 -m znt vn build historia.vn player.html
  python3 -m znt vn demo-build player.html      # genera un ejemplo jugable
  ```

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
  # capa 2 — acceso a datos
  container.py  par .HD/.BIN  + clase Container (repack)
  codec.py      decompress (del ELF) + compress_store
  tim2.py       lector TIM2 -> PNG/RGBA + clase Texture (des-swizzle CLUT)
  font.py       atlas BMP + mapeo    + clase Font
  scriptscan.py escaner de la API Squirrel del engine (capa 2b)
  __init__.py   znt.open() -> Disc.scenes / .textures / .font
  __main__.py   CLI unificada (python -m znt <grupo> ...)
  # capa 1 — runtime off-console
  render.py     Layer/MessageWindow + compositor a PNG
  sqparse.py    tokenizer + parser Pratt de Squirrel
  sqtranspile.py  AST Squirrel -> Python
  sqrt.py       runtime del código transpilado (objetos, corrutinas)
  sqrun.py      corre una escena real y saca frames
  engine.py     runtime en vivo headless (animación + corrutina de escena)
  frontends.py  frontend headless del engine: export APNG
  # framework de creación de VN (headless)
  image.py      lector PNG stdlib -> filas RGBA (assets propios)
  vnstudio.py   VNRuntime: reproduce un modelo autoral con el render/animación real
  # capa 3 — autoría
  vn.py         DSL .vn -> player HTML + ops de modelo (validate/rename/...)
  gui/          FRONT INTERACTIVO (tkinter) — opcional, borrable, no lo importa el core
    studio.py     VN Studio: editor gráfico
    testbench.py  banco de pruebas (inyecta animación en vivo)
    window.py     ventana en vivo (play)
docs/engine_api.md   catálogo de la API del engine (capa 2b)
docs/authoring.md    formato .vn para crear una VN (capa 3)
research/codec_search.py   búsqueda automatizada del codec (resultado negativo)
```

Un self-check por módulo, sin depender del juego: `python3 -m znt demo` (16/16).

**Core headless separable.** Todo el paquete `znt` es headless salvo `znt/gui/`
(el front tkinter). Se puede **borrar `znt/gui/` entero** y el core sigue: acceso a
datos, codec, render, transpilador, runtime, `record` a APNG y el `VNRuntime` de VN.
`znt demo` lo reporta y los comandos `play`/`testbench`/`studio` avisan si el front
no está. Ningún módulo del core importa `gui` ni `tkinter`.

## VN Studio — editor gráfico (`python -m znt studio [proyecto.vn]`)

Corre el engine real; edita un proyecto `.vn`:

- Escenas y pasos (`bg`/`show`/`hide`/`say`/`animate`/`choice`/`goto`/`end`):
  agregar, duplicar, reordenar, borrar; renombrar/reordenar escenas.
- Sprites: asignar PNG por personaje, **arrastrar en el escenario** con **snap +
  guías** (centro/presets/piso/otros sprites; Shift = libre).
- Por capa: **orden Z** (al frente/fondo), **zoom**, **opacidad**, **tinte**.
- **Previsualización de transiciones** (▶ probar) sin entrar a Play; **Play** corre
  la escena con animación real; **undo/redo** (Ctrl+Z/Y).
- **Validar** el proyecto (gotos/personajes/dead-ends/assets), **biblioteca de
  assets** (doble-click asigna), **Guardar .vn** / **Exportar** a player HTML.

Lógica de modelo testeable en `vn.py` (`validate`/`rename_character`/
`duplicate_scene`/`move_scene`/`list_assets`); el runtime `VNRuntime` es headless.

### En el browser (`python -m znt web [proyecto.vn]`)

Mismo editor sin tkinter: el server (stdlib) es la fuente de verdad — corre el
`VNRuntime` real y describe el layout; el browser lo compone con CSS en % (se
reescala solo con la ventana) y las animaciones llegan como APNG del engine.

Layout de app de edición: barra de herramientas, **outliner** (escenas + capas
del paso, al frente primero), **viewport** centrado con letterbox, marco de
selección con handles (arrastrar una esquina = zoom) y guías (centro / tercios /
zona segura), **inspector** con secciones plegables y campos numéricos que se
arrastran (Shift = fino), **timeline** con una pista por tipo de paso, regla,
playhead, scrub y reordenar arrastrando (Ctrl+rueda = zoom), y barra de estado.
Los tres paneles se redimensionan y el tamaño queda guardado.

Atajos: Espacio (Play/avanzar), Esc, ←/→, Supr, G (guías), Ctrl+Z/Y/S, **?**
(lista completa). Nuevo/abrir/personaje/escena usan diálogos propios.

Funciones: **Play** (los choices saltan de escena), **orden Z**, selectores de
sprite, fondo y audio con botón **"…"** para elegir un archivo de tu compu (se
copia junto al `.vn`), y editar id/nombre/color del personaje.

`znt/web/` es opcional igual que `znt/gui/`: se puede borrar y el core sigue.
