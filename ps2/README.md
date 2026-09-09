# ELF player VN para PS2 (camino C del spike)

Reproduce en PS2 una VN autoral compilada a blob `.vnp` (`znt iso build`). Es la
pieza nativa: lo demás (autoría, compilación del blob, masterizado del ISO) está
en el SDK Python.

## Estado

**Compila y bootea**, tanto por `Run ELF` como desde un **ISO** masterizado
(`ps2/build.sh` con la imagen docker `ps2dev/ps2dev`; `tests/pcsx2_boot.sh` lo bootea
y verifica por el log, `ZNT_ISO=x.iso` usa el ISO y `ZNT_SHOT=x.png` saca la foto).

- **`vnp.c`** (lector del blob v5): verificado en host. Carga **sólo la cabecera**;
  imágenes y audio se leen por demanda, alineados al sector (**1.4 MB/s** desde el
  DVD; con lecturas sin alinear eran 166 KB/s y un fondo tardaba 6.7 s).
- **Imagen**: fondo sólido, degradé o textura, con **crossfade** (`fade=`); sprites
  con alfa, orden Z, zoom, opacidad y **tinte**. Las texturas van en **8 bits con
  paleta** cuando la imagen entra en 256 colores exactos (4x menos VRAM y disco); un
  degradé pintado se queda en RGBA32 para no producir bandas.
- **Animación**: tween en x/y con curvas y las seis acciones (`wave`, `jump`, `fall`…).
- **Texto**: UTF-8 con la fuente horneada, **corte por palabra** y **tipeo** a 40 cps
  (X completa la línea, la siguiente X avanza).
- **Elecciones** con el pad, saltos entre escenas y final, verificados sin joystick
  con el modo `autoplay`.
- **Audio**: BGM en WAV/PCM por streaming (loop, corta al cambiar) y **efectos en
  ADPCM** en canales de la SPU2, que suenan encima de la música.
- **Partidas**: Start abre el menú (Seguir / Guardar / Cargar); se guarda escena,
  paso y música en la memory card, y al cargar se rehace la escena hasta ese paso.
  Select muestra el **historial** de diálogos y Triángulo **saltea** texto rápido.

Pendiente: probarlo en una consola real (sólo corrió en PCSX2).

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
