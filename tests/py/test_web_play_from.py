"""Play arranca en el paso elegido y cuenta en qué paso/escena está."""
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

# desde el paso 3 ("a: dos"): lo anterior (bg, show a) ya está aplicado
st.op({"op": "select", "scene": "s", "step": 3})
st.op({"op": "play", "scene": "s", "step": 3})
pl = play()
assert pl["say"]["text"] == "dos", pl["say"]
assert (pl["scene"], pl["step"]) == ("s", 3), (pl["scene"], pl["step"])
assert [l["id"] for l in pl["layers"]] == ["a"], "el show de antes se aplicó, el de después no"

st.op({"op": "play_advance"})
pl = play()
assert pl["say"]["text"] == "tres" and pl["step"] == 5, (pl["say"], pl["step"])
assert sorted(l["id"] for l in pl["layers"]) == ["a", "b"]

st.op({"op": "play_advance"})
pl = play()
assert pl["choices"] and pl["step"] == 6, "parado en el choice"

# elegir salta de escena: el cursor lo dice
st.op({"op": "play_choose", "i": 0})
pl = play()
assert (pl["scene"], pl["step"]) == ("t", 0) and pl["say"]["text"] == "cuatro", (pl["scene"], pl["step"])
st.op({"op": "play_advance"})
assert play()["done"] and play()["step"] == 1

# sin paso elegido arranca del principio
st.op({"op": "play_stop"}); st.op({"op": "select", "scene": "s", "step": -1})
st.op({"op": "play", "scene": "s"})
assert play()["step"] == 2 and play()["say"]["text"] == "uno"

# la edición no se tocó
assert st.state()["scene"] == "s" and st.state()["step"] == -1
print("PLAY-FROM GREEN")
