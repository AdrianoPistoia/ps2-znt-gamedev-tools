"""Blob v5: `bg X fade=ms` viaja como u16 fade en todo bg; `animate move` lleva y
(0x7FFF = no dado, para no pisar la coordenada que el autor no tocó)."""
from znt import vn, vniso
m = vn._link_choices(vn.parse(
    'title: T\ncharacter a "A" color=#fff\n'
    'scene s\n  bg #223 fade=400\n  bg grad:#000,#fff\n  show a center\n'
    '  animate a move x=100 time=300\n  animate a move y=-40 curve=accel time=200\n'
    '  animate a move x=10 y=20\n  a: h\n  end\n'))
r = vniso.read_blob(vniso.compile_blob(m, font=None))
st = r["scenes"][0]
assert st[0]["op"] == "bg" and st[0]["fade"] == 400, st[0]
assert st[1]["op"] == "bg" and st[1]["fade"] == 0, st[1]
an = [s for s in st if s["op"] == "animate"]
assert an[0]["x"] == 100 and an[0]["y"] is None, an[0]
assert an[1]["x"] is None and an[1]["y"] == -40 and an[1]["curve"] == "accel", an[1]
assert an[2]["x"] == 10 and an[2]["y"] == 20, an[2]
print("BLOB FADE/Y GREEN")
