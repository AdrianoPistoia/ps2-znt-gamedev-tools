#!/usr/bin/env python3
"""Lector mínimo de PNG a filas RGBA (solo stdlib), para cargar assets propios en
el runtime de VN. Complementa el escritor de `render`/`tim2`.

Soporta profundidad 8 bits, color types 0/2/3/6 (gris, RGB, paleta, RGBA) y los
5 filtros. Devuelve `(w, h, rows)` donde cada fila son `w*4` bytes RGBA — el mismo
formato que consume `render.Layer.loadImage`.

ponytail: 8bpp nomás; agregar 16bpp/interlaced sólo si algún asset lo pide.
"""
import struct, zlib

CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else (b if pb <= pc else c)


def load_png(data):
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "no es PNG"
    i = 8
    w = h = depth = ctype = None
    idat = bytearray(); plte = b""; trns = b""
    while i < len(data):
        ln = struct.unpack(">I", data[i:i+4])[0]
        tag = data[i+4:i+8]; body = data[i+8:i+8+ln]; i += 12 + ln
        if tag == b"IHDR":
            w, h, depth, ctype = struct.unpack(">IIBB", body[:10])
        elif tag == b"PLTE": plte = body
        elif tag == b"tRNS": trns = body
        elif tag == b"IDAT": idat += body
        elif tag == b"IEND": break
    assert depth == 8, f"solo 8bpp (vino {depth})"
    ch = CHANNELS[ctype]
    stride = w * ch
    raw = zlib.decompress(bytes(idat))
    # des-filtrado por scanline
    out = bytearray(); prev = bytearray(stride)
    pos = 0
    for _ in range(h):
        ft = raw[pos]; line = bytearray(raw[pos+1:pos+1+stride]); pos += 1 + stride
        if ft == 1:
            for x in range(ch, stride): line[x] = (line[x] + line[x-ch]) & 255
        elif ft == 2:
            for x in range(stride): line[x] = (line[x] + prev[x]) & 255
        elif ft == 3:
            for x in range(stride):
                a = line[x-ch] if x >= ch else 0
                line[x] = (line[x] + (a + prev[x]) // 2) & 255
        elif ft == 4:
            for x in range(stride):
                a = line[x-ch] if x >= ch else 0
                c = prev[x-ch] if x >= ch else 0
                line[x] = (line[x] + _paeth(a, prev[x], c)) & 255
        out += line; prev = line
    # a RGBA
    rows = []
    for y in range(h):
        s = out[y*stride:(y+1)*stride]
        r = bytearray(w * 4)
        for x in range(w):
            if ctype == 6:
                r[x*4:x*4+4] = s[x*4:x*4+4]
            elif ctype == 2:
                r[x*4:x*4+3] = s[x*3:x*3+3]; r[x*4+3] = 255
            elif ctype == 0:
                g = s[x]; r[x*4:x*4+3] = bytes((g, g, g)); r[x*4+3] = 255
            elif ctype == 4:
                g, a = s[x*2], s[x*2+1]; r[x*4:x*4+3] = bytes((g, g, g)); r[x*4+3] = a
            elif ctype == 3:
                idx = s[x]
                r[x*4:x*4+3] = plte[idx*3:idx*3+3]
                r[x*4+3] = trns[idx] if idx < len(trns) else 255
        rows.append(bytes(r))
    return w, h, rows


def load_png_file(path):
    return load_png(open(path, "rb").read())


def demo():
    """Round-trip: escribe un PNG RGB con render y lo relee."""
    from . import render
    fb = render.Framebuffer(3, 2, bg=(10, 20, 30))
    fb.buf[0:3] = bytes((200, 100, 50))      # pixel (0,0)
    w, h, rows = load_png(fb.png_bytes())
    assert (w, h) == (3, 2), (w, h)
    assert rows[0][0:4] == bytes((200, 100, 50, 255)), rows[0][:4]
    assert rows[1][0:4] == bytes((10, 20, 30, 255)), rows[1][:4]
    # filtros: una imagen con gradiente fuerza filtros Sub/Up/Paeth
    fb2 = render.Framebuffer(8, 8, bg=(0, 0, 0))
    for y in range(8):
        for x in range(8):
            o = (y*8+x)*3; fb2.buf[o:o+3] = bytes((x*30 & 255, y*30 & 255, (x+y)*15 & 255))
    w2, h2, rows2 = load_png(fb2.png_bytes())
    assert rows2[3][12:15] == bytes((3*30, 3*30, 6*15)), rows2[3][12:15]
    print("demo OK")


if __name__ == "__main__":
    demo()
