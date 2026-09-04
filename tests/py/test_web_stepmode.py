"""Play del editor es paso a paso: cada click ejecuta UN paso (el bug reportado:
seleccionar el fondo y que 'empiece desde el personaje')."""
import tempfile, os
from znt.web import server as ws

d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter c "Chofi"\nscene inicio\n  bg #123456\n  show c center\n  c: AAAA\n  end\n'
    'scene t\n  bg #000000\n  c: en t\n  end\n')
st = ws.Studio(p)
play = lambda: st.state()["play"]

st.op({"op": "select", "scene": "inicio", "step": 0})       # el fondo
st.op({"op": "play", "scene": "inicio", "step": 0})
pl = play()
assert pl["step"] == 0, f"arranca EN el fondo, no en el diálogo: {pl['step']}"
assert pl["bg"]["color"] == "#123456", "el fondo ya está"
assert pl["layers"] == [] and pl["say"] is None, "y todavía no hay personaje ni diálogo"

st.op({"op": "play_advance"})
pl = play()
assert pl["step"] == 1 and [l["id"] for l in pl["layers"]] == ["c"] and pl["say"] is None, "click: aparece el personaje"
st.op({"op": "play_advance"})
pl = play()
assert pl["step"] == 2 and pl["say"]["text"] == "AAAA", "click: el diálogo"
st.op({"op": "play_advance"})
pl = play()
assert pl["step"] == 3 and pl["done"], "click: end"
assert play()["say"] is None, "al terminar no queda el diálogo colgado"

# desde el medio: lo anterior aplicado, el paso elegido ejecutado
st.op({"op": "play", "scene": "inicio", "step": 2})
pl = play()
assert pl["step"] == 2 and pl["say"]["text"] == "AAAA" and [l["id"] for l in pl["layers"]] == ["c"]

# goto/choice: entra a la otra escena y ejecuta sólo su primer paso
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter c "Chofi"\nscene inicio\n  choice\n  - ir -> t\n'
    'scene t\n  bg #000000\n  c: en t\n  end\n')
st2 = ws.Studio(p)
st2.op({"op": "play", "scene": "inicio", "step": 0})
assert st2.state()["play"]["choices"]
st2.op({"op": "play_choose", "i": 0})
pl = st2.state()["play"]
assert (pl["scene"], pl["step"]) == ("t", 0) and pl["say"] is None, pl
print("STEPMODE GREEN")
