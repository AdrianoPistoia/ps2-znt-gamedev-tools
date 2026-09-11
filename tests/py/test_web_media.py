"""Background and audio pickers: list by type and upload from the system."""
import tempfile, os, base64
from znt import vn
from znt.web import server as ws

d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter a "Ana"\nscene s\n  bg #000000\n  bgm x.wav\n  a: hello\n  end\n')
for f in ("room.png", "theme.wav", "notes.txt"):
    open(os.path.join(d, f), "wb").write(b"x")

assert vn.list_assets(d) == ["room.png"], "default: images"
assert vn.list_assets(d, "audio") == ["theme.wav"], "audio filtered"
assert vn.list_assets(d, "all") == ["room.png", "theme.wav"], "both, without junk"

st = ws.Studio(p)
assert st.assets("audio") == ["theme.wav"]

# upload a background from the system and apply it to the selected bg step
st.op({"op": "select", "scene": "s", "step": 0})
st.op({"op": "upload", "name": "sky.png", "data": base64.b64encode(b"png").decode(), "apply": "bg"})
assert os.path.exists(os.path.join(d, "sky.png"))
assert st.model["scenes"]["s"][0]["spec"] == {"kind": "img", "file": "sky.png"}, \
    st.model["scenes"]["s"][0]
assert st.state()["can_undo"]

# upload an audio file and apply it to the bgm step
st.op({"op": "select", "scene": "s", "step": 1})
st.op({"op": "upload", "name": "ost.wav", "data": base64.b64encode(b"wav").decode(), "apply": "file"})
assert st.model["scenes"]["s"][1]["file"] == "ost.wav"

# without apply it only copies the file
st.op({"op": "upload", "name": "other.png", "data": ""})
assert os.path.exists(os.path.join(d, "other.png")) and "other.png" in st.assets()
print("MEDIA GREEN")
