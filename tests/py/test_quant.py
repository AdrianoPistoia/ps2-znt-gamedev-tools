"""Cuantización a 256 colores (8bpp + CLUT) para las texturas del player PS2.
Baja 4x la VRAM y 4x los bytes que se leen del DVD. El CLUT sale ya en el orden
que espera el GS (CSM1), así el ELF lo sube tal cual."""
import math
from znt import quant

def rgba(px):                      # lista de tuplas -> bytes
    return b"".join(bytes(p) for p in px)

def err(a, b):                     # error medio por canal
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)

# --- tamaños y forma de la salida ---
w, h = 8, 4
img = rgba([(10, 20, 30, 255)] * (w * h))
clut, idx = quant.quantize(w, h, img)
assert len(clut) == 1024, len(clut)          # 256 entradas RGBA
assert len(idx) == w * h, len(idx)

# --- color plano: round-trip exacto ---
assert quant.unquantize(w, h, clut, idx) == img

# --- pocos colores distintos (arte plano de VN): exacto, sin pérdida ---
cols = [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 128), (0, 0, 0, 0)]
img = rgba([cols[(x + y) % 4] for y in range(16) for x in range(16)])
clut, idx = quant.quantize(16, 16, img)
assert quant.unquantize(16, 16, clut, idx) == img, "con <=256 colores no tiene que perder nada"
assert len(set(idx)) == 4, sorted(set(idx))

# --- degradé: más de 256 colores, error chico ---
W = H = 64
img = rgba([(x * 4, y * 4, (x + y) * 2, 255) for y in range(H) for x in range(W)])
clut, idx = quant.quantize(W, H, img)
out = quant.unquantize(W, H, clut, idx)
assert err(img, out) < 6, err(img, out)

# --- alfa: lo transparente sigue transparente y lo opaco opaco ---
img = rgba([(200, 100, 50, 0) if x < 32 else (200, 100, 50, 255) for y in range(H) for x in range(W)])
clut, idx = quant.quantize(W, H, img)
out = quant.unquantize(W, H, clut, idx)
for i in range(0, len(img), 4):
    assert out[i + 3] == img[i + 3], (i, out[i + 3], img[i + 3])

# --- el CLUT viaja en el orden del GS (CSM1): las entradas 8-15 y 16-23 van cruzadas ---
plain = bytes(range(256)) * 4
sw = quant.swizzle_clut(plain)
assert quant.swizzle_clut(sw) == plain, "el intercambio es su propio inverso"
assert sw[8 * 4:9 * 4] == plain[16 * 4:17 * 4], "la entrada 8 sale en el lugar 16"
assert sw[0:4] == plain[0:4] and sw[24 * 4:25 * 4] == plain[24 * 4:25 * 4], "0-7 y 24-31 no se mueven"

# --- sin pérdida sólo si entra en 256 colores exactos ---
assert quant.is_lossless(rgba([(1, 2, 3, 255)] * 100))
assert quant.is_lossless(rgba([(i, 0, 0, 255) for i in range(256)]))
assert not quant.is_lossless(rgba([(i % 256, i // 256, 0, 255) for i in range(300)]))

# --- el blob: arte plano va a 8bpp, el degradé se queda en RGBA32 (bandas visibles) ---
import tempfile, os, zlib, struct
from znt import vn, vniso

def png(path, w, h, f):
    ch = lambda t, b: struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b))
    raw = b"".join(b"\0" + b"".join(bytes(f(x, y)) for x in range(w)) for y in range(h))
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                           + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b""))

d = tempfile.mkdtemp()
png(f"{d}/plano.png", 64, 64, lambda x, y: (240, 200, 60, 255 if x < 40 else 0))       # 2 colores
png(f"{d}/degrade.png", 64, 64, lambda x, y: (x * 4, y * 4, (x + y) * 2, 255))         # miles
m = vn._link_choices(vn.parse('title: T\ncharacter a "A"\nsprite a plano.png\n'
                              'scene s\n  bg degrade.png\n  show a left\n  end\n'))
r = vniso.read_blob(vniso.compile_blob(m, base=d, font=None))
fmts = {(i[0], i[1]): i[4] for i in r["images"]}
assert fmts == {(64, 64): 0} or len(r["images"]) == 2, r["images"]
por_len = {i[4] for i in r["images"]}
assert 0 in por_len and 1 in por_len, [(i[0], i[1], i[3], i[4]) for i in r["images"]]
plano = next(i for i in r["images"] if i[4] == 1)
assert plano[3] == 1024 + 64 * 64, plano          # CLUT + un byte por pixel
degrade = next(i for i in r["images"] if i[4] == 0)
assert degrade[3] == 64 * 64 * 4, degrade         # crudo: sin bandas

# quantize="always" fuerza el 8bpp también en el degradé
r2 = vniso.read_blob(vniso.compile_blob(m, base=d, font=None, quantize="always"))
assert all(i[4] == 1 for i in r2["images"]), r2["images"]

print("QUANT GREEN")
