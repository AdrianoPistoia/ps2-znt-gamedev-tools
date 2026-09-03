"""Play: reproducir la escena desde el editor web (avanzar y elegir)."""
import tempfile, os
from znt.web import server as ws

d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter a "Ana" color=#e79ab0\n'
    'scene uno\n  bg grad:#101828,#304060\n  show a left\n  a: primera\n  a: segunda\n'
    '  choice\n    - Ir -> dos\n    - Fin -> tres\n'
    'scene dos\n  a: elegiste ir\n  end\n'
    'scene tres\n  * fin\n  end\n')
st = ws.Studio(p)

# arranca la reproducción: estado con capas + primer diálogo
s = st.op({"op": "play", "scene": "uno"})
pl = s["play"]
assert pl and pl["playing"] and pl["say"]["text"] == "primera", pl
assert any(l["id"] == "a" for l in pl["layers"]), pl["layers"]
assert pl["bg"]["kind"] == "grad"

# avanzar
pl = st.op({"op": "play_advance"})["play"]
assert pl["say"]["text"] == "segunda", pl["say"]

# llega al choice
pl = st.op({"op": "play_advance"})["play"]
assert len(pl["choices"]) == 2 and pl["say"] is None, pl

# elegir la primera opción salta a la escena "dos"
pl = st.op({"op": "play_choose", "i": 0})["play"]
assert pl["say"]["text"] == "elegiste ir", pl["say"]

# el final marca done
pl = st.op({"op": "play_advance"})["play"]
assert pl["done"], pl

# salir de play no toca el modelo ni la selección de edición
before = st.scene, st.step, len(st.model["scenes"])
st.op({"op": "play_stop"})
assert st.op({"op": "select", "scene": "uno", "step": -1})["play"] is None
assert (st.scene, st.step, len(st.model["scenes"])) == ("uno", -1, before[2])
print("PLAY GREEN")
