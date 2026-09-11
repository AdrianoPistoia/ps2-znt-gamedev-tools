"""The PNG reader copes with whatever people download from the internet."""
import zlib, struct
from znt import image

ch = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
def png(w, h, depth, ctype, raw, plte=b"", interlace=0):
    out = b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, depth, ctype, 0, 0, interlace))
    if plte: out += ch(b"PLTE", plte)
    return out + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b"")

# 16 bits per channel (what half of Photoshop exports): downsampled to 8
raw = b"".join(b"\x00" + b"\xff\xee\x00\x11\x80\x00" * 2 for _ in range(2))
w, h, rows = image.load_png(png(2, 2, 16, 2, raw))
assert (w, h) == (2, 2) and rows[0][:4] == bytes([255, 0, 128, 255]), rows[0][:4]

# 4-bit palette (optimized PNG): two pixels per byte
plte = bytes([255,0,0, 0,255,0, 0,0,255])
raw4 = b"".join(b"\x00" + bytes([0x01, 0x20]) for _ in range(2))   # 3 px per row
w, h, rows = image.load_png(png(3, 2, 4, 3, raw4, plte))
assert (w, h) == (3, 2)
assert rows[0][:12] == bytes([255,0,0,255, 0,255,0,255, 0,0,255,255]), rows[0][:12]

# interlaced: not supported, but it says why
try:
    image.load_png(png(2, 2, 8, 2, b"\x00\x00\x00\x00\x00\x00\x00\x00", interlace=1))
    raise SystemExit("should have failed")
except Exception as e:
    assert "interlac" in str(e).lower(), str(e)
print("DEPTHS GREEN")
