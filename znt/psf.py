#!/usr/bin/env python3
"""PSF console font parser (PSF1 and PSF2), stdlib. Used to bake a glyph atlas
into the VN blob (see `vniso.bake_font`). No font is embedded in the repo: the
author picks the .psf at build time (its license travels with the .vnp, not
with this code).

Returns `Font(w, h, glyphs)` where `glyphs[codepoint]` = bytes of `h` rows,
each `ceil(w/8)` bytes (1bpp, MSB first).
"""
import struct, gzip


class Font:
    def __init__(self, w, h, glyphs):
        self.w, self.h, self.glyphs = w, h, glyphs
    @property
    def stride(self): return (self.w + 7) // 8
    def has(self, cp): return cp in self.glyphs


def _maybe_gunzip(data):
    return gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data


def parse(data):
    data = _maybe_gunzip(data)
    if data[:4] == b"\x72\xb5\x4a\x86":
        return _psf2(data)
    if data[:2] == b"\x36\x04":
        return _psf1(data)
    raise ValueError("not a PSF1/PSF2")


def _psf1(d):
    mode, charsize = d[2], d[3]
    w, h = 8, charsize
    nglyphs = 512 if (mode & 0x01) else 256
    off = 4
    bitmaps = [d[off + i*charsize: off + (i+1)*charsize] for i in range(nglyphs)]
    off += nglyphs * charsize
    glyphs = {}
    if mode & 0x02:                       # unicode table: u16 per codepoint, 0xFFFF separates
        i = 0
        for gi in range(nglyphs):
            while off + 1 < len(d):
                cp = struct.unpack_from("<H", d, off)[0]; off += 2
                if cp == 0xFFFF: break
                if cp != 0xFFFE: glyphs.setdefault(cp, bitmaps[gi])
    else:
        for gi in range(min(nglyphs, 256)): glyphs[gi] = bitmaps[gi]   # assumes Latin-1
    return Font(w, h, glyphs)


def _psf2(d):
    (magic, ver, hdr, flags, length, charsize, height, width) = struct.unpack_from("<IIIIIIII", d, 0)
    stride = (width + 7) // 8
    off = hdr
    bitmaps = [d[off + i*charsize: off + (i+1)*charsize] for i in range(length)]
    off += length * charsize
    glyphs = {}
    if flags & 0x01:                      # unicode table in UTF-8, 0xFF separates glyphs
        gi = 0
        seq = bytearray()
        while off < len(d) and gi < length:
            b = d[off]; off += 1
            if b == 0xFF:
                for ch in seq.decode("utf-8", "ignore"):
                    glyphs.setdefault(ord(ch), bitmaps[gi])
                seq = bytearray(); gi += 1
            elif b == 0xFE:
                pass                       # sequence separator (ligatures): ignore
            else:
                seq.append(b)
    else:
        for gi in range(length): glyphs[gi] = bitmaps[gi]
    return Font(width, height, glyphs)


# typical system fonts with Latin coverage (for a convenience default)
DEFAULT_CANDIDATES = [
    "/usr/share/kbd/consolefonts/lat9w-16.psfu.gz",
    "/usr/share/kbd/consolefonts/cp850-8x16.psfu.gz",
    "/usr/share/kbd/consolefonts/default8x16.psfu.gz",
    "/usr/share/consolefonts/lat9w-16.psfu.gz",
]


def find_default():
    import os
    for p in DEFAULT_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def load(path):
    return parse(open(path, "rb").read())


def demo():
    p = find_default()
    if not p:
        print("demo OK (no system PSF; parser not exercised)"); return
    f = load(p)
    assert f.w in (8, 9) and f.h >= 8, (f.w, f.h)
    assert f.has(ord("A")) and any(f.glyphs[ord("A")]), "glyph A is empty"
    assert f.has(ord(" ")) and not any(f.glyphs[ord(" ")]), "space is not empty"
    # lat9/cp850 cover ñ
    if f.has(ord("ñ")):
        assert any(f.glyphs[ord("ñ")])
    print("demo OK")


if __name__ == "__main__":
    demo()
