#!/usr/bin/env python3
"""Frontend headless del `engine`: graba la corrida a un PNG animado (APNG, todo
color) reusando el escritor de chunks de PNG, sin cuantización de paleta. El core
es headless; este lo consume sin acoplarse (el engine no lo importa).

Los frentes interactivos (ventana en vivo, banco de pruebas, VN Studio) viven en
el subpaquete `znt.gui` — se pueden borrar sin afectar al core.

  python -m znt record <disc> <scene> <out.apng>   # graba a APNG
"""
import zlib, struct


# --- APNG (PNG animado, RGB, sin cuantizar) ---------------------------------
def _chunk(tag, data):
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))


def _zpix(rgb, w, h):
    raw = bytearray()
    for y in range(h):
        raw.append(0); raw += rgb[y*w*3:(y+1)*w*3]     # filtro 0 por scanline
    return zlib.compress(bytes(raw), 6)


def write_apng(frames, w, h, path, delay_ms=80, plays=0):
    """frames: lista de buffers RGB (w*h*3 bytes). plays=0 -> loop infinito."""
    assert frames, "sin frames"
    out = [b"\x89PNG\r\n\x1a\n",
           _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)),
           _chunk(b"acTL", struct.pack(">II", len(frames), plays))]
    seq = 0
    dn, dd = delay_ms, 1000
    for i, fr in enumerate(frames):
        out.append(_chunk(b"fcTL", struct.pack(">IIIIIHHBB", seq, w, h, 0, 0, dn, dd, 0, 0)))
        seq += 1
        z = _zpix(bytes(fr), w, h)
        if i == 0:
            out.append(_chunk(b"IDAT", z))
        else:
            out.append(_chunk(b"fdAT", struct.pack(">I", seq) + z)); seq += 1
    out.append(_chunk(b"IEND", b""))
    open(path, "wb").write(b"".join(out))
    return w, h, len(frames)


def _shrink(rgb, w, h, k):
    """Downsample nearest-neighbor por factor entero k (para achicar el APNG)."""
    if k <= 1:
        return rgb, w, h
    w2, h2 = w // k, h // k
    out = bytearray(w2 * h2 * 3)
    for y in range(h2):
        sy = y * k
        for x in range(w2):
            s = (sy * w + x * k) * 3
            d = (y * w2 + x) * 3
            out[d:d+3] = rgb[s:s+3]
    return bytes(out), w2, h2


def record(engine, scene, path, fps=15, hold_ms=500, anim_ms=750, max_frames=90, shrink=2):
    """Corre la escena capturando frames durante cada animación + un hold corto en
    cada talk, y avanza solo. Escribe un APNG (achicado por `shrink` para pesar poco)."""
    dt = 1000 // fps
    frames = []
    engine.load(scene)

    def snap():
        if len(frames) < max_frames:
            frames.append(bytes(engine.frame().buf))

    while not engine.done and len(frames) < max_frames:
        el = 0
        while engine.animating() and el < anim_ms:
            engine.tick(dt); snap(); el += dt
        snap()
        for _ in range(max(1, hold_ms // dt)):     # hold para "leer"
            snap()
        engine.advance()
    w, h = engine.W, engine.H
    shrunk = [_shrink(f, w, h, shrink) for f in frames]
    fw, fh = shrunk[0][1], shrunk[0][2]
    return write_apng([s[0] for s in shrunk], fw, fh, path, delay_ms=dt)


# --- entrada ----------------------------------------------------------------
def record_cli(disc_path, scene, out):
    import znt
    from .engine import Engine
    w, h, n = record(Engine(znt.open(disc_path)), int(scene), out)
    print(f"APNG {w}x{h}, {n} frames -> {out}")


def demo():
    """Self-check sin display: APNG válido con acTL y N frames."""
    w, h = 4, 3
    a = bytes([200, 30, 30]) * (w*h)
    b = bytes([30, 30, 200]) * (w*h)
    import tempfile, os
    p = tempfile.mktemp(suffix=".apng")
    write_apng([a, b, a], w, h, p, delay_ms=100)
    d = open(p, "rb").read(); os.remove(p)
    assert d[:8] == b"\x89PNG\r\n\x1a\n"
    assert b"acTL" in d and b"fcTL" in d and b"fdAT" in d
    # num_frames en acTL == 3
    i = d.index(b"acTL")
    nf = struct.unpack(">I", d[i+4:i+8])[0]
    assert nf == 3, nf
    print("demo OK")


if __name__ == "__main__":
    demo()
