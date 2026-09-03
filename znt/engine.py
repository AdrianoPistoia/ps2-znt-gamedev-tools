#!/usr/bin/env python3
"""Core del runtime en vivo — headless y desacoplado del frontend.

El engine mantiene el estado de la escena (capas con animación, cuadro de
diálogo), avanza el tiempo (`tick`) y compone el frame actual (`frame`) sobre un
framebuffer. No sabe NADA de la pantalla: un frontend (ventana tkinter, export
APNG, ...) lo maneja llamando tick/frame/advance y devolviéndole input.

La animación sale de las props que ya trae cada `set` de la escena
(`xFrom`→`x` en `moveTime`, `opacityFrom`→`opacity` en `opacityTime`): son un
tween. El `talk` suspende la corrutina de la escena (stackful, de `sqrt`); el
frontend anima mientras espera y hace `advance()` para despertarla.

Contrato para el frontend:
    e = Engine(disc); e.load(1000)
    while not e.done:
        e.tick(dt_ms)                 # avanza animaciones
        fb = e.frame()                # framebuffer actual (render.Framebuffer)
        present(fb)                    # <- lo dibuja el frontend
        if user_click and e.waiting:  # e.waiting == parado en un talk
            e.advance()
    # e.speaker / e.text = diálogo actual ; e.animating() = hay tweens vivos
"""
import sys

from . import render, sqrt, sqtranspile
from .tim2 import Texture

IDX = lambda v: int(v) & 0xFFFFFF
BANK = lambda v: (int(v) >> 24) & 0xFF


class Tween:
    __slots__ = ("frm", "to", "dur", "t")
    def __init__(self, frm, to, dur):
        self.frm, self.to, self.dur, self.t = float(frm), float(to), max(1.0, float(dur)), 0.0
    def tick(self, dt): self.t = min(self.dur, self.t + dt)
    @property
    def done(self): return self.t >= self.dur
    @property
    def value(self):
        k = self.t / self.dur
        return self.frm + (self.to - self.frm) * k


class LayerState:
    """Una capa animable. Props con tween activo interpolan; el resto son fijas."""
    def __init__(self):
        self.rows = None
        self.x = self.y = 0.0
        self.opacity = 100.0
        self.level = 0
        self.show = True
        self.tw = {}                 # prop -> Tween

    def target(self, prop, to, frm=None, dur=0):
        if frm is not None and dur and frm != to:
            self.tw[prop] = Tween(frm, to, dur)
            setattr(self, prop, float(frm))
        else:
            self.tw.pop(prop, None)
            setattr(self, prop, float(to))

    def tick(self, dt):
        for prop, t in list(self.tw.items()):
            t.tick(dt); setattr(self, prop, t.value)
            if t.done:
                setattr(self, prop, t.to); del self.tw[prop]

    @property
    def animating(self): return bool(self.tw)


class Engine:
    def __init__(self, disc, w=640, h=448):
        self.disc = disc
        self.font = disc.font
        self.W, self.H = w, h
        self.layers = {}
        self.speaker = None
        self.text = ""
        self.waiting = False         # parado en un talk esperando input
        self.done = False
        self._next = None
        self._thread = None
        self.R = self._root()

    # --- recursos ----------------------------------------------------------
    def _rows(self, image):
        if image is None or BANK(image) != 0x02:
            return None
        try:
            return Texture(self.disc.textures.container[IDX(image)]).rgba()
        except Exception:
            return None

    # --- comandos de escena (nativos hacia el script) ----------------------
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
        if "x" in p: l.target("x", p["x"], p.get("xFrom"), p.get("moveTime", 0))
        if "y" in p: l.target("y", p["y"], p.get("yFrom"), p.get("moveTime", 0))
        if "opacity" in p:
            l.target("opacity", p["opacity"], p.get("opacityFrom"), p.get("opacityTime", 0))

    def cmd_talk(self, name, _u, text, voice=None):
        self.speaker, self.text = name, str(text)
        self.waiting = True
        sqrt._suspend()              # cede al frontend; se reanuda en advance()
        self.waiting = False

    def cmd_next(self, scene_id=None, *a):
        self._next = IDX(scene_id) if scene_id is not None else None

    def cmd_isjump(self, *a):
        return True                  # en vivo entramos estableciendo la escena

    # --- ciclo -------------------------------------------------------------
    def load(self, scene_index):
        self._next = None
        src = self.disc.scenes[int(scene_index)]
        ns = {k: getattr(sqrt, k) for k in dir(sqrt) if not k.startswith("__")}
        ns["R"] = self.R
        code = compile(sqtranspile.transpile(src), f"<scene {scene_index}>", "exec")
        self._thread = sqrt.SqThread(lambda: exec(code, ns))
        self.done = False
        self._thread.call()          # corre hasta el primer talk (o el final)
        self._after_run()

    def advance(self):
        """Despierta la escena hasta el próximo talk (o el final)."""
        if self.done or self._thread is None:
            return
        self._thread.wakeup()
        self._after_run()

    def _after_run(self):
        if self._thread.getstatus() == "dead":
            if self._next is not None:
                self.load(self._next)      # encadena a la escena siguiente
            else:
                self.done = True

    def tick(self, dt):
        for l in self.layers.values():
            l.tick(dt)

    def animating(self):
        return any(l.animating for l in self.layers.values())

    def frame(self):
        fb = render.Framebuffer(self.W, self.H)
        for l in sorted(self.layers.values(), key=lambda s: -s.level):
            if not l.rows or not l.show:
                continue
            w = len(l.rows[0]) // 4
            ly = render.Layer().loadImage(l.rows)
            ly.setPos(int(l.x) + self.W // 2 - w // 2, int(l.y))
            ly.setOpacity(l.opacity)
            ly.draw(fb)
        if self.text:
            win = render.MessageWindow(self.font, x=32, y=self.H - 108, h=96)
            win.ShowNamePlate(self.speaker if self.speaker else 0)
            win.write(self.text)
            win.draw(fb)
        return fb

    # --- root con stubs ----------------------------------------------------
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
    """Self-check sin assets: el tween interpola y el loop tick/advance avanza."""
    l = LayerState()
    l.target("x", 100, frm=0, dur=200)
    assert l.x == 0.0 and l.animating
    l.tick(100); assert 49 <= l.x <= 51, l.x        # mitad
    l.tick(100); assert l.x == 100.0 and not l.animating
    # sin From: set inmediato
    l.target("opacity", 50); assert l.opacity == 50.0 and "opacity" not in l.tw

    # engine con un disc falso: corre una "escena" transpilada de verdad
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
