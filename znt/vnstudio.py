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


def _scale_rows(rows, pct):
    """Escala filas RGBA por `pct`% (nearest-neighbor)."""
    if pct == 100:
        return rows
    h, w = len(rows), len(rows[0]) // 4
    nw, nh = max(1, w * pct // 100), max(1, h * pct // 100)
    out = []
    for y in range(nh):
        src = rows[y * h // nh]; r = bytearray(nw * 4)
        for x in range(nw):
            sx = x * w // nw
            r[x*4:x*4+4] = src[sx*4:sx*4+4]
        out.append(bytes(r))
    return out


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
        self._bad = {}
        self._base = None; self._base_sig = None; self._base_builds = 0
        self.reset_state()

    def reset_state(self):
        self.stage = {}          # name -> LayerState
        self.speaker = self.text = None
        self.choices = []
        self.bg_spec = None      # último fondo aplicado (para el frontend)
        self.bgm = None          # archivo de música actual (estado)
        self.last_se = None      # último efecto disparado
        self.se_seq = 0          # cuántos se dispararon (el cliente detecta uno nuevo por esto)
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
        except Exception as e:                      # se dibuja el placeholder,
            self._bad[fname] = str(e) or type(e).__name__   # pero se avisa por qué
        self._asset_cache[fname] = rows
        return rows

    def warnings(self):
        """Assets que no se pudieron leer (el escenario los reemplaza por el
        placeholder, pero el editor tiene que poder decir qué pasó)."""
        return [f"no se pudo leer {f}: {why}" for f, why in sorted(self._bad.items())]

    def _bg_rows(self, spec):
        if spec["kind"] == "solid":
            return _solid_rows(self.W, self.H, _hex(spec["color"]))
        if spec["kind"] == "grad":
            return _grad_rows(self.W, self.H, spec["a"], spec["b"])
        return self._load_asset(spec.get("file", "")) or _solid_rows(self.W, self.H, (20, 22, 34))

    def _sprite_rows(self, cid, expr=None):
        c = self.model["characters"].get(cid, {})
        f = vn.sprite_file(c, expr)
        if f:
            rows = self._load_asset(f)
            if rows:
                return rows
        return _block_rows(200, 300, _hex(c.get("color")))

    # --- ejecutar la escena ------------------------------------------------
    def enter(self, scene_id):
        self.reset_state()
        self.scene_id = scene_id
        self._run()

    def enter_at(self, scene_id, k):
        """Play desde el paso k: lo anterior se aplica sin frenar (como el editor),
        y de ahí en adelante corre normal."""
        self.reset_state(); self.scene_id = scene_id
        k = max(0, int(k))
        for s in self._steps()[:k]:
            self._exec(s, navigate=False)
        self.settle()
        self.ip = k
        self._run()

    @property
    def cursor(self):
        """Índice del paso en el que está parado el Play (el último ejecutado)."""
        return max(0, self.ip - 1)

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
            fade, old = int(s.get("fade") or 0), self.stage.get("bg")
            if fade and old is not None and old.rows:      # crossfade: el viejo queda abajo
                prev = self.stage.setdefault("bg_prev", LayerState())
                prev.rows, prev.level, prev.opacity, prev.show = old.rows, -1, 100.0, True
                prev.x = prev.y = 0.0
            l = self.stage.setdefault("bg", LayerState()); l.level = 0
            l.rows = self._bg_rows(s["spec"]); l.x = l.y = 0.0
            if fade and self.stage.get("bg_prev") is not None and self.stage["bg_prev"].show:
                l.opacity = 0.0; l.target("opacity", 100, frm=0, dur=fade)
            else:
                l.opacity = 100.0
            self.bg_spec = s["spec"]
        elif op == "show":
            l = self.stage.setdefault(s["id"], LayerState())
            was = bool(getattr(l, "show", False) and l.rows)   # ya estaba en escena
            l.rows = self._sprite_rows(s["id"], s.get("expr")); l.expr = s.get("expr")
            # re-mostrar (cambio de expresión) sin decir dónde: se queda donde está
            if "x" in s: l.x = float(s["x"])
            elif "pos" in s or not was: l.x = float(POS.get(s.get("pos", "center"), 0))
            if "y" in s or not was: l.y = float(s.get("y", 0))
            if "z" in s: l.level = int(s["z"])
            elif not was: l.level = 10 + len([k for k in self.stage if k != "bg"])
            if "zoom" in s or not was: l.zoom = float(s.get("zoom", 100))
            l._zc = None
            if "opacity" in s or not was: l.opacity = float(s.get("opacity", 100))
            if "tint" in s or not was: l.tint = s.get("tint")
            l.show = True
        elif op == "hide":
            if s["id"] in self.stage: self.stage[s["id"]].show = False
        elif op == "animate":
            self._animate(s)
        elif op == "bgm":
            self.bgm = None if s.get("stop") else s.get("file")
        elif op == "se":
            self.last_se = s.get("file"); self.se_seq += 1
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

    def preview_upto(self, scene_id, k, settle=True):
        """Estado tras ejecutar los pasos 0..k de una escena (para el editor).
        settle=True deja las animaciones resueltas (estático); settle=False las deja
        vivas desde t=0 para previsualizar la transición."""
        self.reset_state(); self.scene_id = scene_id
        self.speaker = self.text = None; self.choices = []
        for s in self._steps()[:k+1]:
            self._exec(s, navigate=False)
        if settle:
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
        prev = self.stage.get("bg_prev")               # terminó el fade: el viejo se va
        if prev is not None and prev.show and not self.stage["bg"].tw:
            prev.show = False

    def animating(self):
        return any(l.animating for l in self.stage.values())

    def _drawn(self, l):
        """Filas ya escaladas por el zoom de la capa (cacheadas por %)."""
        z = int(l.zoom)
        if z == 100:
            return l.rows
        c = getattr(l, "_zc", None)
        if not c or c[0] != z:
            l._zc = (z, _scale_rows(l.rows, z))
        return l._zc[1]

    def _screen(self, l, rows=None):
        """(sx, sy, w, h) del blit, anclado a base-centro (con zoom)."""
        rows = rows if rows is not None else self._drawn(l)
        w, h = len(rows[0]) // 4, len(rows)
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
        rows = self._drawn(l); w, h = len(rows[0]) // 4, len(rows)
        l.x = float(sx - (self.W // 2 - w // 2))
        l.y = float(sy - (self.H - h))

    def invalidate(self):
        self._asset_cache.clear(); self._bad.clear()

    def _blit(self, fb, l):
        rows = self._drawn(l)
        sx, sy, w, h = self._screen(l, rows)
        ly = render.Layer().loadImage(rows)
        ly.setPos(sx, sy); ly.setOpacity(l.opacity)
        if l.tint:
            ly.setColor(*(c * 100 // 255 for c in _hex(l.tint)))   # tinte multiplicativo
        ly.draw(fb)

    @staticmethod
    def _sig(layers):
        return tuple((id(l), int(l.x), int(l.y), int(l.opacity), l.level,
                      int(l.zoom), l.tint, id(l.rows)) for l in layers)

    def frame(self):
        """Compone el frame. Cachea lo que va DETRÁS de la primera capa animada
        (el fondo, que es lo caro) y por frame sólo re-blitea de ahí en adelante."""
        order = [l for l in sorted(self.stage.values(), key=lambda s: s.level)
                 if l.rows and l.show]                      # menor level al fondo
        k = next((i for i, l in enumerate(order) if l.animating), len(order))
        sig = self._sig(order[:k])
        if sig != self._base_sig:
            base = render.Framebuffer(self.W, self.H)
            for l in order[:k]:
                self._blit(base, l)
            self._base, self._base_sig = bytes(base.buf), sig
            self._base_builds += 1
        fb = render.Framebuffer(self.W, self.H)
        fb.buf = bytearray(self._base)
        for l in order[k:]:
            self._blit(fb, l)
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
    # zoom: escala anclada a base-centro (placeholder 200x300 al 200% -> 400x600)
    m3 = vn._link_choices(vn.parse('title: t\ncharacter z "Z"\nscene s\n  show z center x=0 zoom=200\n  z: h\n  end\n'))
    r3 = VNRuntime(m3); r3.enter("s")
    assert r3.stage["z"].zoom == 200.0
    sx3, sy3, w3, h3 = r3.layer_rect("z")
    assert (w3, h3) == (400, 600) and sx3 == r3.W // 2 - 200 and sy3 == r3.H - 600, (w3, h3, sx3, sy3)
    # opacidad y tinte por capa
    m4 = vn._link_choices(vn.parse('title: t\ncharacter w "W" color=#ffffff\n'
                                   'scene s\n  bg #000000\n  show w center opacity=50 tint=#0000ff\n  w: h\n  end\n'))
    r4 = VNRuntime(m4); r4.enter("s")
    assert r4.stage["w"].opacity == 50.0 and r4.stage["w"].tint == "#0000ff"
    fb4 = r4.frame(); rw = r4.layer_rect("w")
    o = ((rw[1] + rw[3]//2) * fb4.w + rw[0] + rw[2]//2) * 3
    cw = tuple(fb4.buf[o:o+3])
    assert cw[0] == 0 and cw[1] == 0 and cw[2] > 0, ("tinte azul", cw)   # R,G a 0; B queda
    # previsualización de transición: settle=False la deja viva desde t=0
    m5 = vn._link_choices(vn.parse('title: t\ncharacter a "A"\nscene s\n  show a center x=0\n'
                                   '  animate a move x=200 curve=linear time=400\n  a: h\n  end\n'))
    r5 = VNRuntime(m5)
    r5.preview_upto("s", 1, settle=False)
    assert "x" in r5.stage["a"].tw and r5.stage["a"].x == 0.0     # viva, sin arrancar
    r5.preview_upto("s", 1)                                       # settle=True: resuelta
    assert "x" not in r5.stage["a"].tw and r5.stage["a"].x == 200.0
    # audio: el runtime trackea bgm/se como estado
    m6 = vn._link_choices(vn.parse('title: t\ncharacter a "A"\nscene s\n'
                                   '  bgm tema.ogg\n  a: hola\n  se golpe.wav\n  bgm stop\n  end\n'))
    r6 = VNRuntime(m6); r6.enter("s")
    assert r6.bgm == "tema.ogg" and r6.last_se is None            # tras el primer talk
    r6.advance(); assert r6.last_se == "golpe.wav" and r6.bgm is None   # se + bgm stop
    print("demo OK")


if __name__ == "__main__":       # el runtime es headless; el editor va en `znt studio`
    demo()
