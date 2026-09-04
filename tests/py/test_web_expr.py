"""Expresiones en el runtime y el server."""
import tempfile, os, zlib, struct
from znt.web import server as ws
from znt.vnstudio import VNRuntime
from znt import vn

def png(path, w, h, col):
    ch = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    raw = b"".join(b"\x00" + bytes(col) * w for _ in range(h))
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                           + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b""))

d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
png(os.path.join(d, "ana.png"), 10, 20, (1, 2, 3)); png(os.path.join(d, "feliz.png"), 30, 40, (4, 5, 6))
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter ana "Ana"\nsprite ana ana.png\nsprite ana feliz feliz.png\n'
    'scene s\n  show ana left\n  ana: uno\n  show ana feliz\n  ana: dos\n  show ana right\n  end\n')

# runtime: la expresión elige el archivo y re-mostrar sin pos conserva la posición
rt = VNRuntime(vn._link_choices(vn.parse(open(p, encoding="utf-8").read())), d)
rt.preview_upto("s", 0)
l = rt.stage["ana"]; assert (len(l.rows[0]) // 4, len(l.rows)) == (10, 20) and l.x == -180.0
rt.preview_upto("s", 2)
l = rt.stage["ana"]; assert (len(l.rows[0]) // 4, len(l.rows)) == (30, 40), "cambió a feliz.png"
assert l.x == -180.0, f"sin pos mantiene la posición: {l.x}"
rt.preview_upto("s", 4)
assert rt.stage["ana"].x == 180.0, "con pos explícita se mueve"

# server: stage expone la expresión; ops para definir expresiones
st = ws.Studio(p)
st.op({"op": "select", "scene": "s", "step": 2})
lay = st.stage("s", 2)["layers"][0]
assert lay["expr"] == "feliz" and lay["url"].endswith("feliz.png"), lay
assert lay["w"] == 30

st.op({"op": "set_sprite", "id": "ana", "expr": "triste", "file": "ana.png"})
assert st.model["characters"]["ana"]["expr"]["triste"] == "ana.png"
st.op({"op": "set_sprite", "id": "ana", "expr": "triste", "file": ""})
assert "triste" not in st.model["characters"]["ana"]["expr"], "vacío = quitar la expresión"
st.op({"op": "import_asset", "path": os.path.join(d, "feliz.png"), "id": "ana", "expr": "guiño"})
assert st.model["characters"]["ana"]["expr"]["guiño"] == "feliz.png"

# el show elige expresión por props, y el estado lista las expresiones del personaje
st.op({"op": "set_props", "props": {"expr": "guiño"}})
assert st.model["scenes"]["s"][2]["expr"] == "guiño"
st.op({"op": "set_props", "props": {"expr": ""}})
assert "expr" not in st.model["scenes"]["s"][2], "vacío = sprite base"
print("EXPR RUNTIME GREEN")
