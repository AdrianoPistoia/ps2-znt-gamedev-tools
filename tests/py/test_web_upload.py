"""Elegir una imagen del sistema: el browser la sube y queda junto al .vn."""
import tempfile, os, base64, zlib, struct
from znt.web import server as ws

def png(w, h):                                    # PNG mínimo, opaco
    raw = b"".join(b"\x00" + bytes([255, 0, 0]) * w for _ in range(h))
    ch = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    return (b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b""))

d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write('title: T\ncharacter a "Ana"\nscene s\n  show a\n  a: hola\n  end\n')
st = ws.Studio(p)

data = base64.b64encode(png(4, 6)).decode()
st.op({"op": "upload_sprite", "id": "a", "name": "ana.png", "data": data})
assert os.path.exists(os.path.join(d, "ana.png")), "debe guardarse junto al .vn"
assert st.model["characters"]["a"]["sprite"] == "ana.png", "y quedar asignado"
assert "ana.png" in st.assets(), "y aparecer en la lista de assets"
assert st.state()["can_undo"], "debe entrar en el historial"

st.op({"op": "select", "scene": "s", "step": 0})
l = st.stage("s", 0)["layers"][0]
assert (l["w"], l["h"]) == (4, 6), f"el escenario debe usar la imagen subida: {l}"

# no se escribe fuera de la carpeta del proyecto
st.op({"op": "upload_sprite", "id": "a", "name": "../fuga.png", "data": data})
assert not os.path.exists(os.path.join(d, "..", "fuga.png")), "path traversal"
print("UPLOAD GREEN")
