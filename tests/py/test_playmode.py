"""Play has to be able to show both pacings:

- **step by step** (the editor's, default): each click executes ONE step, and a `group`
  runs together. Useful to watch each background and each sprite land.
- **like the player**: each click runs everything up to the next dialogue or choice, which
  is what the HTML player and the PS2 ELF really do.

The runtime already had both (`enter_at`/`step_once` and `enter`/`advance`); what was
missing was being able to pick them from the editor, so what is previewed is what
the player is going to see."""
import tempfile, os
from znt import vn, vnstudio
from znt.web import server as ws

SRC = ('title: T\ncharacter a "A" color=#fff\n'
       'scene s\n  bg #101\n  show a left\n  a: hola\n'
       '  bg #202\n  show a right\n  a: chau\n  end\n')
m = vn._link_choices(vn.parse(SRC))

# --- the runtime: game mode runs up to the dialogue ---
rt = vnstudio.VNRuntime(m); rt.enter("s")
assert rt.text == "hola" and "a" in rt.stage, (rt.text, "background and sprite already applied")

# --- the runtime: step by step stops at every step ---
rt = vnstudio.VNRuntime(m); rt.enter_at("s", 0)
assert rt.text is None, "step 0 is the background"
rt.step_once(); assert rt.text is None, "the show follows"
rt.step_once(); assert rt.text == "hola", rt.text

# --- the server: step by step by default (previous behavior unchanged) ---
d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write(SRC)
st = ws.Studio(p)
pl = st.op({"op": "play", "scene": "s", "step": 0})["play"]
assert pl["say"] is None and pl["step"] == 0, (pl["step"], "starts at the background")
assert pl["stepwise"] is True

# --- the server: player mode runs up to the dialogue, and advances just like the player ---
pl = st.op({"op": "play", "scene": "s", "step": 0, "stepwise": False})["play"]
assert pl["stepwise"] is False
assert pl["say"]["text"] == "hola", pl["say"]
assert [l["id"] for l in pl["layers"]] == ["a"], "the sprite is already placed"
pl = st.op({"op": "play_advance"})["play"]
assert pl["say"]["text"] == "chau", pl["say"]
pl = st.op({"op": "play_advance"})["play"]
assert pl["done"], "end"

print("PLAYMODE GREEN")
