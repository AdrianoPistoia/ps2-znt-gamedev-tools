"""Background transition: `bg X fade=ms` crossfades with the previous background."""
from znt import vn
from znt.vnstudio import VNRuntime

m = vn.parse('title: T\ncharacter a "A"\nscene s\n  bg #000000\n  a: uno\n  bg #ffffff fade=400\n  a: dos\n  end\n')
st = m["scenes"]["s"]
assert st[0] == {"op": "bg", "spec": {"kind": "solid", "color": "#000000"}}, "no fade, same as before"
assert st[2]["fade"] == 400, st[2]
assert vn.parse(vn.to_text(m))["scenes"]["s"] == st, "round-trip"
assert vn.default_step("bg", m).get("fade") is None

rt = VNRuntime(vn._link_choices(m), ".")
rt.preview_upto("s", 2, settle=False)               # the bg with fade was just applied
bg = rt.stage["bg"]
assert bg.opacity < 100, f"the new background starts transparent: {bg.opacity}"
assert "bg_prev" in rt.stage and rt.stage["bg_prev"].show, "the previous one stays underneath while the fade lasts"
assert rt.stage["bg_prev"].level < bg.level
rt.settle()
assert rt.stage["bg"].opacity == 100 and not rt.stage.get("bg_prev", None) or not rt.stage["bg_prev"].show, \
    "when done: new background opaque and the old one goes away"
rt.preview_upto("s", 2)                              # the editor (settle=True) sees it resolved
assert rt.stage["bg"].opacity == 100

# the fading background is an animated layer: the frame does not blow up and composes
fb = rt.frame(); assert len(fb.buf) == rt.W * rt.H * 3

# HTML player: the fade travels with the step and there is logic to apply it
html = vn.render_html(vn._link_choices(m), ".")
assert '"fade": 400' in html or '"fade":400' in html
assert "s.fade" in html, "the player uses the fade"
print("FADE GREEN")
