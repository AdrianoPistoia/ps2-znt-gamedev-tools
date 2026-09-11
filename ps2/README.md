# VN player ELF for PS2 (path C of the spike)

Plays on PS2 an authored VN compiled to a `.vnp` blob (`znt iso build`). It is the
native piece: everything else (authoring, blob compilation, ISO mastering) lives
in the Python SDK.

## Status

**Builds and boots**, both via `Run ELF` and from a mastered **ISO**
(`ps2/build.sh` with the `ps2dev/ps2dev` docker image; `tests/pcsx2_boot.sh` boots it
and verifies through the log, `ZNT_ISO=x.iso` uses the ISO and `ZNT_SHOT=x.png` takes the screenshot).

- **`vnp.c`** (v5 blob reader): verified on the host. Loads **only the header**;
  images and audio are read on demand, sector-aligned (**1.4 MB/s** from the
  DVD; with unaligned reads it was 166 KB/s and a background took 6.7 s).
- **Image**: solid, gradient or texture background, with **crossfade** (`fade=`); sprites
  with alpha, Z order, zoom, opacity and **tint**. Textures go as **8-bit with
  palette** when the image fits in 256 exact colours (4x less VRAM and disk); a
  painted gradient stays RGBA32 to avoid banding.
- **Animation**: tween on x/y with curves and the six actions (`wave`, `jump`, `fall`…).
- **Text**: UTF-8 with the baked font, **word wrap** and **typing** at 40 cps
  (X completes the line, the next X advances).
- **Choices** with the pad, jumps between scenes and end, verified without a joystick
  with the `autoplay` mode.
- **Audio**: streamed WAV/PCM BGM (loops, cuts on change) and **ADPCM effects**
  on SPU2 channels, which play on top of the music.
- **Saves**: Start opens the menu (Resume / Save / Load); scene, step and music
  are saved to the memory card, and on load the scene is replayed up to that step.
  Select shows the dialogue **history** and Triangle **skips** text fast.

Pending: trying it on a real console (it only ran in PCSX2).

The **font** is baked into the blob from a console `.psf` (`znt iso build`
autodetects it; `--font path.psf` to pick it, `--no-font` to leave it out). Only
the glyphs the VN uses are embedded. The licence of the chosen font travels with the
`.vnp`, not with this repo.

## Build (with ps2dev)

[ps2dev](https://github.com/ps2dev/ps2dev) toolchain. Via Docker:

```sh
docker run --rm -v "$PWD:/src" -w /src/ps2 ps2dev/ps2dev sh -c 'make'
# -> ZNTVN.ELF
```

Or with ps2dev installed locally (`$PS2SDK`, `$PS2DEV/bin` on the PATH): `cd ps2 && make`.

## Try it in PCSX2

1. Compile a VN to a blob:  `python3 -m znt iso build story.vn out.vnp`  (without `--elf`).
2. Rename it `ZNTVN.VNP` and put it where the ELF looks for it:
   - **host fs** (fastest in PCSX2): next to the ELF; PCSX2 with *Host filesystem* enabled → `host:ZNTVN.VNP`.
   - or inside an ISO:  `python3 -m znt iso build story.vn story.iso --elf ZNTVN.ELF`  and run the ISO.
3. In PCSX2: **Run ELF** (`ZNTVN.ELF`) or boot the ISO.

On a real console (modded PS2 with FreeMcBoot): boot the ISO via OPL (USB/HDD) or
via DVD-R through ESR. See `docs/spike-ps2-iso.md`.

## Files

- `vnp.h` / `vnp.c` — blob reader (mirror of `znt/vniso.py`).
- `main.c` — gsKit init, blob loading, scene interpreter, render, pad.
- `test_vnp_host.c` — host test of the reader (`make host`).
- `Makefile` — build of the ELF (PS2SDK) and of the host test.
