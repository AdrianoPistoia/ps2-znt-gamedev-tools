# Compilar el ELF y correr la VN en PS2 (PCSX2)

Guía de la **primera** compilación del player nativo (`ps2/`) y de cómo probar una
VN en el emulador. Requiere la toolchain **ps2dev**; el SDK Python arma el blob y
el ISO. Ver el estado y las notas del ELF en [`ps2/README.md`](../ps2/README.md).

## 0. Verificar sin PS2 (rápido)

El lector del blob es correcto y se prueba en el host, sin toolchain:

```sh
python3 -m znt iso build historia.vn game.vnp        # compila el blob
cd ps2 && make host && ./test_vnp ../game.vnp        # -> "C READER OK"
```

## 1. Toolchain ps2dev (Docker)

Lo más simple es la imagen oficial (trae PS2SDK, gsKit, audsrv):

```sh
cd ~/Projects/ps2-znt-gamedev-tools
ps2/build.sh            # docker run … ps2dev/ps2dev (instala make en el contenedor) -> ps2/ZNTVN.ELF
```

Con ps2dev instalado local (`$PS2DEV`, `$PS2SDK`, `$PS2DEV/bin` en el PATH):
`cd ps2 && make`.

> Si el link falla por audsrv/gsKit, revisá que la imagen los tenga (`ls
> $PS2SDK/ports/lib`). El audio carga `freesd.irx`+`audsrv.irx` en `audio_init()`:
> ajustá ese `SifLoadModule` a tu entorno (ver `ps2/README.md`).

## 2. Preparar los datos

```sh
python3 -m znt iso build historia.vn game.vnp        # sólo el blob (con fuente auto)
```

Para PS2 el BGM conviene en **WAV PCM** (ogg/mp3 no se decodifican en consola).
`--font ruta.psf` elige la fuente; `--no-font` la omite.

## 3. Probar en PCSX2

### A) Rápido — Run ELF + host filesystem
1. Copiá el blob como `ZNTVN.VNP` **al lado** de `ZNTVN.ELF` (el player busca
   `host:ZNTVN.VNP`).
2. En PCSX2, activá el *Host filesystem* y **Run ELF** → `ps2/ZNTVN.ELF`.
   (El soporte de `host:` varía por versión de PCSX2; si no toma, usá el ISO.)

### B) Robusto — bootear un ISO
```sh
python3 -m znt iso build historia.vn historia.iso --elf ps2/ZNTVN.ELF --name ZNTVN
```
Cargá `historia.iso` en PCSX2 y arrancá. Este camino no depende del host fs.

## 4. En una PS2 real (opcional)

Consola con **FreeMcBoot**: bootear el ISO por **OPL** (USB/HDD) o por **DVD-R**
vía **ESR**. Sin mods no bootea (igual que cualquier homebrew). Ver
[`docs/spike-ps2-iso.md`](spike-ps2-iso.md).

## 5. Iterar

Lo *nuestro* (formato, lector, fuente, math de animación) está verificado en el
host; lo que suele necesitar ajuste al primer build es el glue marcado `/*GSKIT*/`
(sprites/atlas/mode) y `/*AUDIO*/` (carga de módulos, formato audsrv). Editás
`ps2/main.c`, recompilás (paso 1) y volvés a PCSX2.

Verificación automática: `tests/pcsx2_boot.sh` (boot por log) y `tests/checklist.sh`
(todo el plan de `docs/checklist.md` en orden, con build + boot + VN de features).
