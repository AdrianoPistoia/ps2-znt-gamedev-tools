"""Expressions in the runtime and the server."""
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
png(os.path.join(d, "ana.png"), 10, 20, (1, 2, 3)); png(os.path.join(d, "happy.png"), 30, 40, (4, 5, 6))
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter ana "Ana"\nsprite ana ana.png\nsprite ana happy happy.png\n'
    'scene s\n  show ana left\n  ana: one\n  show ana happy\n  ana: two\n  show ana right\n  end\n')

# runtime: the expression picks the file, and re-showing without a pos keeps the position
rt = VNRuntime(vn._link_choices(vn.parse(open(p, encoding="utf-8").read())), d)
rt.preview_upto("s", 0)
l = rt.stage["ana"]; assert (len(l.rows[0]) // 4, len(l.rows)) == (10, 20) and l.x == -180.0
rt.preview_upto("s", 2)
l = rt.stage["ana"]; assert (len(l.rows[0]) // 4, len(l.rows)) == (30, 40), "switched to happy.png"
assert l.x == -180.0, f"without a pos it keeps the position: {l.x}"
rt.preview_upto("s", 4)
assert rt.stage["ana"].x == 180.0, "with an explicit pos it moves"

# server: the stage exposes the expression; ops to define expressions
st = ws.Studio(p)
st.op({"op": "select", "scene": "s", "step": 2})
lay = st.stage("s", 2)["layers"][0]
assert lay["expr"] == "happy" and lay["url"].endswith("happy.png"), lay
assert lay["w"] == 30

st.op({"op": "set_sprite", "id": "ana", "expr": "sad", "file": "ana.png"})
assert st.model["characters"]["ana"]["expr"]["sad"] == "ana.png"
st.op({"op": "set_sprite", "id": "ana", "expr": "sad", "file": ""})
assert "sad" not in st.model["characters"]["ana"]["expr"], "empty = remove the expression"
st.op({"op": "import_asset", "path": os.path.join(d, "happy.png"), "id": "ana", "expr": "wink"})
assert st.model["characters"]["ana"]["expr"]["wink"] == "happy.png"

# show picks the expression via props, and the state lists the character's expressions
st.op({"op": "set_props", "props": {"expr": "wink"}})
assert st.model["scenes"]["s"][2]["expr"] == "wink"
st.op({"op": "set_props", "props": {"expr": ""}})
assert "expr" not in st.model["scenes"]["s"][2], "empty = base sprite"
print("EXPR RUNTIME GREEN")
