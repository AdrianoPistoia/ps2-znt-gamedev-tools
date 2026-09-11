"""Export from the UI: HTML player, PS2 blob and (when possible) ISO."""
import tempfile, os, shutil
from znt.web import server as ws
from znt import vniso

d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write('title: T\ncharacter a "Ana"\nscene s\n  a: hello\n  end\n')
st = ws.Studio(p)

r = st.op({"op": "export", "path": os.path.join(d, "out.html")})
assert not r.get("error") and os.path.exists(os.path.join(d, "out.html"))

r = st.op({"op": "export_ps2", "path": os.path.join(d, "out.vnp")})
assert not r.get("error"), r.get("error")
blob = open(os.path.join(d, "out.vnp"), "rb").read()
assert vniso.read_blob(blob)["scenes"][0][0]["text"] == "hello", "the blob is the in-memory project (not the .vn on disk)"
assert "out.vnp" in (r.get("notice") or ""), "says what it wrote"

r = st.op({"op": "export_ps2", "path": os.path.join(d, "out.iso")})
assert r.get("error") and "ELF" in r["error"], "an ISO needs the ELF"
elf = os.path.join(d, "p.elf"); open(elf, "wb").write(b"\x7fELF")
r = st.op({"op": "export_ps2", "path": os.path.join(d, "out.iso"), "elf": elf})
if shutil.which("genisoimage"):
    assert not r.get("error") and os.path.exists(os.path.join(d, "out.iso")), r.get("error")
else:
    assert r.get("error") and "genisoimage" in r["error"]
print("EXPORT GREEN")
