#!/usr/bin/env python3
"""Compila un modelo `.vn` a un **blob binario `.vnp`** que el ELF player de PS2
(camino C del spike) lee y ejecuta. Headless y testeable; el `read_blob` de acá
sirve de verificación y de **spec** para el lector en C.

Formato (little-endian):

    "VNP1" | u16 version | u16 start_scene
    -- string pool --   u32 N ; por cada: u16 len + UTF-8      (idx 0xFFFFFFFF = none)
    -- characters --    u32 N ; por cada: u32 name_str, u32 color_rgba, u16 sprite_img(0xFFFF none)
    -- images --        u32 N ; por cada: u16 w, u16 h, u8 fmt(0=RGBA32), u32 len, bytes
    -- scenes --        u32 N ; por cada: u32 nsteps ; por cada step: u8 op + payload

Opcodes: 1 bg, 2 show, 3 hide, 4 say, 5 anim, 6 bgm, 7 se, 8 choice, 9 goto, 10 end.
(payloads: ver `_emit_step` / `_read_step`). Audio: opcode con el nombre de archivo,
sin data embebida todavía (diferido, ver spike).
"""
import struct, os, shutil, subprocess, tempfile

from . import vn, image, psf

SYSTEM_CNF = "BOOT2 = cdrom0:\\{name}.ELF;1\r\nVER = 1.00\r\nVMODE = {vmode}\r\n"

MAGIC = b"VNP1"
OP = dict(bg=1, show=2, hide=3, say=4, anim=5, bgm=6, se=7, choice=8, goto=9, end=10)
IOP = {v: k for k, v in OP.items()}
# códigos de animación (curvas + acciones)
ANIM = {"linear": 0, "accel": 1, "decel": 2, "move": 3,
        "wave": 10, "waveonce": 11, "jump": 12, "jumponce": 13, "fall": 14, "vibrate": 15}
IANIM = {v: k for k, v in ANIM.items()}
NONE32 = 0xFFFFFFFF
NONE16 = 0xFFFF


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
    """Todos los caracteres que la VN muestra (diálogos, opciones, nombres) + ASCII."""
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
    """Hornea un atlas 1bpp con los glifos que la VN usa, desde un .psf.
    Devuelve (cell_w, cell_h, cps_ordenados, bitmap) o None si no hay fuente."""
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


def compile_blob(model, base=".", font=None):
    model = vn._link_choices(model) if any(
        s["op"] == "_option" for steps in model["scenes"].values() for s in steps) else model
    order = model["order"]
    scene_idx = {sid: i for i, sid in enumerate(order)}

    # --- pool de strings (dedup) ---
    pool, pidx = [], {}
    def S(s):
        if s is None: return NONE32
        if s not in pidx:
            pidx[s] = len(pool); pool.append(s)
        return pidx[s]

    # --- personajes (sin narrator) e índice ---
    char_idx = {}
    chars = []
    for cid, c in model["characters"].items():
        if cid == "narrator":
            continue
        char_idx[cid] = len(chars); chars.append(c)

    # --- imágenes (sprites de personajes + fondos img) ---
    img_idx = {}
    images = []
    def IMG(fname):
        if not fname:
            return NONE16
        if fname not in img_idx:
            try:
                w, h, rows = image.load_png_file(f"{base}/{fname}")
                data = b"".join(rows)
            except Exception:
                w, h, data = 1, 1, b"\0\0\0\0"          # placeholder si falta
            img_idx[fname] = len(images); images.append((w, h, data))
        return img_idx[fname]

    for c in chars:
        c["_spr"] = IMG(c.get("sprite"))

    w = _W()
    w.b += MAGIC; w.u16(2); w.u16(scene_idx.get(model.get("start", order[0]), 0))
    S(model["title"])                                    # reservar título como string 0

    # cuerpo de escenas primero (llena el pool), luego se serializa el pool al final…
    # más simple: serializar en orden fijo pero el pool debe estar completo antes.
    # Estrategia: pre-pasar por todo para llenar el pool, luego emitir sin ambigüedad.
    for c in chars:
        S(c["name"])
    scene_bytes = []
    for sid in order:
        sw = _W(); steps = model["scenes"][sid]
        sw.u32(len(steps))
        for s in steps:
            _emit_step(sw, s, S, char_idx, scene_idx, IMG)
        scene_bytes.append(bytes(sw.b))

    # --- string pool ---
    w.u32(len(pool))
    for s in pool:
        enc = s.encode("utf-8"); w.u16(len(enc)); w.b += enc
    # --- characters ---
    w.u32(len(chars))
    for c in chars:
        w.u32(pidx[c["name"]]); w.u32(_rgba(c.get("color"))); w.u16(c["_spr"])
    # --- images ---
    w.u32(len(images))
    for iw, ih, data in images:
        w.u16(iw); w.u16(ih); w.u8(0); w.blob(data)
    # --- font (opcional) ---
    fnt = bake_font(model, font)
    if fnt:
        cw, ch, cps, fdata = fnt
        w.u8(1); w.u16(cw); w.u16(ch); w.u32(len(cps))
        for cp in cps:
            w.u32(cp)
        w.b += fdata
    else:
        w.u8(0)
    # --- scenes ---
    w.u32(len(order))
    for sb in scene_bytes:
        w.b += sb
    return bytes(w.b)


def build_iso(elf_path, blob_path, out_iso, name="VN", vmode="NTSC"):
    """Masteriza un ISO9660 booteable: SYSTEM.CNF (BOOT2 -> {name}.ELF), el ELF y el
    blob .vnp. Requiere `genisoimage`. Nombres 8.3 en MAYÚSCULAS (iso-level 1)."""
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


def _emit_step(w, s, S, char_idx, scene_idx, IMG):
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
    elif op == "show":
        w.u16(char_idx.get(s["id"], NONE16))
        w.i16(s.get("x", 0)); w.i16(s.get("y", 0)); w.i16(s.get("z", 0))
        w.u16(int(s.get("zoom", 100))); w.u8(int(s.get("opacity", 100)))
        w.u32(_rgba(s["tint"]) if s.get("tint") else 0)
    elif op == "hide":
        w.u16(char_idx.get(s["id"], NONE16))
    elif op == "say":
        w.u16(char_idx.get(s.get("who"), NONE16)); w.u32(S(s.get("text", "")))
    elif op == "animate":
        p = s.get("params", {})
        w.u8(ANIM.get(s["kind"], 0))                     # curva-como-kind / move / acción
        w.u8(ANIM.get(p.get("curve", "linear"), 0))      # curva (para move)
        w.i16(p.get("x", 0)); w.u16(int(p.get("time", p.get("falltime", 0))))
        w.i16(p.get("vib", p.get("vibration", 0))); w.u16(int(p.get("cycle", 0)))
        w.i16(p.get("dist", p.get("distance", 0)))
    elif op == "bgm":
        w.u8(1 if s.get("stop") else 0); w.u32(S(s.get("file")) if s.get("file") else NONE32)
    elif op == "se":
        w.u32(S(s.get("file")) if s.get("file") else NONE32)
    elif op == "choice":
        opts = s.get("options", []); w.u8(len(opts))
        for o in opts:
            w.u32(S(o["label"])); w.u16(scene_idx.get(o["target"], NONE16))
    elif op == "goto":
        w.u16(scene_idx.get(s["target"], NONE16))
    elif op == "end":
        pass


# --- lector de verificación (y spec del lector en C) ------------------------
class _R:
    def __init__(self, b): self.b = b; self.o = 0
    def u8(self): v = self.b[self.o]; self.o += 1; return v
    def u16(self): v = struct.unpack_from("<H", self.b, self.o)[0]; self.o += 2; return v
    def i16(self): v = struct.unpack_from("<h", self.b, self.o)[0]; self.o += 2; return v
    def u32(self): v = struct.unpack_from("<I", self.b, self.o)[0]; self.o += 4; return v
    def take(self, n): d = self.b[self.o:self.o+n]; self.o += n; return d


def read_blob(data):
    r = _R(data)
    assert r.take(4) == MAGIC, "no es VNP"
    version = r.u16(); start = r.u16()
    pool = []
    for _ in range(r.u32()):
        n = r.u16(); pool.append(r.take(n).decode("utf-8"))
    def S(i): return None if i == NONE32 else pool[i]
    chars = []
    for _ in range(r.u32()):
        chars.append(dict(name=S(r.u32()), color=r.u32(), sprite=r.u16()))
    images = []
    for _ in range(r.u32()):
        iw = r.u16(); ih = r.u16(); r.u8(); images.append((iw, ih)); r.take(r.u32())
    font = None
    if r.u8():
        cw = r.u16(); ch = r.u16(); n = r.u32()
        cps = [r.u32() for _ in range(n)]
        stride = (cw + 7) // 8
        r.take(n * ch * stride)
        font = {"cell": (cw, ch), "cps": cps}
    scenes = []
    for _ in range(r.u32()):
        steps = [_read_step(r, S) for _ in range(r.u32())]
        scenes.append(steps)
    return dict(version=version, start=start, title=pool[0] if pool else None,
                characters=chars, images=images, font=font, scenes=scenes)


def _read_step(r, S):
    op = IOP[r.u8()]
    if op == "bg":
        k = r.u8()
        if k == 0: return {"op": "bg", "kind": "solid", "color": r.u32()}
        if k == 1: return {"op": "bg", "kind": "grad", "a": r.u32(), "b": r.u32()}
        return {"op": "bg", "kind": "img", "img": r.u16()}
    if op == "show":
        return {"op": "show", "id": r.u16(), "x": r.i16(), "y": r.i16(), "z": r.i16(),
                "zoom": r.u16(), "opacity": r.u8(), "tint": r.u32()}
    if op == "hide":
        return {"op": "hide", "id": r.u16()}
    if op == "say":
        return {"op": "say", "who": r.u16(), "text": S(r.u32())}
    if op == "anim":
        kind = IANIM.get(r.u8(), "linear"); curve = IANIM.get(r.u8(), "linear")
        return {"op": "animate", "kind": kind, "curve": curve, "x": r.i16(),
                "time": r.u16(), "vib": r.i16(), "cycle": r.u16(), "dist": r.i16()}
    if op == "bgm":
        return {"op": "bgm", "stop": r.u8(), "file": S(r.u32())}
    if op == "se":
        return {"op": "se", "file": S(r.u32())}
    if op == "choice":
        n = r.u8()
        return {"op": "choice", "options": [{"label": S(r.u32()), "target": r.u16()} for _ in range(n)]}
    if op == "goto":
        return {"op": "goto", "target": r.u16()}
    return {"op": op}


def build(vn_path, out, elf=None, name="VN", font="auto"):
    """Compila una .vn a blob; si se da un ELF, masteriza el .iso booteable.
    Sin ELF, escribe sólo el blob .vnp (para probar el pipeline). `font`: ruta a un
    .psf, "auto" (detecta una del sistema) o None (sin texto)."""
    if font == "auto":
        font = psf.find_default()
    text = open(vn_path, encoding="utf-8").read()
    model = vn._link_choices(vn.parse(text))
    blob = compile_blob(model, os.path.dirname(os.path.abspath(vn_path)), font=font)
    if font:
        print(f"fuente horneada: {os.path.basename(font)}")
    if elf:
        tmp = out + ".vnp.tmp"
        open(tmp, "wb").write(blob)
        try:
            build_iso(elf, tmp, out, name=name)
        finally:
            os.remove(tmp)
        print(f"ISO booteable -> {out}  ({len(blob)} bytes de datos, ELF {os.path.basename(elf)})")
    else:
        vnp = out if out.endswith(".vnp") else out + ".vnp"
        open(vnp, "wb").write(blob)
        print(f"blob -> {vnp} ({len(blob)} bytes). Pasá --elf <player.elf> para masterizar el .iso.")
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
    # animate + imagen real embebida (round-trip)
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
    assert r2["images"] == [(2, 2)], r2["images"]
    assert r2["version"] == 2 and r2["font"] is None      # sin fuente -> sección vacía
    an = r2["scenes"][0][1]
    assert an["op"] == "animate" and an["kind"] == "move" and an["curve"] == "accel" and an["x"] == 200
    # horneado de fuente (si hay una PSF de sistema)
    pf = psf.find_default()
    if pf:
        m3 = vn._link_choices(vn.parse('title: t\ncharacter a "Añí"\nscene s\n  a: Holá ¿ñ?\n  end\n'))
        rf = read_blob(compile_blob(m3, ".", font=pf))
        assert rf["font"] and rf["font"]["cell"] == (8, 16), rf["font"]
        for ch in "Holá¿ñ?A":
            assert ord(ch) in rf["font"]["cps"], f"falta glifo {ch!r}"
    print("demo OK")


if __name__ == "__main__":
    import sys
    cli(sys.argv[1:])
