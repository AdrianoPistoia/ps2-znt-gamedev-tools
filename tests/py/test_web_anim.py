import threading, urllib.request, tempfile, os, struct
from znt.web import server as ws

d = tempfile.mkdtemp(); p = os.path.join(d, "a.vn")
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter z "Zoe" color=#88ffdd\nscene s\n  bg grad:#101828,#304060\n'
    '  show z left\n  animate z move x=180 curve=decel time=600\n  z: llego\n  end\n')
st = ws.Studio(p)
h = ws.make_server(st, "127.0.0.1", 0); port = h.server_address[1]
threading.Thread(target=h.serve_forever, daemon=True).start()

r = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/anim?scene=s&step=2&ms=400")
data = r.read()
assert r.headers.get("Content-Type", "").startswith("image/"), r.headers.get("Content-Type")
assert data[:8] == b"\x89PNG\r\n\x1a\n", "no es PNG"
assert b"acTL" in data, "no es APNG (falta acTL)"
i = data.index(b"acTL"); n = struct.unpack(">I", data[i+4:i+8])[0]
assert n >= 2, f"deberia tener varios frames, tiene {n}"
print(f"ANIM GREEN ({n} frames, {len(data)//1024} KB)")
h.shutdown()
