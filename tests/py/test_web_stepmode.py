"""Editor Play is step by step: each click runs ONE step (the reported bug:
select the background and it 'starts from the character')."""
import tempfile, os
from znt.web import server as ws

d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter c "Chofi"\nscene start\n  bg #123456\n  show c center\n  c: AAAA\n  end\n'
    'scene t\n  bg #000000\n  c: in t\n  end\n')
st = ws.Studio(p)
play = lambda: st.state()["play"]

st.op({"op": "select", "scene": "start", "step": 0})       # the background
st.op({"op": "play", "scene": "start", "step": 0})
pl = play()
assert pl["step"] == 0, f"starts AT the background, not at the dialogue: {pl['step']}"
assert pl["bg"]["color"] == "#123456", "the background is already there"
assert pl["layers"] == [] and pl["say"] is None, "and no character or dialogue yet"

st.op({"op": "play_advance"})
pl = play()
assert pl["step"] == 1 and [l["id"] for l in pl["layers"]] == ["c"] and pl["say"] is None, "click: the character appears"
st.op({"op": "play_advance"})
pl = play()
assert pl["step"] == 2 and pl["say"]["text"] == "AAAA", "click: the dialogue"
st.op({"op": "play_advance"})
pl = play()
assert pl["step"] == 3 and pl["done"], "click: end"
assert play()["say"] is None, "no dialogue left hanging when it ends"

# from the middle: earlier steps applied, the selected one executed
st.op({"op": "play", "scene": "start", "step": 2})
pl = play()
assert pl["step"] == 2 and pl["say"]["text"] == "AAAA" and [l["id"] for l in pl["layers"]] == ["c"]

# goto/choice: enters the other scene and runs only its first step
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter c "Chofi"\nscene start\n  choice\n  - go -> t\n'
    'scene t\n  bg #000000\n  c: in t\n  end\n')
st2 = ws.Studio(p)
st2.op({"op": "play", "scene": "start", "step": 0})
assert st2.state()["play"]["choices"]
st2.op({"op": "play_choose", "i": 0})
pl = st2.state()["play"]
assert (pl["scene"], pl["step"]) == ("t", 0) and pl["say"] is None, pl
print("STEPMODE GREEN")
