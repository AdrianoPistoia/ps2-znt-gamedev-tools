"""New / Open project from the web editor."""
import tempfile, os
from znt.web import server as ws

d1, d2 = tempfile.mkdtemp(), tempfile.mkdtemp()
p1 = os.path.join(d1, "one.vn"); p2 = os.path.join(d2, "two.vn")
open(p1, "w", encoding="utf-8").write('title: One\ncharacter a "Ana"\nscene s\n  a: hello\n  end\n')
open(p2, "w", encoding="utf-8").write('title: Two\ncharacter b "Leo"\nscene other\n  b: bye\n  end\n')

st = ws.Studio(p1)
st.op({"op": "add_step", "kind": "say"})           # dirty the history
assert st.state()["can_undo"]

# open another project: replaces model, base and path; resets selection and history
st.op({"op": "open_project", "path": p2})
assert st.model["title"] == "Two", st.model["title"]
assert st.path == p2 and st.base == os.path.dirname(os.path.abspath(p2)), (st.path, st.base)
assert st.scene == "other" and st.step == -1, (st.scene, st.step)
assert not st.state()["can_undo"], "the history must reset on open"
assert st.rt.model is st.model, "the runtime must point at the new model"

# the new project's stage works
sg = st.stage("other", 0)
assert sg["say"]["text"] == "bye", sg["say"]

# new blank project
st.op({"op": "new_project"})
assert st.model["title"] == "New VN" and st.path is None
assert len(st.model["scenes"]) == 1 and st.step == -1
assert not st.state()["can_undo"]
print("PROJECT GREEN")
