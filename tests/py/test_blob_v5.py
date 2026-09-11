"""Blob v5: header with head_size; images and audio are an index (off, len) and the
data goes at the end of the file. That way the ELF loads only the header and reads each
image / audio on demand (fseek) instead of holding the whole blob in the EE's 32 MB."""
import tempfile, os, zlib, struct
from znt import vn, vniso

def png(path, w, h, col):
    ch = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    raw = b"".join(b"\x00" + bytes(col) * w for _ in range(h))
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                           + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b""))

d = tempfile.mkdtemp()
png(os.path.join(d, "ana.png"), 4, 6, (1, 2, 3)); png(os.path.join(d, "fondo.png"), 8, 2, (7, 8, 9))
open(os.path.join(d, "t.wav"), "wb").write(b"RIFFxxxxWAVE" + b"\x55" * 100)
m = vn._link_choices(vn.parse(
    'title: T\ncharacter ana "Ana" color=#fff\nsprite ana ana.png\n'
    'scene s\n  bg fondo.png\n  bgm t.wav\n  show ana left\n  ana: hola\n  end\n'))
blob = vniso.compile_blob(m, base=d, font=None)
r = vniso.read_blob(blob)
assert r["version"] == 5, r["version"]
H = r["head_size"]
assert 0 < H < len(blob), (H, len(blob))
assert len(r["images"]) == 2
for w, h, off, ln, fmt in r["images"]:
    assert fmt == 0 and ln == w * h * 4, (w, h, fmt, "small image: raw RGBA32")
    assert off >= H and off + ln <= len(blob), (w, h, off, ln, H)
name, alen, aoff = r["audios"][0]
assert name == "t.wav" and alen == 112 and aoff >= H and blob[aoff:aoff + alen] == open(os.path.join(d, "t.wav"), "rb").read()
# the background image is verbatim (RGBA) at its offset
fw, fh, foff, flen, _ = r["images"][r["scenes"][0][0]["img"]]
assert (fw, fh) == (8, 2) and blob[foff:foff + 4] == bytes((7, 8, 9, 255)), blob[foff:foff + 4]
# the header alone is enough to read everything but the data (which is what the ELF does)
r2 = vniso.read_blob(blob[:H])
assert r2["scenes"] == r["scenes"] and r2["images"] == r["images"] and r2["audios"] == r["audios"]
# Every datum starts at a 2048 sector: the cdvd driver reads whole sectors, and
# asking it for an unaligned span makes it spin extra (166 KB/s measured in PCSX2).
for w, h, off, ln, fmt in r["images"]:
    assert off % 2048 == 0, (off, "image not sector-aligned")
for name, ln, off in r["audios"]:
    assert off % 2048 == 0, (off, name, "audio not sector-aligned")
assert H % 2048 == 0, (H, "the header has to end on a sector")
# the data goes after the header and does not overlap (with padding in between)
ends = sorted([(i[2], i[3]) for i in r["images"]] + [(a[2], a[1]) for a in r["audios"]])
prev = H
for off, ln in ends:
    assert off >= prev, (off, prev, "overlapping data")
    prev = off + ln
assert prev <= len(blob)
# the position preset travels as x (the ELF does not know left/center/right)
sh = r["scenes"][0][2]
assert sh["op"] == "show" and sh["x"] == vn.POS["left"] == -180, sh
print("BLOB V5 GREEN")
