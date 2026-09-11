# Building the ELF and running the VN on PS2 (PCSX2)

Guide to the **first** build of the native player (`ps2/`) and to trying a VN in
the emulator. Requires the **ps2dev** toolchain; the Python SDK builds the blob and
the ISO. See the status and notes of the ELF in [`ps2/README.md`](../ps2/README.md).

## 0. Verify without a PS2 (quick)

The blob reader is correct and is tested on the host, without a toolchain:

```sh
python3 -m znt iso build story.vn game.vnp           # compiles the blob
cd ps2 && make host && ./test_vnp ../game.vnp        # -> "C READER OK"
```

## 1. ps2dev toolchain (Docker)

The simplest option is the official image (ships PS2SDK, gsKit, audsrv):

```sh
cd ~/Projects/ps2-znt-gamedev-tools
ps2/build.sh            # docker run … ps2dev/ps2dev (installs make in the container) -> ps2/ZNTVN.ELF
```

With ps2dev installed locally (`$PS2DEV`, `$PS2SDK`, `$PS2DEV/bin` on the PATH):
`cd ps2 && make`.

> If the link fails on audsrv/gsKit, check that the image has them (`ls
> $PS2SDK/ports/lib`). Audio loads `freesd.irx`+`audsrv.irx` in `audio_init()`:
> adjust that `SifLoadModule` to your environment (see `ps2/README.md`).

## 2. Prepare the data

```sh
python3 -m znt iso build story.vn game.vnp           # just the blob (with auto font)
```

For PS2 the BGM should be **PCM WAV** (ogg/mp3 are not decoded on the console).
`--font path.psf` picks the font; `--no-font` leaves it out.

## 3. Try it in PCSX2

### A) Quick — Run ELF + host filesystem
1. Copy the blob as `ZNTVN.VNP` **next to** `ZNTVN.ELF` (the player looks for
   `host:ZNTVN.VNP`).
2. In PCSX2, enable the *Host filesystem* and **Run ELF** → `ps2/ZNTVN.ELF`.
   (`host:` support varies by PCSX2 version; if it does not pick it up, use the ISO.)

### B) Robust — boot an ISO
```sh
python3 -m znt iso build story.vn story.iso --elf ps2/ZNTVN.ELF --name ZNTVN
```
Load `story.iso` in PCSX2 and start it. This path does not depend on the host fs.

## 4. On a real PS2 (optional)

Console with **FreeMcBoot**: boot the ISO via **OPL** (USB/HDD) or via **DVD-R**
through **ESR**. Without mods it does not boot (same as any homebrew). See
[`docs/spike-ps2-iso.md`](spike-ps2-iso.md).

## 5. Iterate

*Our* part (format, reader, font, animation math) is verified on the host; what
usually needs adjusting on the first build is the glue marked `/*GSKIT*/`
(sprites/atlas/mode) and `/*AUDIO*/` (module loading, audsrv format). Edit
`ps2/main.c`, rebuild (step 1) and go back to PCSX2.

Automated verification: `tests/pcsx2_boot.sh` (boot by log) and `tests/checklist.sh`
(the whole plan in `docs/checklist.md` in order, with build + boot + the features VN).
