"""Editing characters from the web: rename id, display name and colour."""
import tempfile, os
from znt.web import server as ws

d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter a "Ana"\nscene s\n  show a\n  a: hello\n  end\n')
st = ws.Studio(p)

st.op({"op": "rename_char", "old": "a", "new": "ana"})
m = st.model
assert "ana" in m["characters"] and "a" not in m["characters"]
assert m["scenes"]["s"][0]["id"] == "ana" and m["scenes"]["s"][1]["who"] == "ana"
assert st.state()["can_undo"]

# id taken: does not break the model
st.op({"op": "add_char", "id": "leo", "name": "Leo"})
st.op({"op": "rename_char", "old": "ana", "new": "leo"})
assert m["characters"]["leo"]["name"] == "Leo" and "ana" in m["characters"]

# display name and colour
st.op({"op": "set_char", "id": "ana", "name": "Ana Ruiz", "color": "#ff0000"})
assert m["characters"]["ana"] == {"name": "Ana Ruiz", "color": "#ff0000"}
st.op({"op": "select", "scene": "s", "step": 1})
assert st.stage("s", 1)["say"]["name"] == "Ana Ruiz", "the stage uses the new name"

st.op({"op": "undo"})
assert m["characters"]["ana"]["name"] == "Ana"
print("CHAR GREEN")
