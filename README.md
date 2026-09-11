# ps2-znt-gamedev-tools

Reverse-engineering SDK for the engine of **Zero no Tsukaima: Koakuma to
Harukaze no Concerto** (PS2, `SLPS-25709`, Marvelous Interactive, 2006). It opens
the game data, exposes its systems in typed form and documents the API the engine
gives to the scripts — the groundwork for reimplementing the engine off-console.

Everything is **stdlib Python, no dependencies**. Every module ships a synthetic
self-check that does not need the game: `python3 -m znt demo`.

**Install** (optional; puts the `znt` command on the PATH):

```sh
pip install -e .          # editable; needs Python 3.9+ (tkinter for the editor)
znt demo                  # from any folder
znt studio               # opens VN Studio
```
Without installing: `python3 -m znt <group> ...` from the repo root.

> **Legal.** Tools and format notes for interoperability. No game asset is
> distributed; the `.gitignore` excludes them. Any result is published as a
> binary patch, never as an ISO.

---

## The roadmap: layer 2 → 1 → 3

The engine comes out in three stacked layers. This repo covers **2** and **2b**.

```
┌──────────────────────────────────────────────────┐
│  3. Authoring  create a new VN (PC player)       │  ✅ .vn DSL -> HTML player
├──────────────────────────────────────────────────┤
│  1. Runtime    run the scenes on the PC          │  ✅ live window +
│     Squirrel VM + TIM2/font render + animation   │     animation (separate frontend)
├──────────────────────────────────────────────────┤
│  2. Access     open/inspect/modify/repack        │  ✅
│     container, codec, TIM2, font                 │
└──────────────────────────────────────────────────┘
```

- **Layer 2** — the `znt` data-access library. Reads and writes every format,
  does not run game logic.
- **Layer 2b** — the engine's API towards the scripts, mapped in
  [`docs/engine_api.md`](docs/engine_api.md). It is the input for layer 1.
- **Layer 1** — off-console runtime. The Squirrel source is **transpiled to Python**
  (`sqparse` → `sqtranspile`) and runs on `sqrt` (object model, stackful
  coroutines); `render` draws TIM2 layers + text with the font; `sqrun` implements
  the scene commands (`set`/`talk`/`reset`/`next`...) and composes frames.
  **1920/1920 scenes transpile and compile**; a real scene runs and gets drawn:

  ```sh
  python3 -m znt sqrun iso 1000 frame.png     # transpile+run+draw scene 1000
  ```

  **Live runtime, with a decoupled frontend:** the `engine` core is headless
  (layer state with **tween animation**, dialogue box, scene coroutine that
  suspends on every `talk`) and knows nothing about the screen; the frontends in
  `frontends` consume it — `TkWindow` (live window, tkinter) and a full-colour
  **APNG** export. Animation comes from the `set` props (`xFrom`→`x` over
  `moveTime`, `opacityFrom`→`opacity`), and scenes chain on their own via `next`.

  ```sh
  python3 -m znt play   iso 1000              # live window (click/space advances)
  python3 -m znt record iso 1000 out.apng     # record the run to an animated PNG
  python3 -m znt testbench iso 1000           # test bench: animate layers live
  ```

  The **test bench** (`testbench`) runs the real engine and lets you inject
  animations live onto the scene's layers (pick layer + curve or action +
  parameters and watch it move), with an inspector of every layer's state. Its
  `Bench` core is headless and scriptable (no tkinter).

  Still missing for a complete runtime: the `LayerModule` animation modules
  (accel/decel/wave curves, not just linear tween), audio, and input beyond
  advancing.

  **Native PS2 player** (`ps2/`, C with gsKit/audsrv): the same compiled `.vn`
  (`znt iso build`) comes out as a **bootable ISO**. Runs in PCSX2 with backgrounds
  and sprites (8-bit with palette when nothing is lost), crossfade, tweens with
  curves, text with typing and word wrap, choices, streamed BGM and effects on the
  SPU2, **saves on the memory card**, pause menu, history and fast-forward. Data is
  read from the DVD on demand, sector-aligned (1.4 MB/s). See
  [`docs/build-ps2.md`](docs/build-ps2.md) and [`docs/checklist.md`](docs/checklist.md)
  (`tests/checklist.sh` runs the 19 items in order, with real build and boot).
- **Layer 3** — authoring a new VN. A `.vn` text format (characters, scenes,
  `bg`/`show`/`say`/`choice`/`goto`) that `vn` compiles to a self-contained,
  shareable HTML player. See [`docs/authoring.md`](docs/authoring.md).

  ```sh
  python3 -m znt vn build story.vn player.html
  python3 -m znt vn demo-build player.html      # generates a playable example
  ```

## Use as a library

```python
import znt
disc = znt.open("iso")           # dir with the .HD/.BIN pairs extracted from the disc
src  = disc.scenes[1]            # Squirrel source of the scene (str, CP932)
tex  = disc.textures[12]         # Texture -> tex.png("bg.png")
font = disc.font                 # glyph atlas + character->index mapping

disc.scenes.set(1, new.encode("cp932"))
disc.scenes.repack()             # rewrites SCENE_ID.HD/.BIN
```

## CLI

```sh
python3 -m znt demo                                       # self-check of everything
python3 -m znt container info  SCENE_ID.HD SCENE_ID.BIN   # raw .HD/.BIN pair
python3 -m znt extract         SCENE_ID.HD SCENE_ID.BIN out/ .nut   # decompress
python3 -m znt tim2 png        0012.tm2 names.png
python3 -m znt font widths     0006.bmp 0005.txt          # ink widths (VWF)
python3 -m znt scan            scripts/ --elf SLPS_257.09  # engine API
```

The pairs come out of the ISO with `7z` (flat ISO9660, no nested containers):

```sh
7z e -y 'Zero no Tsukaima KtHC.iso' -oiso '*.HD' '*.BIN' 'SLPS_257.09'
```

---

## Formats (reference)

### `.HD` / `.BIN` container — `znt/container.py`
Every system is a pair. **`.HD`** is a flat array of little-endian `uint32` with
the size of each entry (no header or magic; `len(HD)/4` = count). **`.BIN`** is
the concatenated entries, each padded to **2048 bytes** (one DVD sector).
Verified byte-exact on the five pairs of the disc.

| Pair | Entries | Content |
|---|---:|---|
| `SCENE_ID` | 1921 | the scripts (Squirrel source) |
| `SCENEDAT` | 1184 | TIM2 textures (CGs, sprites) |
| `NORMAL`   | 360  | TIM2 textures (UI, font) |
| `VOICE_ID` | 16192| voices |
| `SOUND_ID` | 106  | music and SFX |

### Codec — `znt/codec.py`
Ported from the routine at `0x0011c264`-`0x0011c5e8` in the ELF. **It is not an LZ
over the output**: the match opcodes reference a move-to-front list of the 6 most
recent token positions of the *input stream*.

| token | opcode |
|---|---|
| `0xE0`-`0xFF` | run of `(T & 0x1F) + 1` literals |
| `0xC0`-`0xDF` | RLE: the next byte, `(T & 0x1F) + 2` times |
| `0x00`-`0xBF` | replay of the token at `recent[T >> 5]` |

The dictionary comes primed with six buffers of a zero RLE, so a replay against an
unused slot emits zeros. After the LZ pass there is a de-interleave of `cnt`
planes. Validated: 3365/3365 entries of the disc decompress to the exact `usize`.
**`compress_store`** does the minimal inverse (encodes as literal runs) to
reinsert modified entries without reimplementing the original compressor.

### Font — `znt/font.py`
`NORMAL` #0006 is a 1bpp monochrome BMP of 1024x1380 with **24x26** cells, 42
glyphs per row. #0005 is the character→glyph mapping: plain CP932 text, 42
characters per line, line N is row N of the atlas. The renderer is **monospaced**
(there is no width table in the ELF); `font.py` measures the real ink width of
each glyph for a future VWF.

### TIM2 — `znt/tim2.py`
Minimal TIM2 reader (4bpp/8bpp indexed) with grayscale PNG dump, stdlib only.

### The engine — `docs/engine_api.md`
The scripts are **Squirrel source** (SqPlus bindings, confirmed in the ELF).
`znt/scriptscan.py` maps the API: it separates definitions from calls over the
1920 scenes and cross-references the candidate natives with the ELF strings.
Result: 36 global natives (35 confirmed), `Layer`/`MessageWindow` classes, and the
whole animation library that runs script-side. See the full catalogue.

## Layout

```
znt/            the SDK (importable package, stdlib)
  # layer 2 — data access
  container.py  .HD/.BIN pair + Container class (repack)
  codec.py      decompress (from the ELF) + compress_store
  tim2.py       TIM2 reader -> PNG/RGBA + Texture class (CLUT de-swizzle)
  font.py       BMP atlas + mapping  + Font class
  scriptscan.py scanner of the engine's Squirrel API (layer 2b)
  __init__.py   znt.open() -> Disc.scenes / .textures / .font
  __main__.py   unified CLI (python -m znt <group> ...)
  # layer 1 — off-console runtime
  render.py     Layer/MessageWindow + compositor to PNG
  sqparse.py    Squirrel tokenizer + Pratt parser
  sqtranspile.py  Squirrel AST -> Python
  sqrt.py       runtime for the transpiled code (objects, coroutines)
  sqrun.py      runs a real scene and emits frames
  engine.py     headless live runtime (animation + scene coroutine)
  frontends.py  headless engine frontend: APNG export
  # VN creation framework (headless)
  image.py      stdlib PNG reader -> RGBA rows (own assets)
  psf.py        console .psf fonts (baked into the PS2 blob)
  vniso.py      .vn -> .vnp v5 blob (header + on-demand data) and bootable ISO
  adpcm.py      WAV -> SPU2 ADPCM (the blob's `se`)
  vnstudio.py   VNRuntime: plays an authoring model with the real render/animation
  # layer 3 — authoring
  vn.py         .vn DSL -> HTML player + model ops (validate/rename/...)
  gui/          INTERACTIVE FRONTEND (tkinter) — optional, deletable, the core does not import it
    studio.py     VN Studio: graphical editor
    testbench.py  test bench (injects live animation)
    window.py     live window (play)
docs/engine_api.md   catalogue of the engine API (layer 2b)
docs/authoring.md    .vn format for creating a VN (layer 3)
research/codec_search.py   automated codec search (negative result)
```

One self-check per module, without depending on the game: `python3 -m znt demo` (16/16).

**Separable headless core.** The whole `znt` package is headless except `znt/gui/`
(the tkinter frontend). You can **delete `znt/gui/` entirely** and the core keeps
working: data access, codec, render, transpiler, runtime, `record` to APNG and the
VN `VNRuntime`. `znt demo` reports it and the `play`/`testbench`/`studio` commands
warn if the frontend is missing. No core module imports `gui` or `tkinter`.

## VN Studio — graphical editor (`python -m znt studio [project.vn]`)

Runs the real engine; edits a `.vn` project:

- Scenes and steps (`bg`/`show`/`hide`/`say`/`animate`/`choice`/`goto`/`end`):
  add, duplicate, reorder, delete; rename/reorder scenes.
- Sprites: assign a PNG per character, **drag on the stage** with **snap +
  guides** (centre/presets/floor/other sprites; Shift = free).
- Per layer: **Z order** (front/back), **zoom**, **opacity**, **tint**.
- **Transition preview** (▶ try) without entering Play; **Play** runs the scene
  with real animation; **undo/redo** (Ctrl+Z/Y).
- **Validate** the project (gotos/characters/dead-ends/assets), **asset
  library** (double-click assigns), **Save .vn** / **Export** to HTML player.

Testable model logic in `vn.py` (`validate`/`rename_character`/
`duplicate_scene`/`move_scene`/`list_assets`); the `VNRuntime` runtime is headless.

### In the browser (`python -m znt web [project.vn]`)

```sh
python -m znt web story.vn               # open
python -m znt web story.vn --restart     # stop whichever one is running and start this one
python -m znt web --stop                 # just stop it
python -m znt web story.vn --port 8790 --no-browser
```

`--restart` is the way out when an old server was left running: it finds it
(pidfile or process sweep), stops it and takes the port. Without `--restart`, if
the port is busy it uses the next free one and says so.

Same editor without tkinter: the (stdlib) server is the source of truth — it runs
the real `VNRuntime` and describes the layout; the browser composes it with CSS in
% (rescales with the window on its own) and animations arrive as APNG from the
engine.

Editing-app layout: toolbar, **outliner** (scenes + the step's layers, front
first), centred **viewport** with letterbox, selection frame with handles
(dragging a corner = zoom) and guides (centre / thirds / safe zone), **inspector**
with collapsible sections and draggable numeric fields (Shift = fine), **timeline**
with one track per step type, ruler, playhead, scrub and drag-to-reorder
(Ctrl+wheel = zoom), and a status bar. The three panels are resizable and the
size is remembered.

Shortcuts: Space (Play/advance), Esc, ←/→, Del, G (guides), Ctrl+Z/Y/S, **?**
(full list). New/open/character/scene use their own dialogs.

**Play** starts at the selected step (everything before it stays applied) and
goes **step by step**: each click on the screen runs the next step (background,
character, dialogue…) — or a whole **group** (Ctrl+G over several steps:
`group intro … endgroup` in the .vn) —, and the timeline follows the runtime: the
clip being played is highlighted and if a choice/goto jumps to another scene, the
timeline switches with it. Clicking a clip during Play = play from there. The rest
of the UI is switched off meanwhile; Esc or ⏹ goes back to editing.

Features: **Z order**, and editing the character's id/name/colour in the
Character section of the inspector (the only place where it is chosen and edited).

**Every field that points to a file has its 📁 button**: open, save as, export,
sprite, background and audio. It opens a browser of the server's disk (with
breadcrumbs, ↑, ⌂ and a filter by type) and, for assets, also lets you upload one
from the system dialog; the chosen file is copied next to the `.vn`.

`znt/web/` is optional just like `znt/gui/`: it can be deleted and the core keeps working.
