"""Cambios sin guardar, autosave, borrar escena y personaje."""
import tempfile, os, time
from znt.web import server as ws

d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter a "Ana"\ncharacter b "Leo"\nscene s\n  show a\n  a: hola\n  goto t\n'
    'scene t\n  end\nscene u\n  end\n')
st = ws.Studio(p)

# --- dirty: recién abierto, limpio; tras editar, sucio; tras guardar, limpio
assert st.state()["dirty"] is False
st.op({"op": "select", "scene": "s", "step": 1})
st.op({"op": "set_props", "props": {"text": "chau"}})
assert st.state()["dirty"] is True, "editar ensucia"
st.op({"op": "select", "scene": "s", "step": 0})
assert st.state()["dirty"] is True, "seleccionar no limpia"
st.op({"op": "save"})
assert st.state()["dirty"] is False, "guardar limpia"
st.op({"op": "undo"})
assert st.state()["dirty"] is True, "deshacer también cuenta como cambio"

# --- autosave: cada cambio deja una copia al lado del .vn, y se limpia al guardar
auto = ws.autosave_path(p)
assert os.path.exists(auto), "hay autosave tras un cambio"
assert "chau" not in open(auto, encoding="utf-8").read(), "refleja el estado actual (deshecho)"
st.op({"op": "save"})
assert not os.path.exists(auto), "guardar borra el autosave"

# al abrir, si hay un autosave más nuevo que el .vn, se avisa
st.op({"op": "set_props", "props": {"text": "otra"}})
assert os.path.exists(auto)
time.sleep(0.02)
st2 = ws.Studio(p)
assert any("autosave" in x for x in st2.problems), st2.problems

# --- borrar escena
st.op({"op": "select", "scene": "u", "step": -1})
st.op({"op": "del_scene"})
assert "u" not in st.model["scenes"] and "u" not in st.model["order"]
assert st.state()["scene"] in st.model["scenes"], "queda otra escena seleccionada"
assert st.state()["can_undo"]
r = st.op({"op": "select", "scene": "t", "step": -1}); r = st.op({"op": "del_scene"})
assert "t" not in st.model["scenes"], "borrar una escena referenciada se permite (validar lo reporta)"
assert any("t" in x for x in ws.vn.validate(st.model)), "goto roto reportado"
st.op({"op": "select", "scene": "s", "step": -1})
r = st.op({"op": "del_scene"})
assert r.get("error") and "s" in st.model["scenes"], "la última escena no se borra"

# --- borrar personaje: si está en uso, se niega y dice dónde
r = st.op({"op": "del_char", "id": "a"})
assert r.get("error") and "a" in st.model["characters"], r.get("error")
assert "2 paso" in r["error"] or "pasos" in r["error"], r["error"]
r = st.op({"op": "del_char", "id": "b"})
assert not r.get("error") and "b" not in st.model["characters"]
r = st.op({"op": "del_char", "id": "narrator"})
assert r.get("error"), "el narrador no se borra"
print("LIFECYCLE GREEN")
