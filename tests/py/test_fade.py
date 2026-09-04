"""Transición de fondo: `bg X fade=ms` hace crossfade con el fondo anterior."""
from znt import vn
from znt.vnstudio import VNRuntime

m = vn.parse('title: T\ncharacter a "A"\nscene s\n  bg #000000\n  a: uno\n  bg #ffffff fade=400\n  a: dos\n  end\n')
st = m["scenes"]["s"]
assert st[0] == {"op": "bg", "spec": {"kind": "solid", "color": "#000000"}}, "sin fade, igual que antes"
assert st[2]["fade"] == 400, st[2]
assert vn.parse(vn.to_text(m))["scenes"]["s"] == st, "round-trip"
assert vn.default_step("bg", m).get("fade") is None

rt = VNRuntime(vn._link_choices(m), ".")
rt.preview_upto("s", 2, settle=False)               # recién aplicado el bg con fade
bg = rt.stage["bg"]
assert bg.opacity < 100, f"el fondo nuevo arranca transparente: {bg.opacity}"
assert "bg_prev" in rt.stage and rt.stage["bg_prev"].show, "el anterior sigue abajo mientras dura el fade"
assert rt.stage["bg_prev"].level < bg.level
rt.settle()
assert rt.stage["bg"].opacity == 100 and not rt.stage.get("bg_prev", None) or not rt.stage["bg_prev"].show, \
    "al terminar: fondo nuevo opaco y el viejo se va"
rt.preview_upto("s", 2)                              # el editor (settle=True) lo ve resuelto
assert rt.stage["bg"].opacity == 100

# el fondo con fade es una capa animada: el frame no explota y compone
fb = rt.frame(); assert len(fb.buf) == rt.W * rt.H * 3

# player HTML: el fade viaja al paso y hay lógica para aplicarlo
html = vn.render_html(vn._link_choices(m), ".")
assert '"fade": 400' in html or '"fade":400' in html
assert "s.fade" in html, "el player usa el fade"
print("FADE GREEN")
