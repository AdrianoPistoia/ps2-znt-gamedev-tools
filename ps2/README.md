# ELF player VN para PS2 (camino C del spike)

Reproduce en PS2 una VN autoral compilada a blob `.vnp` (`znt iso build`). Es la
pieza nativa: lo demás (autoría, compilación del blob, masterizado del ISO) está
en el SDK Python.

## Estado

- **`vnp.c` (lector del blob): verificado** — compila en el host y parsea correctamente
  un blob generado por `znt.vniso` (`make host && ./test_vnp <blob.vnp>` → `C READER OK`).
- **`main.c` (gsKit): sin compilar en este entorno (sin toolchain).** Cubre fondo
  (solid/grad/img), sprites (Z, zoom, opacidad), caja de diálogo, **texto con fuente
  (nombre + diálogo + opciones, UTF-8, acentos)** desde el atlas horneado en el blob,
  avance y choices con el pad. Los puntos `/*GSKIT*/` pueden necesitar ajustes según
  tu versión de gsKit. **Falta:** animación por tiempo (curvas/acciones) y audio (SPU2).

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
