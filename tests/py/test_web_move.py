"""Reordenar arrastrando en el timeline: mover a una posición arbitraria."""
import tempfile, os
from znt.web import server as ws

d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter a "Ana"\nscene s\n'
    '  a: uno\n  a: dos\n  a: tres\n  a: cuatro\n  end\n')
st = ws.Studio(p)
txt = lambda: [s.get("text", s["op"]) for s in st.model["scenes"]["s"]]

st.op({"op": "select", "scene": "s", "step": 0})
st.op({"op": "move_step_to", "to": 2})                 # arrastrar 'uno' hasta el lugar 2
assert txt() == ["dos", "tres", "uno", "cuatro", "end"], txt()
assert st.state()["step"] == 2, "el paso movido queda seleccionado"
assert st.state()["can_undo"]

st.op({"op": "move_step_to", "to": 0})                 # y de vuelta al principio
assert txt() == ["uno", "dos", "tres", "cuatro", "end"], txt()

st.op({"op": "move_step_to", "to": 99})                # fuera de rango: no rompe
assert txt() == ["uno", "dos", "tres", "cuatro", "end"], txt()
print("MOVE GREEN")
