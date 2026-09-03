#!/usr/bin/env python3
"""Lector minimo de TIM2 y volcado a PNG en escala de grises (solo stdlib).

  python -m znt tim2 info  a.tm2
  python -m znt tim2 png   a.tm2 salida.png [x y w h]     recorte opcional
"""
import struct, sys, zlib

FMT = {1: '16bpp', 2: '24bpp', 3: '32bpp', 4: '4bpp-idx', 5: '8bpp-idx'}


def parse(d):
    assert d[:4] == b'TIM2', "no es TIM2"
    o = 0x10
    tot, clut, img, hdr, ncol = struct.unpack('<IIIHH', d[o:o+16])
    ityp, mip, ctyp, icol = d[o+16:o+20]
    w, h = struct.unpack('<HH', d[o+20:o+24])
    pix = d[o+hdr:o+hdr+img]
    pal = d[o+hdr+img:o+hdr+img+clut]
    return dict(w=w, h=h, fmt=icol, ncol=ncol, hdr=hdr, pix=pix, pal=pal,
                clut_type=ctyp, img_size=img, clut_size=clut)


def gray(t):
    """indice -> luminancia. Devuelve una fila de bytes por scanline."""
    w, h, f, pix, pal = t['w'], t['h'], t['fmt'], t['pix'], t['pal']
    lut = []
    step = 4 if len(pal) >= t['ncol'] * 4 else 3
    for i in range(t['ncol']):
        r, g, b = pal[i*step:i*step+3] if (i+1)*step <= len(pal) else (0, 0, 0)
        a = pal[i*step+3] if step == 4 and (i+1)*step <= len(pal) else 0x80
        # alfa de PS2: 0x80 = opaco. Se compone contra negro.
        lum = (r*299 + g*587 + b*114) // 1000
        lut.append(min(255, lum * min(a, 0x80) // 0x80 * 2))
    rows = []
    if f == 4:
        stride = w // 2
        for y in range(h):
            r = bytearray()
            for x in range(stride):
                b = pix[y*stride + x]
                r.append(lut[b & 0x0F]); r.append(lut[b >> 4])
            rows.append(bytes(r))
    elif f == 5:
        for y in range(h):
            rows.append(bytes(lut[c] for c in pix[y*w:(y+1)*w]))
    else:
        raise SystemExit(f"formato {FMT.get(f, f)} no soportado para volcado")
    return rows


def _unswizzle_clut(entries):
    """CLUT de PS2 en 8bpp (CSM1): en cada bloque de 32, los runs [8:16] y
    [16:24] van intercambiados. Sin esto los colores salen permutados."""
    out = list(entries)
    for i in range(0, len(out) - 31, 32):
        out[i+8:i+16], out[i+16:i+24] = out[i+16:i+24], out[i+8:i+16]
    return out


def rgba(t):
    """indice -> (r,g,b,a). Devuelve una fila de bytes RGBA por scanline."""
    w, h, f, pix, pal = t['w'], t['h'], t['fmt'], t['pix'], t['pal']
    step = 4 if len(pal) >= t['ncol'] * 4 else 3
    ent = []
    for i in range(t['ncol']):
        r, g, b = pal[i*step:i*step+3] if (i+1)*step <= len(pal) else (0, 0, 0)
        a = pal[i*step+3] if step == 4 and (i+1)*step <= len(pal) else 0x80
        ent.append((r, g, b, min(255, a * 2)))     # alfa PS2: 0x80 = opaco
    if f == 5:
        ent = _unswizzle_clut(ent)
    lut = [bytes(e) for e in ent]
    rows = []
    if f == 4:
        stride = w // 2
        for y in range(h):
            r = bytearray()
            for x in range(stride):
                b = pix[y*stride + x]
                r += lut[b & 0x0F]; r += lut[b >> 4]
            rows.append(bytes(r))
    elif f == 5:
        for y in range(h):
            rows.append(b"".join(lut[c] for c in pix[y*w:(y+1)*w]))
    else:
        raise SystemExit(f"formato {FMT.get(f, f)} no soportado para color")
    return rows


def png(rows, path):
    h = len(rows); w = len(rows[0])
    raw = b"".join(b"\0" + r for r in rows)
    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))
    out = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 6))
           + chunk(b"IEND", b""))
    open(path, "wb").write(out)
    return w, h


class Texture:
    """Un TIM2 en memoria. `.png(path)` lo vuelca; `.rows()` da luminancia."""

    def __init__(self, data):
        self.data = data
        self._t = parse(data)

    @property
    def w(self):
        return self._t['w']

    @property
    def h(self):
        return self._t['h']

    @property
    def fmt(self):
        return FMT.get(self._t['fmt'], self._t['fmt'])

    def rows(self, box=None):
        rs = gray(self._t)
        if box:
            x, y, w, h = box
            rs = [r[x:x+w] for r in rs[y:y+h]]
        return rs

    def rgba(self):
        """Filas de bytes RGBA (4 bytes/pixel)."""
        return rgba(self._t)

    def png(self, path, box=None):
        return png(self.rows(box), path)

    def __repr__(self):
        return f"<Texture {self.w}x{self.h} {self.fmt}>"


def demo():
    """Self-check con un TIM2 sintetico 2x2 de 8bpp indexado."""
    hdr = struct.pack('<IIIHH', 0, 4*4, 4, 0x30, 4) + bytes([0, 0, 0, 5]) + struct.pack('<HH', 2, 2)
    pix = bytes([0, 1, 2, 3])
    pal = bytes([0, 0, 0, 0x80,  255, 255, 255, 0x80,  128, 0, 0, 0x80,  0, 0, 0, 0x80])
    d = b'TIM2' + b'\0' * 12 + hdr + b'\0' * (0x30 - 0x18) + pix + pal
    t = Texture(d)
    assert (t.w, t.h) == (2, 2), (t.w, t.h)
    rs = t.rows()
    assert rs[0][0] == 0 and rs[0][1] == 255, rs[0]
    rg = t.rgba()
    assert rg[0][0:4] == bytes([0, 0, 0, 255]), rg[0][:4]          # indice 0 negro opaco
    assert rg[0][4:8] == bytes([255, 255, 255, 255]), rg[0][4:8]   # indice 1 blanco opaco
    # des-swizzle: bloque de 32, swap [8:16]<->[16:24]
    sw = _unswizzle_clut(list(range(32)))
    assert sw[8:16] == list(range(16, 24)) and sw[16:24] == list(range(8, 16)), sw
    print("demo OK")


def cli(argv):
    if not argv or argv[0] == "demo":
        return demo()
    cmd, src = argv[0], argv[1]
    t = Texture(open(src, "rb").read())
    if cmd == "info":
        print(f"{t.w}x{t.h}  {t.fmt}")
    else:
        box = tuple(map(int, argv[3:7])) if len(argv) > 6 else None
        print("escrito", *t.png(argv[2], box), "->", argv[2])


if __name__ == "__main__":
    cli(sys.argv[1:])
