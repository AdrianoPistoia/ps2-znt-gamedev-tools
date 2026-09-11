"""Expressions in the HTML player and in the PS2 blob."""
import tempfile, os, zlib, struct, base64
from znt import vn, vniso

def png(path, w, h, col):
    ch = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    raw = b"".join(b"\x00" + bytes(col) * w for _ in range(h))
    data = (b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b""))
    open(path, "wb").write(data); return data

d = tempfile.mkdtemp()
png(os.path.join(d, "ana.png"), 4, 6, (1, 2, 3)); feliz = png(os.path.join(d, "feliz.png"), 8, 6, (9, 9, 9))
m = vn._link_choices(vn.parse(
    'title: T\ncharacter ana "Ana" color=#fff\nsprite ana ana.png\nsprite ana feliz feliz.png\n'
    'scene s\n  show ana left\n  ana: hola\n  show ana feliz\n  ana: chau\n  end\n'))

# --- HTML player: carries each expression's image and the show says which one to use
html = vn.render_html(m, d)
assert base64.b64encode(feliz).decode()[:40] in html, "the expression image is embedded"
assert '"feliz"' in html, "and the show/character names it"
assert "exprData" in html

# --- PS2 blob: the show carries the expression's image index (0xFFFF = the character's base)
blob = vniso.compile_blob(m, base=d, font=None)
r = vniso.read_blob(blob)
assert r["version"] >= 4, r["version"]
st = r["scenes"][0]
assert st[0]["op"] == "show" and st[0]["img"] == 0xFFFF, st[0]
assert st[2]["op"] == "show" and st[2]["img"] != 0xFFFF, st[2]
img = r["images"][st[2]["img"]]                       # (w, h, off, len, fmt)
assert tuple(img[:2]) == (8, 6), "points to feliz.png"
ana = next(c for c in r["characters"] if c["sprite"] != 0xFFFF)
assert r["images"][ana["sprite"]][0] == 4, "the base sprite is still ana.png"
print("EXPR EXPORT GREEN")
