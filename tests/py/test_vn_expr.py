"""Expresiones por personaje en el formato .vn."""
from znt import vn

src = ('title: T\ncharacter ana "Ana" color=#7cc4ff\n'
       'sprite ana ana.png\nsprite ana feliz feliz.png\nsprite ana triste triste.png\n'
       'scene s\n  show ana feliz left\n  show ana triste\n  show ana right\n  show ana\n  a: x\n  end\n')
m = vn.parse(src)
c = m["characters"]["ana"]
assert c["sprite"] == "ana.png", "el sprite base sigue igual"
assert c["expr"] == {"feliz": "feliz.png", "triste": "triste.png"}, c.get("expr")

st = m["scenes"]["s"]
assert st[0] == {"op": "show", "id": "ana", "expr": "feliz", "pos": "left"}, st[0]
assert st[1] == {"op": "show", "id": "ana", "expr": "triste"}, "sin pos: no se inventa center (mantiene posición)"
assert st[2] == {"op": "show", "id": "ana", "pos": "right"}, st[2]
assert st[3] == {"op": "show", "id": "ana"}, st[3]

# ida y vuelta
m2 = vn.parse(vn.to_text(m))
assert m2["characters"]["ana"] == c and m2["scenes"]["s"] == st

# qué archivo va
assert vn.sprite_file(c, "feliz") == "feliz.png"
assert vn.sprite_file(c, None) == "ana.png"
assert vn.sprite_file(c, "nada") == "ana.png", "expresión desconocida: cae al base"

# validate
bad = vn.parse('title: T\ncharacter ana "Ana"\nsprite ana ana.png\nscene s\n  show ana enojada\n  end\n')
probs = vn.validate(bad)
assert any("enojada" in p for p in probs), probs
import tempfile, os
d = tempfile.mkdtemp(); open(os.path.join(d, "ana.png"), "wb").write(b"x")
probs = vn.validate(m, d)
assert any("feliz.png" in p for p in probs) and any("triste.png" in p for p in probs), probs
print("EXPR FORMAT GREEN")
