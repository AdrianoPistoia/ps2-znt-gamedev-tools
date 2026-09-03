import json, threading, urllib.request, tempfile, os, struct, zlib
from znt.web import server as ws

d = tempfile.mkdtemp()
px = bytes((200, 80, 90, 255)) * (20 * 30)
raw = b"".join(b"\0" + px[y*80:(y+1)*80] for y in range(30))
ch = lambda t, b: struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b))
open(os.path.join(d, "ana.png"), "wb").write(
    b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", 20, 30, 8, 6, 0, 0, 0))
    + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b""))
open(os.path.join(d, "notas.txt"), "w").write("x")
p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter a "Ana" color=#e79ab0\nscene s\n  show a left\n  a: hola\n  end\n')

st = ws.Studio(p)
h = ws.make_server(st, "127.0.0.1", 0); port = h.server_address[1]
threading.Thread(target=h.serve_forever, daemon=True).start()
B = f"http://127.0.0.1:{port}"
get = lambda u: json.load(urllib.request.urlopen(B + u))

# 1) listar imágenes del proyecto (sólo imágenes)
a = get("/api/assets")
assert a["assets"] == ["ana.png"], a

# 2) sin sprite -> placeholder (url None, tamaño del bloque)
L = {l["id"]: l for l in get("/api/stage?scene=s&step=1")["layers"]}
assert L["a"]["url"] is None and (L["a"]["w"], L["a"]["h"]) == (200, 300)

# 3) asignar sprite
st.op({"op": "set_sprite", "id": "a", "file": "ana.png"})
assert st.model["characters"]["a"]["sprite"] == "ana.png"
L = {l["id"]: l for l in get("/api/stage?scene=s&step=1")["layers"]}
assert L["a"]["url"] and "ana.png" in L["a"]["url"], L["a"]
assert (L["a"]["w"], L["a"]["h"]) == (20, 30), "debe usar el tamaño real del PNG"
assert st.state()["can_undo"], "debe entrar en el historial"

# 4) quitarlo vuelve al placeholder
st.op({"op": "set_sprite", "id": "a", "file": ""})
assert "sprite" not in st.model["characters"]["a"]
L = {l["id"]: l for l in get("/api/stage?scene=s&step=1")["layers"]}
assert L["a"]["url"] is None and (L["a"]["w"], L["a"]["h"]) == (200, 300)

print("SPRITE GREEN")
h.shutdown()
