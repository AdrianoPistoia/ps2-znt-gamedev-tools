#!/usr/bin/env python3
"""Compiles a `.vn` model into a **binary `.vnp` blob** that the PS2 ELF player
(path C of the spike) reads and runs. Headless and testable; the `read_blob` here
serves as verification and as the **spec** for the C reader.

Format (little-endian):

    "VNP1" | u16 version | u16 start_scene | u32 head_size
    -- string pool --   u32 N ; each: u16 len + UTF-8      (idx 0xFFFFFFFF = none)
    -- characters --    u32 N ; each: u32 name_str, u32 color_rgba, u16 sprite_img(0xFFFF none)
    -- images --        u32 N ; each: u16 w, u16 h, u8 fmt, u32 len, u32 off
                        fmt 0 = raw RGBA32; fmt 1 = 8bpp: 1024-byte CLUT (already in
                        GS order) + one byte per pixel. See znt/quant.py.
    -- font --          u8 has ; u16 cw, u16 ch, u32 n, n*u32 cps, 1bpp bitmap
    -- audio --         u32 N ; each: u32 name_str, u32 len, u32 off
    -- scenes --        u32 N ; each: u32 nsteps ; each step: u8 op + payload
    == head_size ==     from here on, the raw image and audio data (absolute off)

Every datum (and the header) starts at a multiple of **2048**, the DVD sector: the
cdvd driver reads whole sectors, and asking it for an unaligned span makes it spin
extra (166 KB/s measured in PCSX2 vs >1 MB/s aligned). The padding is zeros.

v5: the header is read on its own (`head_size`) and each image/audio is fetched on
demand via its `off`: the ELF does not load the whole blob into RAM. `bg` ends in a u16
fade (ms, 0 = cut); `anim` carries i16 x, i16 y (0x7FFF = not given: that coordinate is left alone).

Opcodes: 1 bg, 2 show, 3 hide, 4 say, 5 anim, 6 bgm, 7 se, 8 choice, 9 goto, 10 end.
v4: `show` carries u16 img (the expression's image; 0xFFFF = the character's base sprite).
(payloads: see `_emit_step` / `_read_step`). Audio: opcode with the file name,
no embedded data yet (deferred, see spike).
"""
import struct, os, shutil, subprocess, tempfile

from . import vn, image, psf, adpcm, quant

SYSTEM_CNF = "BOOT2 = cdrom0:\\{name}.ELF;1\r\nVER = 1.00\r\nVMODE = {vmode}\r\n"

MAGIC = b"VNP1"
OP = dict(bg=1, show=2, hide=3, say=4, anim=5, bgm=6, se=7, choice=8, goto=9, end=10)
IOP = {v: k for k, v in OP.items()}
# animation codes (curves + actions)
ANIM = {"linear": 0, "accel": 1, "decel": 2, "move": 3,
        "wave": 10, "waveonce": 11, "jump": 12, "jumponce": 13, "fall": 14, "vibrate": 15}
IANIM = {v: k for k, v in ANIM.items()}
NONE32 = 0xFFFFFFFF
NONE16 = 0xFFFF
NOCOORD = 0x7FFF                  # i16 "not given" in anim (x/y)
SECTOR = 2048                     # DVD sector: every datum starts at a multiple


def _up(n):
    """Rounds up to the sector."""
    return (n + SECTOR - 1) // SECTOR * SECTOR


def _rgba(hexs):
    h = (hexs or "").lstrip("#")
    if len(h) == 6:
        r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4))
        return (r << 24) | (g << 16) | (b << 8) | 0xFF
    return 0


class _W:
    def __init__(self): self.b = bytearray()
    def u8(self, v): self.b.append(v & 0xFF)
    def u16(self, v): self.b += struct.pack("<H", v & 0xFFFF)
    def i16(self, v): self.b += struct.pack("<h", int(v))
    def u32(self, v): self.b += struct.pack("<I", v & 0xFFFFFFFF)
    def blob(self, data): self.u32(len(data)); self.b += data


def _codepoints(model):
    """Every character the VN displays (dialogue, options, names) + ASCII."""
    cps = set(range(0x20, 0x7F))
    for c in model["characters"].values():
        cps |= set(ord(ch) for ch in c.get("name", ""))
    for steps in model["scenes"].values():
        for s in steps:
            if s["op"] == "say":
                cps |= set(ord(ch) for ch in s.get("text", ""))
            elif s["op"] == "choice":
                for o in s.get("options", []):
                    cps |= set(ord(ch) for ch in o["label"])
    return sorted(cps)


def bake_font(model, psf_path):
    """Bakes a 1bpp atlas with the glyphs the VN uses, from a .psf.
    Returns (cell_w, cell_h, sorted_cps, bitmap) or None if there is no font."""
    if not psf_path:
        return None
    f = psf.load(psf_path)
    blank = bytes(f.h * f.stride)
    qmark = f.glyphs.get(ord("?"), blank)
    cps = [cp for cp in _codepoints(model) if cp in f.glyphs] or [ord(" ")]
    data = bytearray()
    for cp in cps:
        data += f.glyphs.get(cp, qmark)
    return (f.w, f.h, cps, bytes(data))


def compile_blob(model, base=".", font=None, quantize="auto"):
    model = vn._link_choices(model) if any(
        s["op"] == "_option" for steps in model["scenes"].values() for s in steps) else model
    order = model["order"]
    scene_idx = {sid: i for i, sid in enumerate(order)}

    # --- string pool (dedup) ---
    pool, pidx = [], {}
    def S(s):
        if s is None: return NONE32
        if s not in pidx:
            pidx[s] = len(pool); pool.append(s)
        return pidx[s]

    # --- characters (without narrator) and index ---
    char_idx = {}
    chars = []
    for cid, c in model["characters"].items():
        if cid == "narrator":
            continue
        char_idx[cid] = len(chars); chars.append(c)

    # --- images (character sprites + img backgrounds) ---
    img_idx = {}
    images = []
    def IMG(fname):
        if not fname:
            return NONE16
        if fname not in img_idx:
            fmt = 0
            try:
                w, h, rows = image.load_png_file(f"{base}/{fname}")
                data = b"".join(rows)
            except Exception:
                w, h, data = 1, 1, b"\0\0\0\0"          # placeholder if missing
            # 8bpp when the CLUT pays for itself (w*h*4 > 1024 + w*h) and nothing is lost.
            # A painted gradient has thousands of colors: with 256 visible banding appears
            # even if the mean error is low, so that one stays RGBA32 (with aligned reads
            # it already loads fast). `quantize="always"` forces the saving anyway.
            if quantize and w * h * 3 > 1024 and (quantize == "always" or quant.is_lossless(data)):
                clut, idx = quant.quantize(w, h, data)
                fmt, data = 1, clut + idx
            img_idx[fname] = len(images); images.append((w, h, fmt, data))
        return img_idx[fname]

    for c in chars:
        c["_spr"] = IMG(c.get("sprite"))
    by_id = {cid: c for cid, c in model["characters"].items()}

    def expr_img(s):                                 # show with expression -> its image
        ex = s.get("expr")
        c = by_id.get(s.get("id"), {})
        f = (c.get("expr") or {}).get(ex) if ex else None
        return IMG(f) if f else NONE16

    # --- audio: bgm embeds the WAV as is (PCM stream); se goes as SPU2 ADPCM ---
    aud_idx = {}
    audios = []
    def AUD(fname, se=False):
        if not fname:
            return NONE16
        key = (fname, se)
        if key not in aud_idx:
            try:
                data = open(f"{base}/{fname}", "rb").read()
                if se:
                    data = adpcm.from_wav(data)
            except (OSError, ValueError):
                aud_idx[key] = NONE16; return NONE16     # missing or not PCM WAV: no audio
            aud_idx[key] = len(audios); audios.append((S(fname), data))  # name into the pool
        return aud_idx[key]

    S(model["title"])                                    # reserve the title as string 0

    # scene bodies first (fills the pool), then the pool is serialized at the end…
    # simpler: serialize in a fixed order, but the pool must be complete beforehand.
    # Strategy: pre-pass over everything to fill the pool, then emit unambiguously.
    for c in chars:
        S(c["name"])
    scene_bytes = []
    for sid in order:
        sw = _W(); steps = model["scenes"][sid]
        sw.u32(len(steps))
        for s in steps:
            _emit_step(sw, s, S, char_idx, scene_idx, IMG, AUD, expr_img)
        scene_bytes.append(bytes(sw.b))

    fnt = bake_font(model, font)
    datas = [d for _, _, _, d in images] + [d for _, d in audios]   # raw data, after the header

    def head(base):                                  # header with absolute offsets from `base`
        w = _W(); off = base
        w.b += MAGIC; w.u16(5); w.u16(scene_idx.get(model.get("start", order[0]), 0)); w.u32(base)
        w.u32(len(pool))
        for s in pool:
            enc = s.encode("utf-8"); w.u16(len(enc)); w.b += enc
        w.u32(len(chars))
        for c in chars:
            w.u32(pidx[c["name"]]); w.u32(_rgba(c.get("color"))); w.u16(c["_spr"])
        w.u32(len(images))
        for iw, ih, ifmt, data in images:
            w.u16(iw); w.u16(ih); w.u8(ifmt); w.u32(len(data)); w.u32(off); off += _up(len(data))
        if fnt:
            cw, ch, cps, fdata = fnt
            w.u8(1); w.u16(cw); w.u16(ch); w.u32(len(cps))
            for cp in cps:
                w.u32(cp)
            w.b += fdata
        else:
            w.u8(0)
        w.u32(len(audios))
        for name_str, data in audios:
            w.u32(name_str); w.u32(len(data)); w.u32(off); off += _up(len(data))
        w.u32(len(order))
        for sb in scene_bytes:
            w.b += sb
        return bytes(w.b)

    base = _up(len(head(0)))                         # the size does not depend on the offsets
    out = bytearray(head(base))
    out += b"\0" * (base - len(out))                  # padding up to the first data sector
    for d in datas:
        out += d; out += b"\0" * (_up(len(d)) - len(d))
    return bytes(out)


def build_iso(elf_path, blob_path, out_iso, name="VN", vmode="NTSC"):
    """Masters a bootable ISO9660: SYSTEM.CNF (BOOT2 -> {name}.ELF), the ELF and the
    .vnp blob. Requires `genisoimage`. UPPERCASE 8.3 names (iso-level 1)."""
    name = name.upper()[:8]
    stage = tempfile.mkdtemp()
    try:
        with open(f"{stage}/SYSTEM.CNF", "w", newline="") as f:
            f.write(SYSTEM_CNF.format(name=name, vmode=vmode))
        shutil.copyfile(elf_path, f"{stage}/{name}.ELF")
        shutil.copyfile(blob_path, f"{stage}/{name}.VNP")
        subprocess.run(
            ["genisoimage", "-quiet", "-iso-level", "1", "-sysid", "PLAYSTATION",
             "-V", name, "-o", out_iso, stage],
            check=True)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return out_iso


def _emit_step(w, s, S, char_idx, scene_idx, IMG, AUD, expr_img=lambda s: NONE16):
    op = s["op"]
    w.u8(OP["anim"] if op == "animate" else OP[op])
    if op == "bg":
        sp = s["spec"]
        if sp["kind"] == "solid":
            w.u8(0); w.u32(_rgba(sp["color"]))
        elif sp["kind"] == "grad":
            w.u8(1); w.u32(_rgba(sp["a"])); w.u32(_rgba(sp["b"]))
        else:
            w.u8(2); w.u16(IMG(sp.get("file")))
        w.u16(int(s.get("fade") or 0))              # v5: crossfade in ms
    elif op == "show":
        w.u16(char_idx.get(s["id"], NONE16))
        w.u16(expr_img(s))                          # v4: the expression's image (NONE = base)
        w.i16(s.get("x", vn.POS.get(s.get("pos"), 0)))     # preset left/center/right -> x
        w.i16(s.get("y", 0)); w.i16(s.get("z", 0))
        w.u16(int(s.get("zoom", 100))); w.u8(int(s.get("opacity", 100)))
        w.u32(_rgba(s["tint"]) if s.get("tint") else 0)
    elif op == "hide":
        w.u16(char_idx.get(s["id"], NONE16))
    elif op == "say":
        w.u16(char_idx.get(s.get("who"), NONE16)); w.u32(S(s.get("text", "")))
    elif op == "animate":
        p = s.get("params", {})
        w.u8(ANIM.get(s["kind"], 0))                     # curve-as-kind / move / action
        w.u8(ANIM.get(p.get("curve", "linear"), 0))      # curve (for move)
        w.i16(p.get("x", NOCOORD)); w.i16(p.get("y", NOCOORD))     # v5: y; 0x7FFF = not given
        w.u16(int(p.get("time", p.get("falltime", 0))))
        w.i16(p.get("vib", p.get("vibration", 0))); w.u16(int(p.get("cycle", 0)))
        w.i16(p.get("dist", p.get("distance", 0)))
    elif op == "bgm":
        w.u8(1 if s.get("stop") else 0); w.u16(AUD(s.get("file")))
    elif op == "se":
        w.u16(AUD(s.get("file"), se=True))
    elif op == "choice":
        opts = s.get("options", []); w.u8(len(opts))
        for o in opts:
            w.u32(S(o["label"])); w.u16(scene_idx.get(o["target"], NONE16))
    elif op == "goto":
        w.u16(scene_idx.get(s["target"], NONE16))
    elif op == "end":
        pass


# --- verification reader (and spec for the C reader) ------------------------
class _R:
    def __init__(self, b): self.b = b; self.o = 0
    def u8(self): v = self.b[self.o]; self.o += 1; return v
    def u16(self): v = struct.unpack_from("<H", self.b, self.o)[0]; self.o += 2; return v
    def i16(self): v = struct.unpack_from("<h", self.b, self.o)[0]; self.o += 2; return v
    def u32(self): v = struct.unpack_from("<I", self.b, self.o)[0]; self.o += 4; return v
    def take(self, n): d = self.b[self.o:self.o+n]; self.o += n; return d


def read_blob(data):
    r = _R(data)
    assert r.take(4) == MAGIC, "not a VNP"
    version = r.u16(); start = r.u16(); head_size = r.u32()
    pool = []
    for _ in range(r.u32()):
        n = r.u16(); pool.append(r.take(n).decode("utf-8"))
    def S(i): return None if i == NONE32 else pool[i]
    chars = []
    for _ in range(r.u32()):
        chars.append(dict(name=S(r.u32()), color=r.u32(), sprite=r.u16()))
    images = []
    for _ in range(r.u32()):
        iw = r.u16(); ih = r.u16(); ifmt = r.u8(); ln = r.u32(); images.append((iw, ih, r.u32(), ln, ifmt))
    font = None
    if r.u8():
        cw = r.u16(); ch = r.u16(); n = r.u32()
        cps = [r.u32() for _ in range(n)]
        stride = (cw + 7) // 8
        r.take(n * ch * stride)
        font = {"cell": (cw, ch), "cps": cps}
    audios = []
    for _ in range(r.u32()):
        nm = S(r.u32()); alen = r.u32(); audios.append((nm, alen, r.u32()))
    scenes = []
    for _ in range(r.u32()):
        steps = [_read_step(r, S) for _ in range(r.u32())]
        scenes.append(steps)
    return dict(version=version, start=start, head_size=head_size, title=pool[0] if pool else None,
                characters=chars, images=images, font=font, audios=audios, scenes=scenes)


def _read_step(r, S):
    op = IOP[r.u8()]
    if op == "bg":
        k = r.u8()
        if k == 0: d = {"op": "bg", "kind": "solid", "color": r.u32()}
        elif k == 1: d = {"op": "bg", "kind": "grad", "a": r.u32(), "b": r.u32()}
        else: d = {"op": "bg", "kind": "img", "img": r.u16()}
        d["fade"] = r.u16(); return d
    if op == "show":
        return {"op": "show", "id": r.u16(), "img": r.u16(), "x": r.i16(), "y": r.i16(), "z": r.i16(),
                "zoom": r.u16(), "opacity": r.u8(), "tint": r.u32()}
    if op == "hide":
        return {"op": "hide", "id": r.u16()}
    if op == "say":
        return {"op": "say", "who": r.u16(), "text": S(r.u32())}
    if op == "anim":
        kind = IANIM.get(r.u8(), "linear"); curve = IANIM.get(r.u8(), "linear")
        x = r.i16(); y = r.i16()
        return {"op": "animate", "kind": kind, "curve": curve,
                "x": None if x == NOCOORD else x, "y": None if y == NOCOORD else y,
                "time": r.u16(), "vib": r.i16(), "cycle": r.u16(), "dist": r.i16()}
    if op == "bgm":
        return {"op": "bgm", "stop": r.u8(), "audio": r.u16()}
    if op == "se":
        return {"op": "se", "audio": r.u16()}
    if op == "choice":
        n = r.u8()
        return {"op": "choice", "options": [{"label": S(r.u32()), "target": r.u16()} for _ in range(n)]}
    if op == "goto":
        return {"op": "goto", "target": r.u16()}
    return {"op": op}


def build(vn_path, out, elf=None, name="VN", font="auto"):
    """Compiles a .vn to a blob; if an ELF is given, masters the bootable .iso.
    Without an ELF, writes only the .vnp blob (to test the pipeline). `font`: path to a
    .psf, "auto" (detects a system one) or None (no text)."""
    if font == "auto":
        font = psf.find_default()
    text = open(vn_path, encoding="utf-8").read()
    model = vn._link_choices(vn.parse(text))
    blob = compile_blob(model, os.path.dirname(os.path.abspath(vn_path)), font=font)
    if font:
        print(f"baked font: {os.path.basename(font)}")
    if elf:
        tmp = out + ".vnp.tmp"
        open(tmp, "wb").write(blob)
        try:
            build_iso(elf, tmp, out, name=name)
        finally:
            os.remove(tmp)
        print(f"bootable ISO -> {out}  ({len(blob)} bytes of data, ELF {os.path.basename(elf)})")
    else:
        vnp = out if out.lower().endswith(".vnp") else out + ".vnp"
        open(vnp, "wb").write(blob)
        print(f"blob -> {vnp} ({len(blob)} bytes). Pass --elf <player.elf> to master the .iso.")
    return out


def cli(argv):
    if not argv or argv[0] == "demo":
        return demo()
    if argv[0] == "build":
        a = argv[1:]; elf = name = None; font = "auto"
        pos = []
        it = iter(a)
        for x in it:
            if x == "--elf": elf = next(it)
            elif x == "--name": name = next(it)
            elif x == "--font": font = next(it)
            elif x == "--no-font": font = None
            else: pos.append(x)
        return build(pos[0], pos[1], elf=elf, name=name or "VN", font=font)
    print(__doc__)


def demo():
    m = vn._link_choices(vn.parse(
        'title: T\ncharacter a "Ana" color=#e79ab0\n'
        'scene uno\n  bg grad:#101828,#304060\n  show a right x=40 z=5 zoom=150 opacity=80\n'
        '  a: Hola.\n  choice\n    - Seguir -> dos\n    - Fin -> dos\n'
        'scene dos\n  * chau\n  end\n'))
    r = read_blob(compile_blob(m))
    assert r["title"] == "T" and r["start"] == 0
    sh = r["scenes"][0][1]
    assert sh["op"] == "show" and sh["x"] == 40 and sh["z"] == 5 and sh["zoom"] == 150 and sh["opacity"] == 80
    assert r["scenes"][0][2]["text"] == "Hola."
    ch = r["scenes"][0][3]
    assert len(ch["options"]) == 2 and ch["options"][0]["target"] == 1
    assert r["scenes"][1][-1]["op"] == "end"
    # animate + real embedded image (round-trip)
    import tempfile, os, struct, zlib
    d = tempfile.mkdtemp()
    px = bytes((10, 20, 30, 255)) * (2 * 2)              # PNG RGBA 2x2
    raw = b"".join(b"\0" + px[y*8:(y+1)*8] for y in range(2))
    chunk = lambda t, b: struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b))
    open(f"{d}/s.png", "wb").write(
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    m2 = vn._link_choices(vn.parse('title: t\ncharacter h "H" color=#fff\nsprite h s.png\n'
                                   'scene s\n  show h center\n  animate h move x=200 curve=accel time=400\n'
                                   '  h: hi\n  end\n'))
    r2 = read_blob(compile_blob(m2, d))
    assert r2["images"][0][:2] == (2, 2) and r2["images"][0][4] == 0, r2["images"]   # small: RGBA32
    assert r2["version"] == 5 and r2["font"] is None      # no font -> empty section
    # audio: bgm embeds the file; the step stores the index
    open(f"{d}/tema.wav", "wb").write(b"RIFF....WAVEfake" * 4)
    m4 = vn._link_choices(vn.parse('title: t\ncharacter a "A"\nscene s\n  bgm tema.wav\n  a: h\n'
                                   '  bgm stop\n  end\n'))
    r4 = read_blob(compile_blob(m4, d))
    assert len(r4["audios"]) == 1 and r4["audios"][0][0] == "tema.wav", r4["audios"]
    assert r4["scenes"][0][0]["op"] == "bgm" and r4["scenes"][0][0]["audio"] == 0
    assert r4["scenes"][0][2]["stop"] == 1 and r4["scenes"][0][2]["audio"] == 0xFFFF
    an = r2["scenes"][0][1]
    assert an["op"] == "animate" and an["kind"] == "move" and an["curve"] == "accel" and an["x"] == 200
    # font baking (if there is a system PSF)
    pf = psf.find_default()
    if pf:
        m3 = vn._link_choices(vn.parse('title: t\ncharacter a "Añí"\nscene s\n  a: Holá ¿ñ?\n  end\n'))
        rf = read_blob(compile_blob(m3, ".", font=pf))
        assert rf["font"] and rf["font"]["cell"] == (8, 16), rf["font"]
        for ch in "Holá¿ñ?A":
            assert ord(ch) in rf["font"]["cps"], f"missing glyph {ch!r}"
    print("demo OK")


if __name__ == "__main__":
    import sys
    cli(sys.argv[1:])
