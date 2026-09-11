# Spike — producing a PS2-bootable `.iso` from an authored VN

**Question:** can this project produce a `.iso` that runs in a PS2 emulator
(PCSX2) and plays a VN created in VN Studio?

**Short answer:** yes, it is possible, and **de-risked in parts** by what we have
already reversed — but the stretch "an ELF comes out and boots" is a separate
**PS2 homebrew** project, not a small extension of the exporter. There are three
paths; the recommended one is a **minimal homebrew ELF** that interprets our `.vn`.
Estimate for the recommended path up to "a real scene boots in PCSX2":
**~1 week** to proof-of-life, **~4–8 weeks** to a usable player.

> Spike = bounded research. It implements nothing; it fixes scope, risks and the
> first experiment to run.

---

## What we ALREADY have (foundations, whatever the path)

- Game formats solved: `.HD/.BIN` container, codec (decode + `compress_store`),
  TIM2 (decode to RGBA), BMP font + mapping. (layer 2)
- The engine API mapped (`docs/engine_api.md`) and 1920 scenes that parse/transpile.
- The **runtime model** (bg + layers + animation by curves/actions + dialogue +
  choices + bgm/se) already specified and with a headless reference implementation
  (`VNRuntime`) — it serves as the **spec** for porting it to PS2.
- The `.vn` authoring format and its compilation.

## What is MISSING (new pieces, per path)

| Piece | New? | Notes |
|---|---|---|
| **Homebrew ELF** (2D GS + input + data reading) | **yes, large** | PS2SDK/ps2dev; gsKit for blits; libpad; cdvd/isofs |
| **Texture encoder** | depends | Path A: **TIM2 encoder** with palette quantisation. B/C: upload **32-bit RGBA** to the GS → no quantisation in the 1st version |
| **Font with accents** | yes | draw Latin/accented glyphs + mapping (shared with the translation) |
| **ISO9660 mastering** | yes, small | `genisoimage` + `SYSTEM.CNF` pointing at the ELF |
| **Audio (SPU2 / bgm-se)** | yes | play ADPCM through the SPU2; the game's `SOUND_ID` format is not reversed → **deferrable** |
| **Scene interpreter on PS2** | yes | Path A: emit the engine's Squirrel. B/C: own interpreter of the compiled `.vn` |

---

## The three paths

### A. Reuse the game as a shell (repack into the ZnT engine)
Emit our scenes as **engine Squirrel** (using `set/talk/select/next` and the
`LayerModule` vocabulary), encode our images to **TIM2**, `compress_store`, and
remaster the game's ISO.

- **For:** the engine, boot, input and (part of the) audio **already work**.
- **Against:**
  - Needs a **TIM2 encoder** (quantisation to 256 colours + CLUT re-swizzle).
  - The font still has no accents (they have to be drawn — an open task of the translation).
  - **Legal:** the resulting ISO carries the ELF and the engine **of the copyrighted
    game**. Distributing original content inside the ZnT shell is murky and odd
    (your VN drags along ZnT's engine and brand). Only a **binary patch** over the
    user's copy is defensible, and this is not a patch: it is new content.
  - **Sector risk:** if the ELF reads files by absolute LBA (question 5 of the
    README, unconfirmed), changing sizes breaks the layout → the ISO has to be
    rebuilt and maybe the file table patched.
- **Verdict:** technical shortcut to "see something boot", **not recommended as a product**.

### B. Full PS2 homebrew (our engine in an ELF)
Port the runtime to a native ELF (C/C++ with PS2SDK): GS, input, ISO reading,
an interpreter (embedded Squirrel or our own), animation, audio, saves.

- **For:** clean origin (our code + the user's assets), no ZnT, own `.iso`,
  legally sound.
- **Against:** it is **a homebrew VN engine from scratch** — a whole discipline
  (GS, DMA, SPU2, memory). **Months.** HIGH complexity.
- **Verdict:** the "right path" long term, but big.

### C. MINIMAL homebrew ELF that interprets the `.vn` (recommended)
A small ELF that does **not** port the ZnT engine or a Squirrel VM: compile the
`.vn` to a compact binary blob and interpret it with just enough — bg + sprites +
text + choices + input. Animation/audio get added later.

- **For:**
  - **B/C need neither TIM2 nor quantisation** in the 1st version: the GS accepts
    **32-bit (PSMCT32)** textures directly → we upload RGBA (more memory, zero
    new algorithm). 8-bit quantisation is a later optimisation.
  - Reuses our scene model as spec; the `.vn`→blob is done by our SDK.
  - Legally clean.
  - **PCSX2 boots a `.elf` directly** (Run ELF) → iterate without mastering an
    ISO; the ISO is left as the last packaging step.
- **Against:** you still have to learn GS/gsKit/libpad and write PS2 C.
- **Verdict:** realistic route to "an original VN boots in PCSX2".

---

## Plan by stages (path C)

1. **Toolchain** — `ps2dev` image (docker) with `mips64r5900el-ps2-elf-gcc`, gsKit,
   libpad. *Low effort.*
2. **Proof-of-life ELF** — clear the screen, upload an RGBA texture and draw a
   string with a bitmap font; **boot in PCSX2** (Run ELF). *~days–1 week.*
3. **`.vn` → blob compiler** — in our SDK (Python): serialise scenes, characters,
   and an **asset atlas** (PNG→raw RGBA or TIM2). With self-check. *~days.*
4. **Minimal player (ELF)** — read the blob, compose bg+sprites (our Z model),
   text box + font with accents, `choice` with the pad, `goto/end`. *~weeks.*
5. **ISO mastering** — `SYSTEM.CNF` (`BOOT2 = cdrom0:\VN.ELF;1`) + `genisoimage`;
   test the `.iso` in PCSX2. *~days.*
6. **Afterwards:** animation (curves/actions already specified), SPU2 audio, saves.

**First experiment (1–2 days, maximum information):**
bring up `ps2dev`, build the gsKit sample that draws a sprite, **boot it in
PCSX2**, and in parallel write a **texture encoder** in the SDK (start with
RGBA→PSMCT32; validate the round-trip against our decoder). That confirms toolchain +
render + the asset bridge, which is 80% of the risk.

---

## Complexity and risk (summary)

| Dimension | A (ZnT shell) | B (full homebrew) | C (minimal ELF) |
|---|---|---|---|
| Effort to "something boots" | medium | high | **medium** |
| Effort to parity | medium-high | very high | high |
| Large new pieces | TIM2 encoder, font | whole engine | ELF + font (32-bit avoids quantising) |
| Legal | **problematic** | clean | **clean** |
| Technical risk | sectors/ISO, foreign engine | broad | bounded and staged |
| Reuses what exists | codec/TIM2/containers | scene model | **model + .vn + SDK** |

**Conclusion.** It is viable and worth it; the shortcut (A) is not advisable for
legal reasons and because it depends on someone else's engine. The goal — *your
original VN booting in PCSX2* — is best reached with **C**: a minimal homebrew ELF
that interprets the `.vn`, with the GS in 32-bit to skip quantisation at first, and
PCSX2 booting the ELF directly to iterate fast. The current SDK already covers the
authoring and data side; the new and large part is the PS2 ELF. Concrete next
step: the 1–2 day experiment above.
