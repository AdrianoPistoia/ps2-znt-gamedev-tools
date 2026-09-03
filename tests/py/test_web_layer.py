"""Editar una capa desde el viewport (zoom/opacidad) escribe en su `show`."""
import tempfile, os
from znt.web import server as ws

d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter a "Ana"\nscene s\n  show a center\n  a: hola\n  a: chau\n  end\n')
st = ws.Studio(p)
st.op({"op": "select", "scene": "s", "step": 2})          # dos pasos después del show

st.op({"op": "set_layer", "id": "a", "props": {"zoom": 150.4, "opacity": 60}})
show = st.model["scenes"]["s"][0]
assert show["zoom"] == 150 and show["opacity"] == 60, show
assert st.stage("s", 2)["layers"][0]["zoom"] == 150, "el escenario lo refleja"
assert st.state()["can_undo"]

st.op({"op": "set_layer", "id": "a", "props": {"tint": "#ff0000"}})
assert st.model["scenes"]["s"][0]["tint"] == "#ff0000"
st.op({"op": "set_layer", "id": "nadie", "props": {"zoom": 10}})   # no explota
print("LAYER GREEN")
