"""add_step con props: un solo op (y un solo undo) para el diálogo rápido."""
import tempfile, os
from znt.web import server as ws
d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write('title: T\ncharacter a "Ana"\ncharacter b "Leo"\nscene s\n  show a\n  end\n')
st = ws.Studio(p)
st.op({"op": "select", "scene": "s", "step": 0})
st.op({"op": "add_step", "kind": "say", "props": {"who": "b", "text": "rápido"}})
s1 = st.model["scenes"]["s"][1]
assert s1 == {"op": "say", "who": "b", "text": "rápido"}, s1
st.op({"op": "undo"})
assert len(st.model["scenes"]["s"]) == 2, "un solo paso de historial"
print("ADDSTEP GREEN")
