"""Orden Z desde el editor web: traer al frente / mandar al fondo."""
import tempfile, os
from znt.web import server as ws

d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter a "Ana"\ncharacter b "Leo"\ncharacter c "Cy"\n'
    'scene s\n  show a left\n  show b center\n  show c right\n  a: hola\n  end\n')
st = ws.Studio(p)
st.op({"op": "select", "scene": "s", "step": 3})

z = lambda: {l["id"]: l["z"] for l in st.stage("s", 3)["layers"]}
z0 = z()
assert z0["a"] < z0["b"] < z0["c"], f"por aparición: {z0}"

# 'a' al frente: queda con el z más alto
st.op({"op": "select", "scene": "s", "step": 0})       # el show de 'a'
st.op({"op": "set_z", "id": "a", "front": True})
z1 = z()
assert z1["a"] > z1["b"] and z1["a"] > z1["c"], f"al frente: {z1}"
assert st.model["scenes"]["s"][0]["z"] == z1["a"], "debe escribirse en el paso show"
assert st.state()["can_undo"], "debe entrar en el historial"

# 'a' al fondo: queda con el z más bajo (pero por encima del fondo)
st.op({"op": "set_z", "id": "a", "front": False})
z2 = z()
assert z2["a"] < z2["b"] and z2["a"] < z2["c"], f"al fondo: {z2}"
assert z2["a"] >= 1, "no debe quedar detrás del fondo"
print("ZORDER GREEN")
