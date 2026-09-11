"""256-color quantization (8bpp + CLUT) for the PS2 player's textures.
Cuts VRAM 4x and the bytes read from the DVD 4x. The CLUT comes out already in
the order the GS expects (CSM1), so the ELF uploads it as-is."""
import math
from znt import quant

def rgba(px):                      # list of tuples -> bytes
    return b"".join(bytes(p) for p in px)

def err(a, b):                     # mean error per channel
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)

# --- sizes and shape of the output ---
w, h = 8, 4
img = rgba([(10, 20, 30, 255)] * (w * h))
clut, idx = quant.quantize(w, h, img)
assert len(clut) == 1024, len(clut)          # 256 RGBA entries
assert len(idx) == w * h, len(idx)

# --- flat color: exact round-trip ---
assert quant.unquantize(w, h, clut, idx) == img

# --- few distinct colors (flat VN art): exact, lossless ---
cols = [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 128), (0, 0, 0, 0)]
img = rgba([cols[(x + y) % 4] for y in range(16) for x in range(16)])
clut, idx = quant.quantize(16, 16, img)
assert quant.unquantize(16, 16, clut, idx) == img, "with <=256 colors nothing must be lost"
assert len(set(idx)) == 4, sorted(set(idx))

# --- gradient: more than 256 colors, small error ---
W = H = 64
img = rgba([(x * 4, y * 4, (x + y) * 2, 255) for y in range(H) for x in range(W)])
clut, idx = quant.quantize(W, H, img)
out = quant.unquantize(W, H, clut, idx)
assert err(img, out) < 6, err(img, out)

# --- alpha: transparent stays transparent and opaque stays opaque ---
img = rgba([(200, 100, 50, 0) if x < 32 else (200, 100, 50, 255) for y in range(H) for x in range(W)])
clut, idx = quant.quantize(W, H, img)
out = quant.unquantize(W, H, clut, idx)
for i in range(0, len(img), 4):
    assert out[i + 3] == img[i + 3], (i, out[i + 3], img[i + 3])

# --- the CLUT travels in GS order (CSM1): entries 8-15 and 16-23 are crossed ---
plain = bytes(range(256)) * 4
sw = quant.swizzle_clut(plain)
assert quant.swizzle_clut(sw) == plain, "the swap is its own inverse"
assert sw[8 * 4:9 * 4] == plain[16 * 4:17 * 4], "entry 8 ends up in slot 16"
assert sw[0:4] == plain[0:4] and sw[24 * 4:25 * 4] == plain[24 * 4:25 * 4], "0-7 and 24-31 do not move"

# --- lossless only if it fits in 256 exact colors ---
assert quant.is_lossless(rgba([(1, 2, 3, 255)] * 100))
assert quant.is_lossless(rgba([(i, 0, 0, 255) for i in range(256)]))
assert not quant.is_lossless(rgba([(i % 256, i // 256, 0, 255) for i in range(300)]))

# --- the blob: flat art goes to 8bpp, the gradient stays RGBA32 (visible banding) ---
import tempfile, os, zlib, struct
from znt import vn, vniso

def png(path, w, h, f):
    ch = lambda t, b: struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b))
    raw = b"".join(b"\0" + b"".join(bytes(f(x, y)) for x in range(w)) for y in range(h))
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                           + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b""))

d = tempfile.mkdtemp()
png(f"{d}/plano.png", 64, 64, lambda x, y: (240, 200, 60, 255 if x < 40 else 0))       # 2 colors
png(f"{d}/degrade.png", 64, 64, lambda x, y: (x * 4, y * 4, (x + y) * 2, 255))         # thousands
m = vn._link_choices(vn.parse('title: T\ncharacter a "A"\nsprite a plano.png\n'
                              'scene s\n  bg degrade.png\n  show a left\n  end\n'))
r = vniso.read_blob(vniso.compile_blob(m, base=d, font=None))
fmts = {(i[0], i[1]): i[4] for i in r["images"]}
assert fmts == {(64, 64): 0} or len(r["images"]) == 2, r["images"]
por_len = {i[4] for i in r["images"]}
assert 0 in por_len and 1 in por_len, [(i[0], i[1], i[3], i[4]) for i in r["images"]]
plano = next(i for i in r["images"] if i[4] == 1)
assert plano[3] == 1024 + 64 * 64, plano          # CLUT + one byte per pixel
degrade = next(i for i in r["images"] if i[4] == 0)
assert degrade[3] == 64 * 64 * 4, degrade         # raw: no banding

# quantize="always" forces 8bpp on the gradient too
r2 = vniso.read_blob(vniso.compile_blob(m, base=d, font=None, quantize="always"))
assert all(i[4] == 1 for i in r2["images"]), r2["images"]

print("QUANT GREEN")
