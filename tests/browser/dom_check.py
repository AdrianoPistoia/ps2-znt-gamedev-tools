#!/usr/bin/env python3
"""Chequeo del DOM ya renderizado (chromium headless): la UI arma lo que debe.
Se saltea solo si no hay chromium."""
import os, re, shutil, subprocess, sys, tempfile, threading, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from znt.web import server as ws

CHROME = next((c for c in ("chromium", "chromium-browser", "google-chrome-stable", "google-chrome")
               if shutil.which(c)), None)
if not CHROME:
    print("SKIP (no hay chromium)"); raise SystemExit(0)

d = tempfile.mkdtemp()
p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter ana "Ana" #7cc4ff\ncharacter leo "Leo" #f0a92e\n'
    'scene s\n  bg #101828\n  show ana center\n  ana: hola\n  end\n')
st = ws.Studio(p)
srv = ws.make_server(st, "127.0.0.1", 0)
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{srv.server_address[1]}/"

def dom_raw():
    out = os.path.join(d, "dom.html")
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--dump-dom",
                    "--virtual-time-budget=4000", url],
                   stdout=open(out, "w"), stderr=subprocess.DEVNULL, timeout=60)
    return open(out, encoding="utf-8").read()

def dom(step):
    st.op({"op": "select", "scene": "s", "step": step})
    return dom_raw()

def ok(cond, msg):
    if not cond:
        print("FALLA:", msg); srv.shutdown(); raise SystemExit(1)

h = dom(1)                                        # paso `show`
sel = re.findall(r'data-role="char"', h)
ok(len(sel) == 1, f"tiene que haber UN solo selector de personaje, hay {len(sel)}")
ok('id="props"' in h and "PERSONAJE" in h.upper(), "el inspector se armó")
ok(h.count('class="clip') == 4, "los 4 pasos como clips en el timeline")
ok('id="layers"' in h and ">Ana<" in h, "la capa aparece en el outliner")

h = dom(2)                                        # paso `say`
ok(len(re.findall(r'data-role="char"', h)) == 1, "en say también, uno solo")
# Play desde el paso elegido: la UI se apaga menos el timeline, y el clip que
# se está reproduciendo queda marcado
st.op({"op": "select", "scene": "s", "step": 2})
st.op({"op": "play", "scene": "s", "step": 2})
h = dom_raw()
ok(re.search(r'<body[^>]*class="[^"]*playing', h), "body.playing mientras se reproduce")
ok('class="clip playing' in h or 'class="clip sel playing' in h or 'clip playing' in h,
   "el clip en reproducción está marcado")
ok(">hola<" in h or "hola" in h, "el diálogo del paso elegido está en pantalla")
st.op({"op": "play_stop"})
srv.shutdown()
print("DOM GREEN")
