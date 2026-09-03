#!/usr/bin/env python3
"""La fuente del juego: NORMAL.BIN #0006, un BMP monocromo de 1bpp.

Atlas de 1024x1380, celdas de 24x26, 42 glifos por fila, 53 filas. El mapeo
Shift-JIS -> indice de glifo es NORMAL.BIN #0005, un archivo de texto CP932 de
42 caracteres por linea: la linea N es la fila N del atlas.

  python -m znt font info   0006.bmp
  python -m znt font png    0006.bmp out.png [x y w h]
  python -m znt font widths 0006.bmp 0005.txt      > anchos de tinta por glifo
"""
import struct, sys, zlib

# Geometria del atlas, derivada en el analisis (ver README 2.4)
CELL_W, CELL_H, PER_ROW = 24, 26, 42


def parse(d):
    off, = struct.unpack('<I', d[10:14])
    w, h, planes, bpp = struct.unpack('<iiHH', d[18:30])
    top_down = h < 0
    h = abs(h)
    stride = ((w * bpp + 31) // 32) * 4
    return dict(w=w, h=h, bpp=bpp, off=off, stride=stride,
                top_down=top_down, pix=d[off:])


def rows(f):
    w, stride, pix = f['w'], f['stride'], f['pix']
    out = []
    for y in range(f['h']):
        line = pix[y*stride:(y+1)*stride]
        r = bytearray()
        for x in range(w):
            bit = (line[x >> 3] >> (7 - (x & 7))) & 1
            r.append(255 if bit else 0)
        out.append(bytes(r))
    return out if f['top_down'] else out[::-1]


def png(rs, path):
    h = len(rs); w = len(rs[0])
    raw = b"".join(b"\0" + r for r in rs)
    def ch(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n"
        + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
        + ch(b"IDAT", zlib.compress(raw, 6)) + ch(b"IEND", b""))
    return w, h


def parse_table(data):
    """NORMAL #0005: texto CP932, 42 caracteres por linea. Indice = posicion."""
    return [c for line in data.decode("cp932").split("\r\n") for c in line]


def ink_width(rs, i):
    """Ancho de tinta del glifo i dentro de su celda. Base para el VWF."""
    r, c = divmod(i, PER_ROW)
    cols = [x for x in range(CELL_W)
            if any(rs[r*CELL_H + y][c*CELL_W + x] for y in range(CELL_H))]
    return cols[-1] - cols[0] + 1 if cols else 0


class Font:
    """Atlas de glifos + mapeo caracter->indice. Construida desde bytes."""

    def __init__(self, atlas_bmp, mapping_bytes):
        self._rows = rows(parse(atlas_bmp))
        self.chars = parse_table(mapping_bytes)          # indice -> caracter
        self.index = {c: i for i, c in enumerate(self.chars)}   # caracter -> indice

    def cell(self, ch):
        """Pixeles (filas de 0/255) de la celda 24x26 del caracter, o None."""
        i = self.index.get(ch)
        if i is None:
            return None
        r, c = divmod(i, PER_ROW)
        return [self._rows[r*CELL_H + y][c*CELL_W:(c+1)*CELL_W] for y in range(CELL_H)]

    def ink_width(self, ch):
        i = self.index.get(ch)
        return ink_width(self._rows, i) if i is not None else 0

    def png(self, path, box=None):
        rs = self._rows
        if box:
            x, y, w, h = box
            rs = [r[x:x+w] for r in rs[y:y+h]]
        return png(rs, path)


def demo():
    """Self-check con un BMP sintetico de 1bpp, sin depender del juego."""
    w, h = 16, 2
    pix = bytes([0b10100000, 0, 0, 0]) + bytes([0, 0b00000001, 0, 0])
    d = (b"BM" + struct.pack("<IHHI", 62 + len(pix), 0, 0, 62)
         + struct.pack("<IiiHHIIiiII", 40, w, -h, 1, 1, 0, len(pix), 0, 0, 2, 0)
         + b"\0" * 8 + pix)
    f = parse(d)
    assert (f["w"], f["h"], f["bpp"], f["stride"], f["top_down"]) == (16, 2, 1, 4, True), f
    rs = rows(f)
    assert [x for x, v in enumerate(rs[0]) if v] == [0, 2], rs[0]
    assert [x for x, v in enumerate(rs[1]) if v] == [15], rs[1]
    # mapeo: dos lineas CP932 separadas por CRLF
    chars = parse_table("ABC\r\nXYZ".encode("cp932"))
    assert chars == list("ABCXYZ") and chars[4] == "Y"
    print("demo OK")


def cli(argv):
    if not argv or argv[0] == "demo":
        return demo()
    cmd, src = argv[0], argv[1]
    f = parse(open(src, "rb").read())
    if cmd == "info":
        print(f"{f['w']}x{f['h']} {f['bpp']}bpp stride={f['stride']} top_down={f['top_down']}")
    elif cmd == "widths":
        rs = rows(f); chars = parse_table(open(argv[2], "rb").read())
        for i, c in enumerate(chars):
            print(f"{i}\t{c}\t{ink_width(rs, i)}")
    else:
        rs = rows(f)
        if len(argv) > 6:
            x, y, w, h = map(int, argv[3:7])
            rs = [r[x:x+w] for r in rs[y:y+h]]
        print("escrito", *png(rs, argv[2]), "->", argv[2])


if __name__ == "__main__":
    cli(sys.argv[1:])
