"""Step groups: several steps that run at once in Play."""
import tempfile, os
from znt import vn
from znt.web import server as ws

src = ('title: T\ncharacter a "Ana"\ncharacter b "Leo"\nscene s\n'
       '  group intro\n  bg #000000\n  show a left\n  show b right\n  endgroup\n'
       '  a: hola\n  group salida\n  show a\n  a: chau\n  endgroup\n  end\n')
m = vn.parse(src)
st = m["scenes"]["s"]
assert [s.get("group") for s in st] == ["intro", "intro", "intro", None, "salida", "salida", None], st
assert st[0]["op"] == "bg" and st[3]["op"] == "say", "the markers are not steps"
assert vn.parse(vn.to_text(m))["scenes"]["s"] == st, "round-trip"
assert vn.groups(st) == [("intro", 0, 2), ("salida", 4, 5)], vn.groups(st)

# Step-by-step Play: a whole group is one click (up to a blocking step)
d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn"); open(p, "w", encoding="utf-8").write(src)
stu = ws.Studio(p)
stu.op({"op": "play", "scene": "s", "step": 0})
pl = stu.state()["play"]
assert pl["step"] == 2 and sorted(l["id"] for l in pl["layers"]) == ["a", "b"], "the intro group ran in full"
stu.op({"op": "play_advance"}); pl = stu.state()["play"]
assert pl["step"] == 3 and pl["say"]["text"] == "hola"
stu.op({"op": "play_advance"}); pl = stu.state()["play"]
assert pl["step"] == 5 and pl["say"]["text"] == "chau", "the salida group runs show + say and stops at the say"
# starting in the middle of a group: runs to the end of the group
stu.op({"op": "play", "scene": "s", "step": 1})
assert stu.state()["play"]["step"] == 2

# group / ungroup from the editor (a single undo)
stu.op({"op": "play_stop"}); stu.op({"op": "select", "scene": "s", "step": 3})
stu.op({"op": "set_group", "indices": [3, 4, 5], "name": "charla"})
assert [s.get("group") for s in stu.model["scenes"]["s"]][3:6] == ["charla"] * 3
assert stu.state()["can_undo"]
stu.op({"op": "set_group", "indices": [4], "name": ""})
assert "group" not in stu.model["scenes"]["s"][4], "ungrouping removes the mark"
r = stu.op({"op": "set_group", "indices": [0, 1], "name": "con espacios raros"})
assert stu.model["scenes"]["s"][0]["group"] == "con_espacios_raros", "name without spaces (format)"
print("GROUPS GREEN")
