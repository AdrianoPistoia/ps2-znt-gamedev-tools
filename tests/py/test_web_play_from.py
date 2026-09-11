"""Play starts at the selected step and reports which step/scene it is at (step by step)."""
import tempfile, os
from znt.web import server as ws

d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter a "Ana"\ncharacter b "Leo"\n'
    'scene s\n  bg #000000\n  show a left\n  a: one\n  a: two\n  show b right\n  b: three\n'
    '  choice\n  - go -> t\n'
    'scene t\n  b: four\n  end\n')
st = ws.Studio(p)
play = lambda: st.state()["play"]

st.op({"op": "select", "scene": "s", "step": 3})
st.op({"op": "play", "scene": "s", "step": 3})
pl = play()
assert pl["say"]["text"] == "two" and (pl["scene"], pl["step"]) == ("s", 3)
assert [l["id"] for l in pl["layers"]] == ["a"], "the earlier show was applied, the later one was not"
st.op({"op": "play_advance"}); pl = play()
assert pl["step"] == 4 and sorted(l["id"] for l in pl["layers"]) == ["a", "b"] and pl["say"] is None, "one step: b appears"
st.op({"op": "play_advance"}); pl = play()
assert pl["say"]["text"] == "three" and pl["step"] == 5
st.op({"op": "play_advance"}); pl = play()
assert pl["choices"] and pl["step"] == 6, "stopped at the choice"
st.op({"op": "play_choose", "i": 0}); pl = play()
assert (pl["scene"], pl["step"]) == ("t", 0) and pl["say"]["text"] == "four"
st.op({"op": "play_advance"})
assert play()["done"] and play()["step"] == 1

st.op({"op": "play_stop"}); st.op({"op": "select", "scene": "s", "step": -1})
st.op({"op": "play", "scene": "s"})
assert play()["step"] == 0 and play()["say"] is None and play()["bg"]["color"] == "#000000", "no step selected: the background"
assert st.state()["scene"] == "s" and st.state()["step"] == -1
print("PLAY-FROM GREEN")
