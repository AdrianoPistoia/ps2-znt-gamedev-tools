"""Nuevo / Abrir proyecto desde el editor web."""
import tempfile, os
from znt.web import server as ws

d1, d2 = tempfile.mkdtemp(), tempfile.mkdtemp()
p1 = os.path.join(d1, "uno.vn"); p2 = os.path.join(d2, "dos.vn")
open(p1, "w", encoding="utf-8").write('title: Uno\ncharacter a "Ana"\nscene s\n  a: hola\n  end\n')
open(p2, "w", encoding="utf-8").write('title: Dos\ncharacter b "Leo"\nscene otra\n  b: chau\n  end\n')

st = ws.Studio(p1)
st.op({"op": "add_step", "kind": "say"})           # ensuciar el historial
assert st.state()["can_undo"]

# abrir otro proyecto: reemplaza modelo, base y ruta; resetea selección e historial
st.op({"op": "open_project", "path": p2})
assert st.model["title"] == "Dos", st.model["title"]
assert st.path == p2 and st.base == os.path.dirname(os.path.abspath(p2)), (st.path, st.base)
assert st.scene == "otra" and st.step == -1, (st.scene, st.step)
assert not st.state()["can_undo"], "el historial debe resetearse al abrir"
assert st.rt.model is st.model, "el runtime debe apuntar al modelo nuevo"

# el stage del proyecto nuevo funciona
sg = st.stage("otra", 0)
assert sg["say"]["text"] == "chau", sg["say"]

# proyecto nuevo en blanco
st.op({"op": "new_project"})
assert st.model["title"] == "Nueva VN" and st.path is None
assert len(st.model["scenes"]) == 1 and st.step == -1
assert not st.state()["can_undo"]
print("PROJECT GREEN")
