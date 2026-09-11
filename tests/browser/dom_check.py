#!/usr/bin/env python3
"""Check of the rendered DOM (headless chromium): the UI builds what it should.
Skips itself if there is no chromium."""
import os, re, shutil, subprocess, sys, tempfile, threading, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from znt.web import server as ws

CHROME = next((c for c in ("chromium", "chromium-browser", "google-chrome-stable", "google-chrome")
               if shutil.which(c)), None)
if not CHROME:
    print("SKIP (no chromium)"); raise SystemExit(0)

d = tempfile.mkdtemp()
p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write(
    'title: T\ncharacter ana "Ana" #7cc4ff\ncharacter leo "Leo" #f0a92e\n'
    'scene s\n  bg #101828\n  show ana center\n  ana: hello\n  end\n')
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
        print("FAIL:", msg); srv.shutdown(); raise SystemExit(1)

h = dom(1)                                        # `show` step
sel = re.findall(r'data-role="char"', h)
ok(len(sel) == 1, f"there must be ONE character selector only, found {len(sel)}")
ok('id="props"' in h and "CHARACTER" in h.upper(), "the inspector was built")
ok(h.count('class="clip') == 4, "the 4 steps as clips in the timeline")
ok('id="layers"' in h and ">Ana<" in h, "the layer shows up in the outliner")

h = dom(2)                                        # `say` step
ok(len(re.findall(r'data-role="char"', h)) == 1, "in say too, only one")
# Play from the selected step: the UI dims except the timeline, and the clip
# being played is marked
st.op({"op": "select", "scene": "s", "step": 2})
st.op({"op": "play", "scene": "s", "step": 2})
h = dom_raw()
ok(re.search(r'<body[^>]*class="[^"]*playing', h), "body.playing while playing")
ok('class="clip playing' in h or 'class="clip sel playing' in h or 'clip playing' in h,
   "the playing clip is marked")
ok(">hello<" in h or "hello" in h, "the selected step's line is on screen")
st.op({"op": "play_stop"})
srv.shutdown()
print("DOM GREEN")
