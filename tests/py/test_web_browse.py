"""Server-side file browser: list and bring a file into the project."""
import tempfile, os
from znt.web import server as ws

root = tempfile.mkdtemp()
proj = os.path.join(root, "proj"); os.makedirs(proj)
other = os.path.join(root, "photos"); os.makedirs(other)
os.makedirs(os.path.join(root, ".hidden"))
p = os.path.join(proj, "h.vn")
open(p, "w", encoding="utf-8").write('title: T\ncharacter a "Ana"\nscene s\n  bg #000\n  show a\n  bgm x\n  end\n')
for f in ("face.png", "theme.wav", "other.vn", "notes.txt"):
    open(os.path.join(other, f), "wb").write(b"x")
st = ws.Studio(p)

r = st.browse(root, "any")
assert r["path"] == root and r["parent"] == os.path.dirname(root)
assert r["dirs"] == ["photos", "proj"], r["dirs"]          # sorted, hidden ones excluded
assert r["home"] == os.path.expanduser("~")

assert st.browse(other, "img")["files"] == ["face.png"]
assert st.browse(other, "audio")["files"] == ["theme.wav"]
assert st.browse(other, "vn")["files"] == ["other.vn"]
assert st.browse(other, "any")["files"] == ["face.png", "notes.txt", "other.vn", "theme.wav"]

# a path that does not exist does not blow up: falls back to home
assert st.browse("/does/not/exist", "any")["path"] == os.path.expanduser("~")
# a file as the path: its folder opens and the file is marked
r = st.browse(os.path.join(other, "face.png"), "img")
assert r["path"] == other and r["pick"] == "face.png"

# bring a file from another folder into the project (copy + assign)
st.op({"op": "select", "scene": "s", "step": 1})
st.op({"op": "import_asset", "path": os.path.join(other, "face.png"), "id": "a"})
assert os.path.exists(os.path.join(proj, "face.png")), "copied next to the .vn"
assert st.model["characters"]["a"]["sprite"] == "face.png"
assert st.state()["can_undo"]

st.op({"op": "select", "scene": "s", "step": 2})
st.op({"op": "import_asset", "path": os.path.join(other, "theme.wav"), "apply": "file"})
assert st.model["scenes"]["s"][2]["file"] == "theme.wav"
assert os.path.exists(os.path.join(proj, "theme.wav"))

r = st.op({"op": "import_asset", "path": os.path.join(other, "missing.png"), "id": "a"})
assert r.get("error"), "if it does not exist, it is reported"
print("BROWSE GREEN")
