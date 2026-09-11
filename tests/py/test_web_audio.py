"""Audio in Play: the state says which bgm is playing and when to fire a se."""
import tempfile, os, threading, urllib.request
from znt.web import server as ws

d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(os.path.join(d, "theme.wav"), "wb").write(b"RIFF\x24\x00\x00\x00WAVEfmt ")
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter a "Ana"\nscene s\n  bgm theme.wav\n  a: one\n  se hit.wav\n  a: two\n'
    '  se hit.wav\n  a: three\n  bgm stop\n  a: four\n  end\n')
st = ws.Studio(p)
st.op({"op": "play", "scene": "s", "step": 0})
pl = st.state()["play"]
assert pl["bgm"] == "theme.wav" and pl["se"] is None and pl["se_seq"] == 0, pl
adv = lambda n: [st.op({"op": "play_advance"}) for _ in range(n)]
adv(2)                                             # say, se
pl = st.state()["play"]
assert pl["se"] == "hit.wav" and pl["se_seq"] == 1, "the se fired once"
adv(2)                                             # say, se
pl = st.state()["play"]
assert pl["se"] == "hit.wav" and pl["se_seq"] == 2, "same file, another trigger: the client tells them apart by seq"
adv(2)                                             # say, bgm stop
assert st.state()["play"]["bgm"] is None, "bgm stop"

# audio is served with its mimetype
srv = ws.make_server(st, "127.0.0.1", 0)
threading.Thread(target=srv.serve_forever, daemon=True).start()
r = urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}/api/asset?f=theme.wav")
assert r.status == 200 and r.headers["Content-Type"].startswith("audio/"), r.headers["Content-Type"]
srv.shutdown()
print("AUDIO GREEN")
