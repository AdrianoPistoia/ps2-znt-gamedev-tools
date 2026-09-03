#!/usr/bin/env python3
"""Parser de fuentes de consola PSF (PSF1 y PSF2), stdlib. Sirve para hornear un
atlas de glifos en el blob de la VN (ver `vniso.bake_font`). No embebe ninguna
fuente en el repo: el autor elige el .psf al compilar (su licencia viaja con el
.vnp, no con este código).

Devuelve `Font(w, h, glyphs)` donde `glyphs[codepoint]` = bytes de `h` filas,
cada una de `ceil(w/8)` bytes (1bpp, bit MSB primero).
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
    raise ValueError("no es PSF1/PSF2")


def _psf1(d):
    mode, charsize = d[2], d[3]
    w, h = 8, charsize
    nglyphs = 512 if (mode & 0x01) else 256
    off = 4
    bitmaps = [d[off + i*charsize: off + (i+1)*charsize] for i in range(nglyphs)]
    off += nglyphs * charsize
    glyphs = {}
    if mode & 0x02:                       # tabla unicode: u16 por codepoint, 0xFFFF separa
        i = 0
        for gi in range(nglyphs):
            while off + 1 < len(d):
                cp = struct.unpack_from("<H", d, off)[0]; off += 2
                if cp == 0xFFFF: break
                if cp != 0xFFFE: glyphs.setdefault(cp, bitmaps[gi])
    else:
        for gi in range(min(nglyphs, 256)): glyphs[gi] = bitmaps[gi]   # asume Latin-1
    return Font(w, h, glyphs)


def _psf2(d):
    (magic, ver, hdr, flags, length, charsize, height, width) = struct.unpack_from("<IIIIIIII", d, 0)
    stride = (width + 7) // 8
    off = hdr
    bitmaps = [d[off + i*charsize: off + (i+1)*charsize] for i in range(length)]
    off += length * charsize
    glyphs = {}
    if flags & 0x01:                      # tabla unicode en UTF-8, 0xFF separa glifos
        gi = 0
        seq = bytearray()
        while off < len(d) and gi < length:
            b = d[off]; off += 1
            if b == 0xFF:
                for ch in seq.decode("utf-8", "ignore"):
                    glyphs.setdefault(ord(ch), bitmaps[gi])
                seq = bytearray(); gi += 1
            elif b == 0xFE:
                pass                       # separador de secuencia (ligaduras): ignorar
            else:
                seq.append(b)
    else:
        for gi in range(length): glyphs[gi] = bitmaps[gi]
    return Font(width, height, glyphs)


# fuentes de sistema típicas con cobertura latina (para default de conveniencia)
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
        print("demo OK (sin PSF de sistema; parser no ejercitado)"); return
    f = load(p)
    assert f.w in (8, 9) and f.h >= 8, (f.w, f.h)
    assert f.has(ord("A")) and any(f.glyphs[ord("A")]), "glifo A vacío"
    assert f.has(ord(" ")) and not any(f.glyphs[ord(" ")]), "espacio no vacío"
    # lat9/cp850 cubren ñ
    if f.has(ord("ñ")):
        assert any(f.glyphs[ord("ñ")])
    print("demo OK")


if __name__ == "__main__":
    demo()
