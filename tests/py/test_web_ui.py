"""El shell web: el server sirve la UI y el JS no le pega a ids inexistentes."""
import re, os, tempfile
from znt.web import server as ws

here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write('title: T\ncharacter a "Ana"\nscene s\n  a: hola\n  end\n')

W = os.path.join(os.path.dirname(ws.__file__))
html = open(os.path.join(W, "ui.html"), encoding="utf-8").read()
js = open(os.path.join(W, "static", "app.js"), encoding="utf-8").read()

ids = set(re.findall(r'id="([\w-]+)"', html))
used = set(re.findall(r'\$\("#([\w-]+)"\)', js))
assert not used - ids, f"el JS busca ids que no existen: {sorted(used - ids)}"

# el shell tiene sus zonas y los splitters que el JS mueve
for zone in ("topbar", "outliner", "viewport", "inspector", "timeline", "status"):
    assert f'id="{zone}"' in html, f"falta la zona {zone}"
panes = set(re.findall(r'data-pane="(\w+)"', html))
assert panes == {"out", "ins", "tl"}, panes
for v in ("--outw", "--insw", "--tlh"):
    assert v in html and v in js, f"{v} tiene que existir en el CSS y moverse desde el JS"

# y se sirven de verdad por HTTP
st = ws.Studio(p); h = ws._Handler
srv = ws.make_server(st, "127.0.0.1", 0)
import threading, urllib.request
threading.Thread(target=srv.serve_forever, daemon=True).start()
u = f"http://127.0.0.1:{srv.server_address[1]}"
assert b"<title>VN Studio" in urllib.request.urlopen(u + "/").read()
for f in ("app.js", "logic.js"):
    assert urllib.request.urlopen(f"{u}/static/{f}").status == 200, f
srv.shutdown()
print("UI GREEN")
