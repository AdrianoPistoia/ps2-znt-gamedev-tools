"""Several steps at once: paste and delete in a single op (a single undo)."""
import tempfile, os
from znt.web import server as ws
d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter a "Ana"\nscene s\n  a: one\n  a: two\n  a: three\n  a: four\n  end\n'
    'scene t\n  end\n')
st = ws.Studio(p)
txt = lambda sc="s": [x.get("text", x["op"]) for x in st.model["scenes"][sc]]

# paste after the selected step (independent copies)
st.op({"op": "select", "scene": "s", "step": 1})
clip = [{"op": "say", "who": "a", "text": "X"}, {"op": "say", "who": "a", "text": "Y"}]
st.op({"op": "paste_steps", "steps": clip})
assert txt() == ["one", "two", "X", "Y", "three", "four", "end"], txt()
assert st.state()["step"] == 3, "the last pasted step stays selected"
clip[0]["text"] = "mutated"
assert txt()[2] == "X", "pasted steps do not share a reference with the clipboard"
st.op({"op": "undo"})
assert txt() == ["one", "two", "three", "four", "end"], "a single undo"

# paste into another scene (clipboard across scenes)
st.op({"op": "select", "scene": "t", "step": -1})
st.op({"op": "paste_steps", "steps": clip})
assert txt("t") == ["end", "mutated", "Y"], "with no step selected it goes at the end"

# delete several
st.op({"op": "select", "scene": "s", "step": 0})
st.op({"op": "del_steps", "indices": [0, 2, 99]})
assert txt() == ["two", "four", "end"], txt()
assert 0 <= st.state()["step"] < 3
st.op({"op": "undo"})
assert txt() == ["one", "two", "three", "four", "end"]
r = st.op({"op": "paste_steps", "steps": [{"op": "nothing"}]})
assert r.get("error"), "an invalid step is rejected"
print("MULTI GREEN")
