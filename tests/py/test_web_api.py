import json, threading, urllib.request, tempfile, os
from znt.web import server as ws

d = tempfile.mkdtemp()
p = os.path.join(d, "h.vn")
open(p, "w").write('title: T\ncharacter a "Ana"\nscene s\n  a: hello\n  end\n')

st = ws.Studio(p)
httpd = ws.make_server(st, "127.0.0.1", 0)
port = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()

B = f"http://127.0.0.1:{port}"
def get(u): return json.load(urllib.request.urlopen(B + u))
def post(u, o):
    r = urllib.request.Request(B + u, data=json.dumps(o).encode(),
                               headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r))

s = get("/api/model")
assert s["model"]["title"] == "T", s["model"]["title"]
assert s["scene"] == "s" and s["step"] == -1
n0 = len(s["model"]["scenes"]["s"])

s = post("/api/op", {"op": "add_step", "kind": "say"})          # add step
assert len(s["model"]["scenes"]["s"]) == n0 + 1, s["model"]["scenes"]["s"]
s = post("/api/op", {"op": "undo"})                              # undo
assert len(s["model"]["scenes"]["s"]) == n0
s = post("/api/op", {"op": "redo"})                              # redo
assert len(s["model"]["scenes"]["s"]) == n0 + 1

s = post("/api/op", {"op": "select", "scene": "s", "step": 0})   # selection
assert s["step"] == 0
s = post("/api/op", {"op": "set_props", "props": {"text": "bye"}})
assert s["model"]["scenes"]["s"][0]["text"] == "bye", s["model"]["scenes"]["s"][0]

s = post("/api/op", {"op": "validate"})                          # validation
assert s["problems"] == [], s["problems"]
s = post("/api/op", {"op": "save"})                              # save .vn
assert "bye" in open(p, encoding="utf-8").read()

assert get("/")["ok"] if False else True                          # index serves HTML (not JSON)
html = urllib.request.urlopen(B + "/").read().decode()
assert "<html" in html.lower(), html[:80]

httpd.shutdown()
print("WEB API GREEN")
