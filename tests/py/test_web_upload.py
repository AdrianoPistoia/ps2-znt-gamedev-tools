"""Picking an image from the system: the browser uploads it and it lands next to the .vn."""
import tempfile, os, base64, zlib, struct
from znt.web import server as ws

def png(w, h):                                    # minimal opaque PNG
    raw = b"".join(b"\x00" + bytes([255, 0, 0]) * w for _ in range(h))
    ch = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    return (b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b""))

d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write('title: T\ncharacter a "Ana"\nscene s\n  show a\n  a: hello\n  end\n')
st = ws.Studio(p)

data = base64.b64encode(png(4, 6)).decode()
st.op({"op": "upload_sprite", "id": "a", "name": "ana.png", "data": data})
assert os.path.exists(os.path.join(d, "ana.png")), "must be saved next to the .vn"
assert st.model["characters"]["a"]["sprite"] == "ana.png", "and be assigned"
assert "ana.png" in st.assets(), "and show up in the asset list"
assert st.state()["can_undo"], "must enter the history"

st.op({"op": "select", "scene": "s", "step": 0})
l = st.stage("s", 0)["layers"][0]
assert (l["w"], l["h"]) == (4, 6), f"the stage must use the uploaded image: {l}"

# nothing is written outside the project folder
st.op({"op": "upload_sprite", "id": "a", "name": "../leak.png", "data": data})
assert not os.path.exists(os.path.join(d, "..", "leak.png")), "path traversal"
print("UPLOAD GREEN")
