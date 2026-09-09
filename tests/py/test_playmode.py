"""Play tiene que poder mostrar los dos ritmos:

- **paso a paso** (el del editor, default): cada click ejecuta UN paso, y un `group`
  corre junto. Sirve para ver aterrizar cada fondo y cada sprite.
- **como el jugador**: cada click corre todo hasta el próximo diálogo u opción, que es
  lo que hacen de verdad el player HTML y el ELF de PS2.

El runtime ya tenía los dos (`enter_at`/`step_once` y `enter`/`advance`); lo que
faltaba era poder elegirlos desde el editor, así lo que se previsualiza es lo que
va a ver el jugador."""
import tempfile, os
from znt import vn, vnstudio
from znt.web import server as ws

SRC = ('title: T\ncharacter a "A" color=#fff\n'
       'scene s\n  bg #101\n  show a left\n  a: hola\n'
       '  bg #202\n  show a right\n  a: chau\n  end\n')
m = vn._link_choices(vn.parse(SRC))

# --- el runtime: modo juego corre hasta el diálogo ---
rt = vnstudio.VNRuntime(m); rt.enter("s")
assert rt.text == "hola" and "a" in rt.stage, (rt.text, "fondo y sprite ya aplicados")

# --- el runtime: paso a paso se frena en cada paso ---
rt = vnstudio.VNRuntime(m); rt.enter_at("s", 0)
assert rt.text is None, "el paso 0 es el fondo"
rt.step_once(); assert rt.text is None, "sigue el show"
rt.step_once(); assert rt.text == "hola", rt.text

# --- el servidor: por defecto paso a paso (no cambia lo de antes) ---
d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write(SRC)
st = ws.Studio(p)
pl = st.op({"op": "play", "scene": "s", "step": 0})["play"]
assert pl["say"] is None and pl["step"] == 0, (pl["step"], "arranca en el fondo")
assert pl["stepwise"] is True

# --- el servidor: modo jugador corre hasta el diálogo, y avanza igual que el player ---
pl = st.op({"op": "play", "scene": "s", "step": 0, "stepwise": False})["play"]
assert pl["stepwise"] is False
assert pl["say"]["text"] == "hola", pl["say"]
assert [l["id"] for l in pl["layers"]] == ["a"], "el sprite ya está puesto"
pl = st.op({"op": "play_advance"})["play"]
assert pl["say"]["text"] == "chau", pl["say"]
pl = st.op({"op": "play_advance"})["play"]
assert pl["done"], "end"

print("PLAYMODE GREEN")
