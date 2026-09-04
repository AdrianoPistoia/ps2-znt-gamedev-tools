"""Explorador de archivos del server: listar y traer un archivo al proyecto."""
import tempfile, os
from znt.web import server as ws

root = tempfile.mkdtemp()
proj = os.path.join(root, "proj"); os.makedirs(proj)
otro = os.path.join(root, "fotos"); os.makedirs(otro)
os.makedirs(os.path.join(root, ".oculto"))
p = os.path.join(proj, "h.vn")
open(p, "w", encoding="utf-8").write('title: T\ncharacter a "Ana"\nscene s\n  bg #000\n  show a\n  bgm x\n  end\n')
for f in ("cara.png", "tema.wav", "otra.vn", "notas.txt"):
    open(os.path.join(otro, f), "wb").write(b"x")
st = ws.Studio(p)

r = st.browse(root, "any")
assert r["path"] == root and r["parent"] == os.path.dirname(root)
assert r["dirs"] == ["fotos", "proj"], r["dirs"]          # ordenadas, sin ocultas
assert r["home"] == os.path.expanduser("~")

assert st.browse(otro, "img")["files"] == ["cara.png"]
assert st.browse(otro, "audio")["files"] == ["tema.wav"]
assert st.browse(otro, "vn")["files"] == ["otra.vn"]
assert st.browse(otro, "any")["files"] == ["cara.png", "notas.txt", "otra.vn", "tema.wav"]

# una ruta que no existe no explota: cae en el home
assert st.browse("/no/existe/nada", "any")["path"] == os.path.expanduser("~")
# un archivo como ruta: se abre su carpeta y queda marcado
r = st.browse(os.path.join(otro, "cara.png"), "img")
assert r["path"] == otro and r["pick"] == "cara.png"

# traer un archivo de otra carpeta al proyecto (copia + asigna)
st.op({"op": "select", "scene": "s", "step": 1})
st.op({"op": "import_asset", "path": os.path.join(otro, "cara.png"), "id": "a"})
assert os.path.exists(os.path.join(proj, "cara.png")), "se copia al lado del .vn"
assert st.model["characters"]["a"]["sprite"] == "cara.png"
assert st.state()["can_undo"]

st.op({"op": "select", "scene": "s", "step": 2})
st.op({"op": "import_asset", "path": os.path.join(otro, "tema.wav"), "apply": "file"})
assert st.model["scenes"]["s"][2]["file"] == "tema.wav"
assert os.path.exists(os.path.join(proj, "tema.wav"))

r = st.op({"op": "import_asset", "path": os.path.join(otro, "no-esta.png"), "id": "a"})
assert r.get("error"), "si no existe, se avisa"
print("BROWSE GREEN")
