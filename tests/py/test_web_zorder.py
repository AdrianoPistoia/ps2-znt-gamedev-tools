"""Z order from the web editor: bring to front / send to back."""
import tempfile, os
from znt.web import server as ws

d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter a "Ana"\ncharacter b "Leo"\ncharacter c "Cy"\n'
    'scene s\n  show a left\n  show b center\n  show c right\n  a: hello\n  end\n')
st = ws.Studio(p)
st.op({"op": "select", "scene": "s", "step": 3})

z = lambda: {l["id"]: l["z"] for l in st.stage("s", 3)["layers"]}
z0 = z()
assert z0["a"] < z0["b"] < z0["c"], f"by appearance: {z0}"

# 'a' to front: ends up with the highest z
st.op({"op": "select", "scene": "s", "step": 0})       # the show of 'a'
st.op({"op": "set_z", "id": "a", "front": True})
z1 = z()
assert z1["a"] > z1["b"] and z1["a"] > z1["c"], f"to front: {z1}"
assert st.model["scenes"]["s"][0]["z"] == z1["a"], "must be written into the show step"
assert st.state()["can_undo"], "must enter the history"

# 'a' to back: ends up with the lowest z (but above the background)
st.op({"op": "set_z", "id": "a", "front": False})
z2 = z()
assert z2["a"] < z2["b"] and z2["a"] < z2["c"], f"to back: {z2}"
assert z2["a"] >= 1, "must not end up behind the background"
print("ZORDER GREEN")
