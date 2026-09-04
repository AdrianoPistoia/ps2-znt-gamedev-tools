"""Exportar desde la UI: player HTML, blob PS2 y (si se puede) ISO."""
import tempfile, os, shutil
from znt.web import server as ws
from znt import vniso

d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write('title: T\ncharacter a "Ana"\nscene s\n  a: hola\n  end\n')
st = ws.Studio(p)

r = st.op({"op": "export", "path": os.path.join(d, "out.html")})
assert not r.get("error") and os.path.exists(os.path.join(d, "out.html"))

r = st.op({"op": "export_ps2", "path": os.path.join(d, "out.vnp")})
assert not r.get("error"), r.get("error")
blob = open(os.path.join(d, "out.vnp"), "rb").read()
assert vniso.read_blob(blob)["scenes"][0][0]["text"] == "hola", "el blob es el proyecto en memoria (no el .vn del disco)"
assert "out.vnp" in (r.get("notice") or ""), "avisa qué escribió"

r = st.op({"op": "export_ps2", "path": os.path.join(d, "out.iso")})
assert r.get("error") and "ELF" in r["error"], "para ISO hace falta el ELF"
elf = os.path.join(d, "p.elf"); open(elf, "wb").write(b"\x7fELF")
r = st.op({"op": "export_ps2", "path": os.path.join(d, "out.iso"), "elf": elf})
if shutil.which("genisoimage"):
    assert not r.get("error") and os.path.exists(os.path.join(d, "out.iso")), r.get("error")
else:
    assert r.get("error") and "genisoimage" in r["error"]
print("EXPORT GREEN")
