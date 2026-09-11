# Checklist to close VN Studio and the PS2 player

Every item has its automated check in `tests/checklist.sh`, which runs them **in
order** and stops at the first one that fails. Mark `[x]` only when the check passes. Status: **18 checks green** (2026-09-09). The numbering goes up to 19
because item 10 became the runner itself.

## VN Studio
- [x] 1. Groups (Ctrl+G): the `grupos` QA flow passes and the work is committed.
- [x] 9. `docs/authoring.md` documents every op of the parser.

## PS2 player
- [x] 2. Toolchain: `docker run ps2dev/ps2dev make` produces `ps2/ZNTVN.ELF`.
- [x] 3. Boot: the ELF starts in PCSX2 with a minimal blob (`host:ZNTVN.VNP`).
- [x] 4. Memory: the ELF does not load the whole blob; images on demand (fseek).
- [x] 5. Background fade: `bg X fade=ms` travels in the blob (v5) and the ELF crossfades.
- [x] 6. Tween on `y`: `animate move y=` travels in the blob and the ELF interpolates it.
- [x] 7. Typing: the ELF reveals the text over time; the first click completes it.
- [x] 8. SE: effects via ADPCM (`audsrv_load_adpcm`), WAV→VAG encoder in the SDK.
- [x] 11. BGM: the audio thread feeds the PCM stream (priority + single-thread audsrv).
- [x] 12. Bootable ISO: starts from the CD and reads at more than 1 MB/s (sector-aligned data).
- [x] 13. Branching verified without a joystick: choice, goto between scenes and end (autoplay).
- [x] 14. Dialogue text wraps by word, not mid-word (`ps2/text.c`).
- [x] 15. 8-bit textures with palette when nothing is lost (4x less VRAM and disk).
- [x] 16. Editor Play with both paces: step by step and as the player.
- [x] 17. Save format with magic, version and CRC (survives a half-written file).
- [x] 18. Save and load on the memory card, resuming mid-scene.
- [x] 19. Pause menu (Start), dialogue history (Select) and fast-forward (Triangle).

## What is left (outside this checklist)

None of this blocks publishing a VN; these are the loose ends at the close of the checklist.

- **Real console.** Everything was verified in PCSX2. The ISO still has to boot on
  a PS2 with FreeMcBoot (OPL via USB/HDD, or DVD-R via ESR).
- **A single save slot.** Enough for "continue where I left off"; several named,
  dated saves are separate work.
- **Painted backgrounds in RGBA32.** Quantisation to 256 colours only kicks in when
  it loses nothing. A gradient or a painted background takes 4x more; with
  *dithering* it would fit in 8 bits without visible banding.
- **Editor.** Light theme and UI scaling, UI translation, dragging files onto the
  stage, shortcuts per step type.
- **Layer 1, running the original game off-console.** It is the other half of the
  repo and is still incomplete: the engine's animation modules (`LayerModule`),
  audio and input. It is a project in itself, not a short to-do.

## How to run
```sh
tests/checklist.sh            # everything, in order
tests/checklist.sh 4          # only from item 4
```
