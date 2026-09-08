"""Blob v5: cabecera con head_size; imágenes y audio son un índice (off, len) y la
data va al final del archivo. Así el ELF carga sólo la cabecera y lee cada imagen /
audio por demanda (fseek) en vez de tener el blob entero en los 32 MB del EE."""
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
for w, h, off, ln in r["images"]:
    assert ln == w * h * 4 and off >= H and off + ln <= len(blob), (w, h, off, ln, H)
name, alen, aoff = r["audios"][0]
assert name == "t.wav" and alen == 112 and aoff >= H and blob[aoff:aoff + alen] == open(os.path.join(d, "t.wav"), "rb").read()
# la imagen del fondo está tal cual (RGBA) en su offset
fw, fh, foff, flen = r["images"][r["scenes"][0][0]["img"]]
assert (fw, fh) == (8, 2) and blob[foff:foff + 4] == bytes((7, 8, 9, 255)), blob[foff:foff + 4]
# la cabecera sola alcanza para leer todo menos los datos (lo que hace el ELF)
r2 = vniso.read_blob(blob[:H])
assert r2["scenes"] == r["scenes"] and r2["images"] == r["images"] and r2["audios"] == r["audios"]
# la data no se solapa ni deja huecos: cabecera + imágenes + audios = archivo
assert H + sum(i[3] for i in r["images"]) + sum(a[1] for a in r["audios"]) == len(blob)
# el preset de posición viaja como x (el ELF no conoce left/center/right)
sh = r["scenes"][0][2]
assert sh["op"] == "show" and sh["x"] == vn.POS["left"] == -180, sh
print("BLOB V5 GREEN")
