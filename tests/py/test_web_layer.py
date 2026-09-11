"""Editing a layer from the viewport (zoom/opacity) writes into its `show`."""
import tempfile, os
from znt.web import server as ws

d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter a "Ana"\nscene s\n  show a center\n  a: hello\n  a: bye\n  end\n')
st = ws.Studio(p)
st.op({"op": "select", "scene": "s", "step": 2})          # two steps after the show

st.op({"op": "set_layer", "id": "a", "props": {"zoom": 150.4, "opacity": 60}})
show = st.model["scenes"]["s"][0]
assert show["zoom"] == 150 and show["opacity"] == 60, show
assert st.stage("s", 2)["layers"][0]["zoom"] == 150, "the stage reflects it"
assert st.state()["can_undo"]

st.op({"op": "set_layer", "id": "a", "props": {"tint": "#ff0000"}})
assert st.model["scenes"]["s"][0]["tint"] == "#ff0000"
st.op({"op": "set_layer", "id": "nobody", "props": {"zoom": 10}})   # does not blow up
print("LAYER GREEN")
