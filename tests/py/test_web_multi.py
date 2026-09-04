"""Varios pasos a la vez: pegar y borrar en un solo op (un solo undo)."""
import tempfile, os
from znt.web import server as ws
d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter a "Ana"\nscene s\n  a: uno\n  a: dos\n  a: tres\n  a: cuatro\n  end\n'
    'scene t\n  end\n')
st = ws.Studio(p)
txt = lambda sc="s": [x.get("text", x["op"]) for x in st.model["scenes"][sc]]

# pegar después del paso elegido (copias independientes)
st.op({"op": "select", "scene": "s", "step": 1})
clip = [{"op": "say", "who": "a", "text": "X"}, {"op": "say", "who": "a", "text": "Y"}]
st.op({"op": "paste_steps", "steps": clip})
assert txt() == ["uno", "dos", "X", "Y", "tres", "cuatro", "end"], txt()
assert st.state()["step"] == 3, "queda seleccionado el último pegado"
clip[0]["text"] = "mutado"
assert txt()[2] == "X", "lo pegado no comparte referencia con el portapapeles"
st.op({"op": "undo"})
assert txt() == ["uno", "dos", "tres", "cuatro", "end"], "un solo undo"

# pegar en otra escena (portapapeles entre escenas)
st.op({"op": "select", "scene": "t", "step": -1})
st.op({"op": "paste_steps", "steps": clip})
assert txt("t") == ["end", "mutado", "Y"], "sin paso elegido va al final"

# borrar varios
st.op({"op": "select", "scene": "s", "step": 0})
st.op({"op": "del_steps", "indices": [0, 2, 99]})
assert txt() == ["dos", "cuatro", "end"], txt()
assert 0 <= st.state()["step"] < 3
st.op({"op": "undo"})
assert txt() == ["uno", "dos", "tres", "cuatro", "end"]
r = st.op({"op": "paste_steps", "steps": [{"op": "nada"}]})
assert r.get("error"), "un paso inválido se rechaza"
print("MULTI GREEN")
