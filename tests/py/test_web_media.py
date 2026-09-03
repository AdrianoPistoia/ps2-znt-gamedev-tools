"""Selectores de fondo y audio: listar por tipo y subir desde el sistema."""
import tempfile, os, base64
from znt import vn
from znt.web import server as ws

d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter a "Ana"\nscene s\n  bg #000000\n  bgm x.wav\n  a: hola\n  end\n')
for f in ("sala.png", "tema.wav", "notas.txt"):
    open(os.path.join(d, f), "wb").write(b"x")

assert vn.list_assets(d) == ["sala.png"], "por defecto: imágenes"
assert vn.list_assets(d, "audio") == ["tema.wav"], "audio filtrado"
assert vn.list_assets(d, "all") == ["sala.png", "tema.wav"], "ambos, sin basura"

st = ws.Studio(p)
assert st.assets("audio") == ["tema.wav"]

# subir un fondo desde el sistema y aplicarlo al paso bg seleccionado
st.op({"op": "select", "scene": "s", "step": 0})
st.op({"op": "upload", "name": "cielo.png", "data": base64.b64encode(b"png").decode(), "apply": "bg"})
assert os.path.exists(os.path.join(d, "cielo.png"))
assert st.model["scenes"]["s"][0]["spec"] == {"kind": "img", "file": "cielo.png"}, \
    st.model["scenes"]["s"][0]
assert st.state()["can_undo"]

# subir un audio y aplicarlo al paso bgm
st.op({"op": "select", "scene": "s", "step": 1})
st.op({"op": "upload", "name": "ost.wav", "data": base64.b64encode(b"wav").decode(), "apply": "file"})
assert st.model["scenes"]["s"][1]["file"] == "ost.wav"

# sin apply sólo copia el archivo
st.op({"op": "upload", "name": "otro.png", "data": ""})
assert os.path.exists(os.path.join(d, "otro.png")) and "otro.png" in st.assets()
print("MEDIA GREEN")
