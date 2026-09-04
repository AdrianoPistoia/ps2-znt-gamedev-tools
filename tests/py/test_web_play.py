"""Play desde el editor (paso a paso) y volver a editar sin tocar nada."""
import tempfile, os
from znt.web import server as ws

d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter a "Ana"\nscene s\n  bg #101828\n  show a left\n  a: uno\n  a: dos\n'
    '  choice\n  - ir -> t\nscene t\n  a: tres\n  end\n')
st = ws.Studio(p)
st.op({"op": "select", "scene": "s", "step": 2})
r = st.op({"op": "play", "scene": "s"})
pl = r["play"]
assert pl["playing"] and pl["step"] == 2 and pl["say"]["text"] == "uno", "arranca en el paso elegido"
assert pl["bg"]["color"] == "#101828" and [l["id"] for l in pl["layers"]] == ["a"]
pl = st.op({"op": "play_advance"})["play"]
assert pl["say"]["text"] == "dos" and pl["step"] == 3
pl = st.op({"op": "play_advance"})["play"]
assert pl["say"] is None and pl["choices"][0]["label"] == "ir", "llega al choice"
pl = st.op({"op": "play_choose", "i": 0})["play"]
assert pl["scene"] == "t" and pl["say"]["text"] == "tres", "elegir salta de escena y muestra su primer paso"
pl = st.op({"op": "play_advance"})["play"]
assert pl["done"], "end"
r = st.op({"op": "play_stop"})
assert r["play"] is None and r["scene"] == "s" and r["step"] == 2, "salir no toca la edición"
print("PLAY GREEN")
