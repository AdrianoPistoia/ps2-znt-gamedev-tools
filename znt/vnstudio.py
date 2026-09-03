#!/usr/bin/env python3
"""Framework gráfico de desarrollo de novelas visuales, sobre el engine real.

Dos piezas:
- `VNRuntime` (headless): reproduce un modelo autoral (`vn`) usando el MISMO
  render y la MISMA animación del engine (capas `LayerState`, curvas y acciones).
  Compone fondo + sprites; el texto del diálogo lo pone el frontend (la fuente del
  juego es japonesa, sin acentos latinos), y lo expone como estado.
- `run_editor` (tkinter): editor visual — lista de escenas y de pasos, edición de
  propiedades, stage en vivo con el engine, Play, y export a `.vn` + player HTML.

    python -m znt studio [proyecto.vn]      # abre el editor (necesita display)

El runtime es headless y guionable; el editor va encima. Reusa image/render/engine
y el formato de `vn` (parse/to_text/build).
"""
import sys, os

from . import render, image, vn
from .engine import LayerState, Action, Tween, CURVES

POS = {"left": -180, "center": 0, "right": 180}
ACTIONS = ("wave", "waveonce", "jump", "jumponce", "fall", "vibrate")


def _hex(c, default=(120, 120, 130)):
    c = (c or "").lstrip("#")
    if len(c) == 6:
        return tuple(int(c[i:i+2], 16) for i in (0, 2, 4))
    return default


def _solid_rows(w, h, rgb):
    row = bytes((*rgb, 255)) * w
    return [row] * h


def _grad_rows(w, h, a, b):
    ca, cb = _hex(a), _hex(b)
    rows = []
    for y in range(h):
        k = y / max(1, h - 1)
        r, g, bl = (int(ca[i] + (cb[i] - ca[i]) * k) for i in range(3))
        rows.append(bytes((r, g, bl, 255)) * w)
    return rows


def _block_rows(w, h, rgb, alpha=170):
    """Placeholder de personaje: bloque tenue con esquinas redondeadas."""
    px = bytes((*rgb, alpha)); clear = bytes((0, 0, 0, 0)); rad = min(w, h) // 6
    rows = []
    for y in range(h):
        r = bytearray()
        for x in range(w):
            corner = ((x < rad and y < rad and (rad-x)**2 + (rad-y)**2 > rad*rad) or
                      (x >= w-rad and y < rad and (x-(w-rad))**2 + (rad-y)**2 > rad*rad) or
                      (x < rad and y >= h-rad and (rad-x)**2 + (y-(h-rad))**2 > rad*rad) or
                      (x >= w-rad and y >= h-rad and (x-(w-rad))**2 + (y-(h-rad))**2 > rad*rad))
            r += clear if corner else px
        rows.append(bytes(r))
    return rows


class VNRuntime:
    def __init__(self, model, base_dir=".", w=640, h=448):
        self.model, self.base, self.W, self.H = model, base_dir, w, h
        self._asset_cache = {}
        self.reset_state()

    def reset_state(self):
        self.stage = {}          # name -> LayerState
        self.speaker = self.text = None
        self.choices = []
        self.scene_id = None
        self.done = False
        self.ip = 0

    # --- assets ------------------------------------------------------------
    def _load_asset(self, fname):
        if fname in self._asset_cache:
            return self._asset_cache[fname]
        rows = None
        try:
            _, _, rows = image.load_png_file(os.path.join(self.base, fname))
        except Exception:
            rows = None
        self._asset_cache[fname] = rows
        return rows

    def _bg_rows(self, spec):
        if spec["kind"] == "solid":
            return _solid_rows(self.W, self.H, _hex(spec["color"]))
        if spec["kind"] == "grad":
            return _grad_rows(self.W, self.H, spec["a"], spec["b"])
        return self._load_asset(spec.get("file", "")) or _solid_rows(self.W, self.H, (20, 22, 34))

    def _sprite_rows(self, cid):
        c = self.model["characters"].get(cid, {})
        if c.get("sprite"):
            rows = self._load_asset(c["sprite"])
            if rows:
                return rows
        return _block_rows(200, 300, _hex(c.get("color")))

    # --- ejecutar la escena ------------------------------------------------
    def enter(self, scene_id):
        self.reset_state()
        self.scene_id = scene_id
        self._run()

    def _steps(self):
        return self.model["scenes"].get(self.scene_id, [])

    def _run(self):
        """Ejecuta pasos no bloqueantes hasta un say/choice/goto/end."""
        self.speaker = self.text = None
        self.choices = []
        steps = self._steps()
        while self.ip < len(steps):
            s = steps[self.ip]; self.ip += 1
            if self._exec(s):
                return
        self.done = True

    def _exec(self, s, navigate=True):
        """Aplica un paso. Devuelve True si es bloqueante (say/choice/goto/end)."""
        op = s["op"]
        if op == "bg":
            l = self.stage.setdefault("bg", LayerState()); l.level = 0
            l.rows = self._bg_rows(s["spec"]); l.x = l.y = 0.0
        elif op == "show":
            l = self.stage.setdefault(s["id"], LayerState())
            l.rows = self._sprite_rows(s["id"])
            l.x = float(s["x"]) if "x" in s else float(POS.get(s.get("pos", "center"), 0))
            l.y = float(s.get("y", 0))
            l.level = 10 + len([k for k in self.stage if k != "bg"]); l.show = True
        elif op == "hide":
            if s["id"] in self.stage: self.stage[s["id"]].show = False
        elif op == "animate":
            self._animate(s)
        elif op == "say":
            self.speaker, self.text = s.get("who"), s.get("text", ""); return True
        elif op == "choice":
            self.choices = s.get("options", []); return True
        elif op == "goto":
            if navigate: self.enter(s["target"])
            return True
        elif op == "end":
            if navigate: self.done = True
            return True
        return False

    def preview_upto(self, scene_id, k):
        """Estado estático tras ejecutar los pasos 0..k de una escena (para el editor)."""
        self.reset_state(); self.scene_id = scene_id
        self.speaker = self.text = None; self.choices = []
        for s in self._steps()[:k+1]:
            self._exec(s, navigate=False)
        self.settle()

    def _animate(self, s):
        l = self.stage.get(s["id"])
        if not l:
            return
        p = s.get("params", {}); kind = s["kind"]
        vib = p.get("vib", p.get("vibration", 16))
        if kind in CURVES or kind == "move":
            curve = kind if kind in CURVES else p.get("curve", "linear")
            if "x" in p: l.target("x", p["x"], frm=l.x, dur=p.get("time", 500), curve=curve)
            if "y" in p: l.target("y", p["y"], frm=l.y, dur=p.get("time", 500), curve=curve)
        elif kind in ACTIONS:
            l.action = Action(kind, vib, p.get("cycle", 340), p.get("wait", 40),
                              p.get("dist", p.get("distance", 120)),
                              p.get("falltime", p.get("time", 600)))

    def advance(self):
        if self.text is not None and not self.done:
            self._run()

    def choose(self, i):
        if 0 <= i < len(self.choices):
            self.enter(self.choices[i]["target"])

    def settle(self):
        """Lleva los tweens (movimientos) a su fin, para el preview estático."""
        for _ in range(60):
            if not any(l.tw for l in self.stage.values()):
                break
            self.tick(30)

    def tick(self, dt):
        for l in self.stage.values():
            l.tick(dt)

    def animating(self):
        return any(l.animating for l in self.stage.values())

    def _screen(self, l):
        """(sx, sy, w, h) del blit de una capa. Compartido por frame() y el editor."""
        w, h = len(l.rows[0]) // 4, len(l.rows)
        ox, oy = l.offset
        return int(l.x + ox) + self.W // 2 - w // 2, int(l.y + oy) + self.H - h, w, h

    def layer_rect(self, name):
        l = self.stage.get(name)
        return self._screen(l) if l and l.rows and l.show else None

    def place_from_screen(self, name, sx, sy):
        """Fija x/y de una capa a partir de una posición de pantalla (drag del editor)."""
        l = self.stage.get(name)
        if not l or not l.rows:
            return
        w, h = len(l.rows[0]) // 4, len(l.rows)
        l.x = float(sx - (self.W // 2 - w // 2))
        l.y = float(sy - (self.H - h))

    def invalidate(self):
        self._asset_cache.clear()

    def frame(self):
        fb = render.Framebuffer(self.W, self.H)
        for l in sorted(self.stage.values(), key=lambda s: s.level):   # menor level al fondo
            if not l.rows or not l.show:
                continue
            sx, sy, w, h = self._screen(l)
            ly = render.Layer().loadImage(l.rows)
            ly.setPos(sx, sy); ly.setOpacity(l.opacity); ly.draw(fb)
        return fb


def demo():
    """Self-check headless: reproduce un modelo con animación, sin display."""
    model = vn._link_choices(vn.parse(
        'title: t\ncharacter a "Ana" color=#77ccff\n'
        'scene uno\n  bg grad:#101828,#304060\n  show a right\n'
        '  animate a move x=0 curve=accel time=400\n'
        '  a: hola\n  * fin\n  end\n'))
    rt = VNRuntime(model)
    rt.enter("uno")
    assert "bg" in rt.stage and "a" in rt.stage, list(rt.stage)
    assert rt.speaker == "a" and rt.text == "hola", (rt.speaker, rt.text)
    # la animación de movimiento está activa y con la curva pedida
    assert "x" in rt.stage["a"].tw and rt.stage["a"].tw["x"].curve == "accel"
    x0 = rt.stage["a"].x
    rt.tick(200); assert rt.stage["a"].x != x0            # se movió
    rt.settle(); assert not rt.stage["a"].tw               # terminó
    fb = rt.frame(); assert (fb.w, fb.h) == (640, 448)
    # avanzar: narración y fin
    rt.advance(); assert rt.text == "fin"
    rt.advance(); assert rt.done
    # posición libre por x/y y round-trip de place_from_screen
    m2 = vn._link_choices(vn.parse('title: t\ncharacter a "A"\nscene s\n  show a center x=60 y=-20\n  a: h\n  end\n'))
    r2 = VNRuntime(m2); r2.enter("s")
    assert r2.stage["a"].x == 60.0 and r2.stage["a"].y == -20.0, (r2.stage["a"].x, r2.stage["a"].y)
    sx, sy, w, h = r2.layer_rect("a")
    r2.place_from_screen("a", sx + 10, sy - 5)      # mover 10 a la derecha, 5 arriba
    assert r2.stage["a"].x == 70.0 and r2.stage["a"].y == -25.0, (r2.stage["a"].x, r2.stage["a"].y)
    print("demo OK")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] != "demo":
        from .studio_ui import run_editor
        run_editor(sys.argv[1] if sys.argv[1] != "new" else None)
    else:
        demo()
