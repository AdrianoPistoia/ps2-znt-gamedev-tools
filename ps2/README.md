# ELF player VN para PS2 (camino C del spike)

Reproduce en PS2 una VN autoral compilada a blob `.vnp` (`znt iso build`). Es la
pieza nativa: lo demás (autoría, compilación del blob, masterizado del ISO) está
en el SDK Python.

## Estado

**Compila y bootea en PCSX2** (`ps2/build.sh` con la imagen docker `ps2dev/ps2dev`;
`tests/pcsx2_boot.sh` lo bootea y verifica por el log; `ZNT_SHOT=x.png` captura).

- **`vnp.c`** (lector del blob v5): verificado en host (`tests/py/mkblob.py` + `make host`).
  Carga **sólo la cabecera** (~2 KB); imágenes y audio se leen por demanda con `fseek`.
- **`main.c`** (gsKit + audsrv): fondo sólido/degradé/imagen con **crossfade** (`fade=`),
  sprites RGBA32 con alfa (Z, zoom, opacidad), **tween en x/y** con curvas y las 6
  acciones, caja de diálogo, **texto UTF-8 con tipeo** (40 cps; X completa, X avanza),
  choices con el pad, **BGM** WAV/PCM por chunks (loop, corta al cambiar) y **SE por
  ADPCM** en canales de la SPU2 (`audsrv_load_adpcm`, el SDK lo convierte al compilar).
- VRAM: un solo framebuffer y sin Z → ~3 MB para texturas (fondo 640x448 = 1.1 MB).
  Pendiente: cuantizar a 8 bpp (CLUT) para escenas con muchos sprites.
- Sin probar en consola real. Sin saves/menú/skip/log de texto.

La **fuente** se hornea en el blob desde un `.psf` de consola (`znt iso build` la
autodetecta; `--font ruta.psf` para elegirla, `--no-font` para omitirla). Solo se
embeben los glifos que la VN usa. La licencia de la fuente elegida viaja con el
`.vnp`, no con este repo.

## Build (con ps2dev)

Toolchain [ps2dev](https://github.com/ps2dev/ps2dev). Vía Docker:

```sh
docker run --rm -v "$PWD:/src" -w /src/ps2 ps2dev/ps2dev sh -c 'make'
# -> ZNTVN.ELF
```

O con ps2dev instalado local (`$PS2SDK`, `$PS2DEV/bin` en el PATH): `cd ps2 && make`.

## Probar en PCSX2

1. Compilá una VN a blob:  `python3 -m znt iso build historia.vn out.vnp`  (sin `--elf`).
2. Renombralo `ZNTVN.VNP` y ponelo donde el ELF lo busque:
   - **host fs** (lo más rápido en PCSX2): al lado del ELF; PCSX2 con *Host filesystem* activo → `host:ZNTVN.VNP`.
   - o dentro de un ISO:  `python3 -m znt iso build historia.vn historia.iso --elf ZNTVN.ELF`  y corré el ISO.
3. En PCSX2: **Run ELF** (`ZNTVN.ELF`) o bootear el ISO.

En consola real (PS2 modeada con FreeMcBoot): bootear el ISO por OPL (USB/HDD) o
por DVD-R vía ESR. Ver `docs/spike-ps2-iso.md`.

## Archivos

- `vnp.h` / `vnp.c` — lector del blob (espejo de `znt/vniso.py`).
- `main.c` — init gsKit, carga del blob, intérprete de escena, render, pad.
- `test_vnp_host.c` — test del lector en el host (`make host`).
- `Makefile` — build del ELF (PS2SDK) y del test host.
