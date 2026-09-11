import json, threading, urllib.request, urllib.error, tempfile, os, struct, zlib
from znt.web import server as ws

d = tempfile.mkdtemp()
# real 20x30 PNG sprite
px = bytes((200, 80, 90, 255)) * (20 * 30)
raw = b"".join(b"\0" + px[y*80:(y+1)*80] for y in range(30))
ch = lambda t, b: struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b))
open(os.path.join(d, "ana.png"), "wb").write(
    b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", 20, 30, 8, 6, 0, 0, 0))
    + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b""))
p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter a "Ana" color=#e79ab0\ncharacter b "Leo" color=#5a86d8\n'
    'sprite a ana.png\n'
    'scene s\n  bg grad:#101828,#304060\n  show a left\n  show b right\n  a: Hello.\n  end\n')

st = ws.Studio(p)
httpd = ws.make_server(st, "127.0.0.1", 0)
port = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()
B = f"http://127.0.0.1:{port}"
get = lambda u: json.load(urllib.request.urlopen(B + u))

s = get("/api/stage?scene=s&step=3")          # up to the say
assert (s["w"], s["h"]) == (640, 448), (s["w"], s["h"])
assert s["bg"]["kind"] == "grad" and s["bg"]["a"] == "#101828", s["bg"]
ids = {l["id"]: l for l in s["layers"]}
assert "a" in ids and "b" in ids, ids.keys()
assert ids["a"]["url"] and "ana.png" in ids["a"]["url"], ids["a"]     # real sprite
assert (ids["a"]["w"], ids["a"]["h"]) == (20, 30), (ids["a"]["w"], ids["a"]["h"])
assert ids["b"]["url"] is None and ids["b"]["color"] == "#5a86d8"     # placeholder
assert ids["a"]["x"] == -180 and ids["b"]["x"] == 180                 # presets
assert s["say"]["name"] == "Ana" and s["say"]["text"] == "Hello."

img = urllib.request.urlopen(B + "/api/asset?f=ana.png").read()       # assets
assert img[:8] == b"\x89PNG\r\n\x1a\n"
try:                                                                  # traversal blocked
    urllib.request.urlopen(B + "/api/asset?f=../../etc/passwd"); raise SystemExit("traversal NOT blocked")
except urllib.error.HTTPError as e:
    assert e.code in (403, 404), e.code

httpd.shutdown()
print("STAGE GREEN")
