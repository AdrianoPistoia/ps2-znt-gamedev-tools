"""Unsaved changes, autosave, deleting a scene and a character."""
import tempfile, os, time
from znt.web import server as ws

d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter a "Ana"\ncharacter b "Leo"\nscene s\n  show a\n  a: hello\n  goto t\n'
    'scene t\n  end\nscene u\n  end\n')
st = ws.Studio(p)

# --- dirty: clean when just opened; dirty after editing; clean after saving
assert st.state()["dirty"] is False
st.op({"op": "select", "scene": "s", "step": 1})
st.op({"op": "set_props", "props": {"text": "bye"}})
assert st.state()["dirty"] is True, "editing makes it dirty"
st.op({"op": "select", "scene": "s", "step": 0})
assert st.state()["dirty"] is True, "selecting does not clean it"
st.op({"op": "save"})
assert st.state()["dirty"] is False, "saving cleans it"
st.op({"op": "undo"})
assert st.state()["dirty"] is True, "undo counts as a change too"

# --- autosave: every change leaves a copy next to the .vn, cleared on save
auto = ws.autosave_path(p)
assert os.path.exists(auto), "there is an autosave after a change"
assert "bye" not in open(auto, encoding="utf-8").read(), "reflects the current (undone) state"
st.op({"op": "save"})
assert not os.path.exists(auto), "saving deletes the autosave"

# on open, if there is an autosave newer than the .vn, it is reported
st.op({"op": "set_props", "props": {"text": "another"}})
assert os.path.exists(auto)
time.sleep(0.02)
st2 = ws.Studio(p)
assert any("autosave" in x for x in st2.problems), st2.problems

# --- delete scene
st.op({"op": "select", "scene": "u", "step": -1})
st.op({"op": "del_scene"})
assert "u" not in st.model["scenes"] and "u" not in st.model["order"]
assert st.state()["scene"] in st.model["scenes"], "another scene stays selected"
assert st.state()["can_undo"]
r = st.op({"op": "select", "scene": "t", "step": -1}); r = st.op({"op": "del_scene"})
assert "t" not in st.model["scenes"], "deleting a referenced scene is allowed (validate reports it)"
assert any("t" in x for x in ws.vn.validate(st.model)), "broken goto reported"
st.op({"op": "select", "scene": "s", "step": -1})
r = st.op({"op": "del_scene"})
assert r.get("error") and "s" in st.model["scenes"], "the last scene cannot be deleted"

# --- delete character: if in use, refuses and says where
r = st.op({"op": "del_char", "id": "a"})
assert r.get("error") and "a" in st.model["characters"], r.get("error")
assert "2 step" in r["error"], r["error"]
r = st.op({"op": "del_char", "id": "b"})
assert not r.get("error") and "b" not in st.model["characters"]
r = st.op({"op": "del_char", "id": "narrator"})
assert r.get("error"), "the narrator cannot be deleted"
print("LIFECYCLE GREEN")
