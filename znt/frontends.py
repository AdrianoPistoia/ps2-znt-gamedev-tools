#!/usr/bin/env python3
"""Headless frontend for the `engine`: records the run to an animated PNG (APNG,
full color) reusing the PNG chunk writer, with no palette quantization. The core
is headless; this consumes it without coupling (the engine does not import it).

The interactive frontends (live window, test bench, VN Studio) live in the
`znt.gui` subpackage — they can be deleted without affecting the core.

  python -m znt record <disc> <scene> <out.apng>   # record to APNG
"""
import zlib, struct


# --- APNG (animated PNG, RGB, unquantized) ----------------------------------
def _chunk(tag, data):
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))


def _zpix(rgb, w, h):
    raw = bytearray()
    for y in range(h):
        raw.append(0); raw += rgb[y*w*3:(y+1)*w*3]     # filter 0 per scanline
    return zlib.compress(bytes(raw), 6)


def write_apng(frames, w, h, path, delay_ms=80, plays=0):
    """frames: list of RGB buffers (w*h*3 bytes). plays=0 -> infinite loop."""
    assert frames, "no frames"
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
    """Nearest-neighbor downsample by integer factor k (to shrink the APNG)."""
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
    """Run the scene capturing frames during each animation + a short hold on
    each talk, advancing on its own. Writes an APNG (shrunk by `shrink` to keep it small)."""
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
        for _ in range(max(1, hold_ms // dt)):     # hold to "read"
            snap()
        engine.advance()
    w, h = engine.W, engine.H
    shrunk = [_shrink(f, w, h, shrink) for f in frames]
    fw, fh = shrunk[0][1], shrunk[0][2]
    return write_apng([s[0] for s in shrunk], fw, fh, path, delay_ms=dt)


# --- entry point ------------------------------------------------------------
def record_cli(disc_path, scene, out):
    import znt
    from .engine import Engine
    w, h, n = record(Engine(znt.open(disc_path)), int(scene), out)
    print(f"APNG {w}x{h}, {n} frames -> {out}")


def demo():
    """Display-free self-check: valid APNG with acTL and N frames."""
    w, h = 4, 3
    a = bytes([200, 30, 30]) * (w*h)
    b = bytes([30, 30, 200]) * (w*h)
    import tempfile, os
    p = tempfile.mktemp(suffix=".apng")
    write_apng([a, b, a], w, h, p, delay_ms=100)
    d = open(p, "rb").read(); os.remove(p)
    assert d[:8] == b"\x89PNG\r\n\x1a\n"
    assert b"acTL" in d and b"fcTL" in d and b"fdAT" in d
    # num_frames in acTL == 3
    i = d.index(b"acTL")
    nf = struct.unpack(">I", d[i+4:i+8])[0]
    assert nf == 3, nf
    print("demo OK")


if __name__ == "__main__":
    demo()
