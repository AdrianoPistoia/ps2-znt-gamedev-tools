"""Reordering by dragging in the timeline: move to an arbitrary position."""
import tempfile, os
from znt.web import server as ws

d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter a "Ana"\nscene s\n'
    '  a: one\n  a: two\n  a: three\n  a: four\n  end\n')
st = ws.Studio(p)
txt = lambda: [s.get("text", s["op"]) for s in st.model["scenes"]["s"]]

st.op({"op": "select", "scene": "s", "step": 0})
st.op({"op": "move_step_to", "to": 2})                 # drag 'one' to slot 2
assert txt() == ["two", "three", "one", "four", "end"], txt()
assert st.state()["step"] == 2, "the moved step stays selected"
assert st.state()["can_undo"]

st.op({"op": "move_step_to", "to": 0})                 # and back to the start
assert txt() == ["one", "two", "three", "four", "end"], txt()

st.op({"op": "move_step_to", "to": 99})                # out of range: does not break
assert txt() == ["one", "two", "three", "four", "end"], txt()
print("MOVE GREEN")
