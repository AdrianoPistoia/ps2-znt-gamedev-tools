"""Play arranca en el paso elegido y cuenta en qué paso/escena está (paso a paso)."""
import tempfile, os
from znt.web import server as ws

d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter a "Ana"\ncharacter b "Leo"\n'
    'scene s\n  bg #000000\n  show a left\n  a: uno\n  a: dos\n  show b right\n  b: tres\n'
    '  choice\n  - ir -> t\n'
    'scene t\n  b: cuatro\n  end\n')
st = ws.Studio(p)
play = lambda: st.state()["play"]

st.op({"op": "select", "scene": "s", "step": 3})
st.op({"op": "play", "scene": "s", "step": 3})
pl = play()
assert pl["say"]["text"] == "dos" and (pl["scene"], pl["step"]) == ("s", 3)
assert [l["id"] for l in pl["layers"]] == ["a"], "el show de antes se aplicó, el de después no"
st.op({"op": "play_advance"}); pl = play()
assert pl["step"] == 4 and sorted(l["id"] for l in pl["layers"]) == ["a", "b"] and pl["say"] is None, "un paso: aparece b"
st.op({"op": "play_advance"}); pl = play()
assert pl["say"]["text"] == "tres" and pl["step"] == 5
st.op({"op": "play_advance"}); pl = play()
assert pl["choices"] and pl["step"] == 6, "parado en el choice"
st.op({"op": "play_choose", "i": 0}); pl = play()
assert (pl["scene"], pl["step"]) == ("t", 0) and pl["say"]["text"] == "cuatro"
st.op({"op": "play_advance"})
assert play()["done"] and play()["step"] == 1

st.op({"op": "play_stop"}); st.op({"op": "select", "scene": "s", "step": -1})
st.op({"op": "play", "scene": "s"})
assert play()["step"] == 0 and play()["say"] is None and play()["bg"]["color"] == "#000000", "sin paso elegido: el fondo"
assert st.state()["scene"] == "s" and st.state()["step"] == -1
print("PLAY-FROM GREEN")
