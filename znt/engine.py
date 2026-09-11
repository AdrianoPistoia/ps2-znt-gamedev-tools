#!/usr/bin/env python3
"""Live runtime core — headless and decoupled from the frontend.

The engine keeps the scene state (animated layers, dialogue box), advances time
(`tick`) and composes the current frame (`frame`) onto a framebuffer. It knows
NOTHING about the screen: a frontend (tkinter window, APNG export, ...) drives
it by calling tick/frame/advance and feeding it input.

Animation comes from the props each scene `set` already carries
(`xFrom`→`x` over `moveTime`, `opacityFrom`→`opacity` over `opacityTime`): they
are a tween. `talk` suspends the scene coroutine (stackful, from `sqrt`); the
frontend animates while waiting and calls `advance()` to wake it up.

Contract for the frontend:
    e = Engine(disc); e.load(1000)
    while not e.done:
        e.tick(dt_ms)                 # advance animations
        fb = e.frame()                # current framebuffer (render.Framebuffer)
        present(fb)                    # <- the frontend draws it
        if user_click and e.waiting:  # e.waiting == stopped at a talk
            e.advance()
    # e.speaker / e.text = current dialogue ; e.animating() = live tweens exist
"""
import sys, math, random

from . import render, sqrt, sqtranspile
from .tim2 import Texture

IDX = lambda v: int(v) & 0xFFFFFF
BANK = lambda v: (int(v) >> 24) & 0xFF


def ease(curve, k):
    """The game's movement curves (LayerMoveModule.action, 0001.nut):
    normal n=t, accel n=t², decel n=1-(1-t)². Faithful to the ELF/scripts."""
    if curve == "accel": return k * k
    if curve == "decel": return 1 - (1 - k) * (1 - k)
    return k                                            # normal / linear


CURVES = ("linear", "accel", "decel")


class Tween:
    __slots__ = ("frm", "to", "dur", "t", "curve")
    def __init__(self, frm, to, dur, curve="linear"):
        self.frm, self.to = float(frm), float(to)
        self.dur, self.t, self.curve = max(1.0, float(dur)), 0.0, curve
    def tick(self, dt): self.t = min(self.dur, self.t + dt)
    @property
    def done(self): return self.t >= self.dur
    @property
    def value(self):
        return self.frm + (self.to - self.frm) * ease(self.curve, self.t / self.dur)


class Action:
    """Action offset (setActionOffset), separate from the position. Exact math
    of the *ActionModule classes (0001.nut):
      wave      dx = vib·sin(2π·now/cycle)                     (continuous)
      waveonce  dx = vib·sin(π + 2π·now/cycle)      until now≥cycle/2
      jump      dy = vib·sin(2π·now/cycle) + vib               (continuous, downward only)
      jumponce  dy = vib·sin(π + 2π·now/cycle) + vib until now≥cycle/2
      fall      dy = -distance + distance·now/fallTime  until now≥fallTime (falls from above)
      vibrate   every waitTime: dx=rand(vib)-vib/2, dy=rand(vib) (downward only)
    """
    def __init__(self, kind, vibration=0, cycle=0, wait=0, distance=0, falltime=0):
        self.kind = kind
        self.vib = float(vibration)
        self.cycle = max(1.0, float(cycle))
        self.wait = max(1.0, float(wait))
        self.distance = float(distance)
        self.falltime = max(1.0, float(falltime))
        self.now = 0.0
        self.next = 0.0
        self.ox = self.oy = 0.0
        self.done = False

    def tick(self, dt):
        if self.done:
            self.ox = self.oy = 0.0; return
        self.now += dt
        w = math.pi * 2 * self.now / self.cycle
        if self.kind == "wave":
            self.ox, self.oy = self.vib * math.sin(w), 0.0
        elif self.kind == "waveonce":
            if self.now >= self.cycle / 2:
                self.done = True; self.ox = self.oy = 0.0
            else:
                self.ox, self.oy = self.vib * math.sin(math.pi + w), 0.0
        elif self.kind == "jump":
            self.ox, self.oy = 0.0, self.vib * math.sin(w) + self.vib
        elif self.kind == "jumponce":
            if self.now >= self.cycle / 2:
                self.done = True; self.ox = self.oy = 0.0
            else:
                self.ox, self.oy = 0.0, self.vib * math.sin(math.pi + w) + self.vib
        elif self.kind == "fall":
            if self.now >= self.falltime:
                self.done = True; self.ox = self.oy = 0.0
            else:
                self.ox = 0.0
                self.oy = -self.distance + self.distance * self.now / self.falltime
        elif self.kind == "vibrate":
            if self.now >= self.next:
                self.ox = random.random() * self.vib - self.vib / 2
                self.oy = random.random() * self.vib
                self.next += self.wait


class LayerState:
    """An animatable layer. Props with an active tween interpolate; the rest are fixed."""
    def __init__(self):
        self.rows = None
        self.x = self.y = 0.0
        self.opacity = 100.0
        self.zoom = 100.0            # scale in % (100 = original size)
        self.tint = None            # multiplicative "#rrggbb", or None
        self.level = 0
        self.show = True
        self.tw = {}                 # prop -> Tween
        self.action = None           # Action (wave/vibrate) or None

    def target(self, prop, to, frm=None, dur=0, curve="linear"):
        if frm is not None and dur and frm != to:
            self.tw[prop] = Tween(frm, to, dur, curve)
            setattr(self, prop, float(frm))
        else:
            self.tw.pop(prop, None)
            setattr(self, prop, float(to))

    def tick(self, dt):
        for prop, t in list(self.tw.items()):
            t.tick(dt); setattr(self, prop, t.value)
            if t.done:
                setattr(self, prop, t.to); del self.tw[prop]
        if self.action:
            self.action.tick(dt)

    @property
    def offset(self):
        return (self.action.ox, self.action.oy) if self.action else (0.0, 0.0)

    @property
    def animating(self):
        return bool(self.tw) or (self.action is not None and not self.action.done)


class Engine:
    def __init__(self, disc, w=640, h=448):
        self.disc = disc
        self.font = disc.font
        self.W, self.H = w, h
        self.layers = {}
        self.speaker = None
        self.text = ""
        self.waiting = False         # stopped at a talk waiting for input
        self.done = False
        self._next = None
        self._thread = None
        self._base = None            # cached composite of the static layers
        self._base_sig = None
        self.R = self._root()

    # --- resources ---------------------------------------------------------
    def _rows(self, image):
        if image is None or BANK(image) != 0x02:
            return None
        try:
            return Texture(self.disc.textures.container[IDX(image)]).rgba()
        except Exception:
            return None

    # --- scene commands (natives exposed to the script) --------------------
    def cmd_reset(self, *a):
        self.layers.clear()

    def cmd_set(self, name, props):
        p = dict(props) if props else {}
        l = self.layers.setdefault(str(name), LayerState())
        if "image" in p:
            rows = self._rows(p["image"])
            if rows is not None:
                l.rows = rows
        if "level" in p: l.level = int(p["level"])
        if "show" in p: l.show = p["show"] not in (0, False)
        if "hide" in p and p["hide"]: l.show = False
        # movement curve from the sign of accel (LayerAccel/Normal/Decel, 0001.nut)
        acc = p.get("accel", 0)
        curve = "accel" if acc and acc > 0 else ("decel" if acc and acc < 0 else "linear")
        mt = p.get("moveTime", 0)
        if "x" in p: l.target("x", p["x"], p.get("xFrom"), mt, curve)
        if "y" in p: l.target("y", p["y"], p.get("yFrom"), mt, curve)
        if "opacity" in p:                              # the game's fades are linear
            l.target("opacity", p["opacity"], p.get("opacityFrom"), p.get("opacityTime", 0))
        if "action" in p:
            kind = {"LayerVibrateActionModule": "vibrate", "LayerWaveActionModule": "wave",
                    "LayerWaveOnceActionModule": "waveonce", "LayerJumpActionModule": "jump",
                    "LayerJumpOnceActionModule": "jumponce", "LayerFallActionModule": "fall"}.get(p["action"])
            if kind:
                l.action = Action(kind, p.get("vibration", 0), p.get("cycle", 0),
                                  p.get("waitTime", 0), p.get("distance", 0),
                                  p.get("falltime", p.get("moveTime", 0)))
        if p.get("stop") or p.get("reset"):
            l.action = None

    def cmd_talk(self, name, _u, text, voice=None):
        self.speaker, self.text = name, str(text)
        self.waiting = True
        sqrt._suspend()              # yield to the frontend; resumes in advance()
        self.waiting = False

    def cmd_next(self, scene_id=None, *a):
        self._next = IDX(scene_id) if scene_id is not None else None

    def cmd_isjump(self, *a):
        return True                  # live, we enter by establishing the scene

    # --- cycle -------------------------------------------------------------
    def load(self, scene_index):
        self._next = None
        src = self.disc.scenes[int(scene_index)]
        ns = {k: getattr(sqrt, k) for k in dir(sqrt) if not k.startswith("__")}
        ns["R"] = self.R
        code = compile(sqtranspile.transpile(src), f"<scene {scene_index}>", "exec")
        self._thread = sqrt.SqThread(lambda: exec(code, ns))
        self.done = False
        self._thread.call()          # runs until the first talk (or the end)
        self._after_run()

    def advance(self):
        """Wake the scene up until the next talk (or the end)."""
        if self.done or self._thread is None:
            return
        self._thread.wakeup()
        self._after_run()

    def _after_run(self):
        if self._thread.getstatus() == "dead":
            if self._next is not None:
                self.load(self._next)      # chain into the next scene
            else:
                self.done = True

    def tick(self, dt):
        for l in self.layers.values():
            l.tick(dt)

    def animating(self):
        return any(l.animating for l in self.layers.values())

    def _blit(self, fb, l):
        w = len(l.rows[0]) // 4
        ox, oy = l.offset
        ly = render.Layer().loadImage(l.rows)
        ly.setPos(int(l.x + ox) + self.W // 2 - w // 2, int(l.y + oy))
        ly.setOpacity(l.opacity)
        ly.draw(fb)

    def frame(self):
        # higher level = further back -> drawn first
        order = sorted((l for l in self.layers.values() if l.show and l.rows),
                       key=lambda s: -s.level)
        dyn = [l for l in order if l.animating]
        # cache valid only if all animated layers are in front (at the end)
        front = not dyn or [order.index(l) for l in dyn] == \
            list(range(len(order) - len(dyn), len(order)))
        if front:
            static = [l for l in order if l not in dyn]
            sig = tuple((id(l), int(l.x), int(l.y), int(l.opacity), l.level, id(l.rows))
                        for l in static)
            if sig != self._base_sig:
                base = render.Framebuffer(self.W, self.H)
                for l in static:
                    self._blit(base, l)
                self._base, self._base_sig = bytes(base.buf), sig
            fb = render.Framebuffer(self.W, self.H)
            fb.buf = bytearray(self._base)          # reuse the cached background
            for l in dyn:
                self._blit(fb, l)
        else:                                        # mixed z-order: recompose everything
            self._base_sig = None
            fb = render.Framebuffer(self.W, self.H)
            for l in order:
                self._blit(fb, l)
        if self.text:
            win = render.MessageWindow(self.font, x=32, y=self.H - 108, h=96)
            win.ShowNamePlate(self.speaker if self.speaker else 0)
            win.write(self.text)
            win.draw(fb)
        return fb

    # --- root with stubs ---------------------------------------------------
    def _root(self):
        R = _Root()
        R.update(sqrt.new_root())
        R["set"] = self.cmd_set
        R["talk"] = self.cmd_talk
        R["reset"] = self.cmd_reset
        R["next"] = self.cmd_next
        R["isJump"] = self.cmd_isjump
        return R


class _Root(dict):
    def __init__(self): super().__init__(); self.missing = set()
    def __missing__(self, key):
        self.missing.add(key); return lambda *a, **k: None


def demo():
    """Asset-free self-check: the tween interpolates and the tick/advance loop moves on."""
    l = LayerState()
    l.target("x", 100, frm=0, dur=200)
    assert l.x == 0.0 and l.animating
    l.tick(100); assert 49 <= l.x <= 51, l.x        # linear: halfway
    l.tick(100); assert l.x == 100.0 and not l.animating
    # no From: immediate set
    l.target("opacity", 50); assert l.opacity == 50.0 and "opacity" not in l.tw

    # exact curves (0001.nut): at t=0.5  accel=0.25, decel=0.75, normal=0.5
    assert ease("accel", 0.5) == 0.25 and ease("decel", 0.5) == 0.75 and ease("linear", 0.5) == 0.5
    la = LayerState(); la.target("x", 100, frm=0, dur=200, curve="accel")
    la.tick(100); assert 24 <= la.x <= 26, la.x     # t²·100 = 25
    ld = LayerState(); ld.target("x", 100, frm=0, dur=200, curve="decel")
    ld.tick(100); assert 74 <= ld.x <= 76, ld.x     # (1-(1-t)²)·100 = 75

    # wave action: dx = vib·sin(2π·now/cycle); at now=cycle/4 -> vib
    aw = Action("wave", vibration=10, cycle=400); aw.tick(100)
    assert 9.9 <= aw.ox <= 10.1 and aw.oy == 0.0, (aw.ox, aw.oy)
    # waveonce ends at cycle/2
    a1 = Action("waveonce", vibration=8, cycle=200); a1.tick(120)
    assert a1.done and a1.ox == 0.0
    # vibrate: shakes within range and downward in y
    av = Action("vibrate", vibration=12, wait=16); av.tick(20)
    assert -6.01 <= av.ox <= 6.01 and 0 <= av.oy <= 12, (av.ox, av.oy)
    # fall: dy = -distance + distance·now/fallTime  (falls from above to 0)
    af = Action("fall", distance=100, falltime=200); af.tick(50);  assert af.oy == -75.0, af.oy
    af.tick(50);   assert af.oy == -50.0, af.oy
    af.tick(100);  assert af.done and af.oy == 0.0
    # jump: dy = vib·sin(2π·now/cycle) + vib  (at cycle/4 -> 2·vib, always ≥0)
    aj = Action("jump", vibration=10, cycle=400); aj.tick(100)
    assert 19.9 <= aj.oy <= 20.1 and aj.ox == 0.0, (aj.ox, aj.oy)
    aj2 = Action("jump", vibration=10, cycle=400); aj2.tick(300)  # 3/4 -> sin=-1 -> 0
    assert -0.1 <= aj2.oy <= 0.1, aj2.oy
    # jumponce ends at cycle/2
    ajo = Action("jumponce", vibration=8, cycle=200); ajo.tick(120)
    assert ajo.done and ajo.oy == 0.0

    # engine with a fake disc: actually runs a transpiled "scene"
    class FakeCont:
        def __getitem__(self, i): raise KeyError
    class FakeScenes:
        def __getitem__(self, i):
            return ('reset();\ntalk("A", null, "hola", null);\n'
                    'talk("A", null, "chau", null);\n')
    class FakeDisc:
        class textures: container = FakeCont()
        scenes = FakeScenes(); font = None
    e = Engine(FakeDisc())
    e.load(0)
    assert e.waiting and e.text == "hola" and e.speaker == "A", (e.waiting, e.text)
    e.advance(); assert e.text == "chau"
    e.advance(); assert e.done
    print("demo OK")


if __name__ == "__main__":
    demo()
