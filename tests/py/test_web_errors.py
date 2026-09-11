"""Nothing silent: an unknown op or an unreadable asset gets REPORTED."""
import tempfile, os, base64
from znt.web import server as ws

d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter a "Ana"\nscene s\n  show a\n  a: hello\n  end\n')
st = ws.Studio(p)
before = repr(st.model)

# 1) op that does not exist (e.g. an old server against a new UI)
r = st.op({"op": "upload_whatever", "id": "a"})
assert "error" in r and "upload_whatever" in r["error"], r.get("error")
assert repr(st.model) == before, "must not touch the model"
assert r.get("model"), "still returns the full state, does not break the UI"

# 2) image the reader does not understand: placeholder + warning naming the file
open(os.path.join(d, "broken.png"), "wb").write(b"\x89PNG\r\n\x1a\ngarbage")
st.op({"op": "set_sprite", "id": "a", "file": "broken.png"})
stg = st.stage("s", 0)
assert stg["layers"], "the scene must keep rendering"
assert any("broken.png" in w for w in stg.get("warnings", [])), stg.get("warnings")

# and one that does read leaves no warning
import zlib, struct
ch = lambda t, dd: struct.pack(">I", len(dd)) + t + dd + struct.pack(">I", zlib.crc32(t + dd))
raw = b"".join(b"\x00" + bytes([200, 100, 50]) * 8 for _ in range(8))
open(os.path.join(d, "ok.png"), "wb").write(
    b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0))
    + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b""))
st.op({"op": "set_sprite", "id": "a", "file": "ok.png"})
assert not st.stage("s", 0).get("warnings"), st.stage("s", 0).get("warnings")
print("ERRORS GREEN")

# 3) opening a .vn that does not exist (typo in the path) must not stay mute:
#    it starts blank BUT says so
st3 = ws.Studio("/does/not/exist/story.vn~")
assert st3.path is None and st3.model["order"], "starts blank anyway"
assert any("does not exist" in p for p in st3.problems), st3.problems
assert st3.state()["problems"] == st3.problems

r = ws.Studio(p).op({"op": "open_project", "path": "/neither/exists.vn"})
assert r.get("error") and "does not exist" in r["error"], r.get("error")
print("ERRORS+OPEN GREEN")
