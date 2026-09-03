"""Nada silencioso: una op desconocida o un asset ilegible se REPORTAN."""
import tempfile, os, base64
from znt.web import server as ws

d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter a "Ana"\nscene s\n  show a\n  a: hola\n  end\n')
st = ws.Studio(p)
antes = repr(st.model)

# 1) op que no existe (p.ej. un server viejo contra una UI nueva)
r = st.op({"op": "upload_lo_que_sea", "id": "a"})
assert "error" in r and "upload_lo_que_sea" in r["error"], r.get("error")
assert repr(st.model) == antes, "no puede tocar el modelo"
assert r.get("model"), "igual devuelve el estado completo, no rompe la UI"

# 2) imagen que el lector no entiende: placeholder + aviso con el nombre
open(os.path.join(d, "rota.png"), "wb").write(b"\x89PNG\r\n\x1a\nbasura")
st.op({"op": "set_sprite", "id": "a", "file": "rota.png"})
stg = st.stage("s", 0)
assert stg["layers"], "la escena tiene que seguir dibujándose"
assert any("rota.png" in w for w in stg.get("warnings", [])), stg.get("warnings")

# y una que sí se lee no deja aviso
import zlib, struct
ch = lambda t, dd: struct.pack(">I", len(dd)) + t + dd + struct.pack(">I", zlib.crc32(t + dd))
raw = b"".join(b"\x00" + bytes([200, 100, 50]) * 8 for _ in range(8))
open(os.path.join(d, "ok.png"), "wb").write(
    b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0))
    + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b""))
st.op({"op": "set_sprite", "id": "a", "file": "ok.png"})
assert not st.stage("s", 0).get("warnings"), st.stage("s", 0).get("warnings")
print("ERRORS GREEN")
