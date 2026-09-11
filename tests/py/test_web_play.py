"""Play from the editor (step by step) and back to editing without touching anything."""
import tempfile, os
from znt.web import server as ws

d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter a "Ana"\nscene s\n  bg #101828\n  show a left\n  a: one\n  a: two\n'
    '  choice\n  - go -> t\nscene t\n  a: three\n  end\n')
st = ws.Studio(p)
st.op({"op": "select", "scene": "s", "step": 2})
r = st.op({"op": "play", "scene": "s"})
pl = r["play"]
assert pl["playing"] and pl["step"] == 2 and pl["say"]["text"] == "one", "starts at the selected step"
assert pl["bg"]["color"] == "#101828" and [l["id"] for l in pl["layers"]] == ["a"]
pl = st.op({"op": "play_advance"})["play"]
assert pl["say"]["text"] == "two" and pl["step"] == 3
pl = st.op({"op": "play_advance"})["play"]
assert pl["say"] is None and pl["choices"][0]["label"] == "go", "reaches the choice"
pl = st.op({"op": "play_choose", "i": 0})["play"]
assert pl["scene"] == "t" and pl["say"]["text"] == "three", "choosing jumps scene and shows its first step"
pl = st.op({"op": "play_advance"})["play"]
assert pl["done"], "end"
r = st.op({"op": "play_stop"})
assert r["play"] is None and r["scene"] == "s" and r["step"] == 2, "leaving does not touch the edit state"
print("PLAY GREEN")
