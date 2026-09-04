"""Audio en Play: el estado dice qué bgm suena y cuándo disparar un se."""
import tempfile, os, threading, urllib.request
from znt.web import server as ws

d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(os.path.join(d, "tema.wav"), "wb").write(b"RIFF\x24\x00\x00\x00WAVEfmt ")
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter a "Ana"\nscene s\n  bgm tema.wav\n  a: uno\n  se golpe.wav\n  a: dos\n'
    '  se golpe.wav\n  a: tres\n  bgm stop\n  a: cuatro\n  end\n')
st = ws.Studio(p)
st.op({"op": "play", "scene": "s", "step": 0})
pl = st.state()["play"]
assert pl["bgm"] == "tema.wav" and pl["se"] is None and pl["se_seq"] == 0, pl
adv = lambda n: [st.op({"op": "play_advance"}) for _ in range(n)]
adv(2)                                             # say, se
pl = st.state()["play"]
assert pl["se"] == "golpe.wav" and pl["se_seq"] == 1, "el se se disparó una vez"
adv(2)                                             # say, se
pl = st.state()["play"]
assert pl["se"] == "golpe.wav" and pl["se_seq"] == 2, "mismo archivo, otro disparo: el cliente lo distingue por seq"
adv(2)                                             # say, bgm stop
assert st.state()["play"]["bgm"] is None, "bgm stop"

# el audio se sirve con su mimetype
srv = ws.make_server(st, "127.0.0.1", 0)
threading.Thread(target=srv.serve_forever, daemon=True).start()
r = urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}/api/asset?f=tema.wav")
assert r.status == 200 and r.headers["Content-Type"].startswith("audio/"), r.headers["Content-Type"]
srv.shutdown()
print("AUDIO GREEN")
