#!/usr/bin/env python3
"""Runner de escenas: integra transpilador + runtime + render para CORRER una
escena real del juego y sacar frames.

No reimplementa el engine entero. Implementa la capa de *comandos de escena* que
las escenas llaman de verdad (`set`, `talk`, `reset`, `next`, `isJump`, ...) sobre
el renderer de `render.py`, y deja un STUB por defecto para cualquier otro native:
así una escena corre de punta a punta aunque falte implementar comandos, y su
propia lógica (`if (isJump())`, ramas, loops) se ejecuta en la VM.

Direccionamiento de recursos del juego: `0x02000000 | idx` = textura de SCENEDAT,
`0x03..` = BGM, `0x04..` = voz, `0x01..` = id de escena.

  python -m znt sqrun <disc> <scene_index> <out.png>
"""
import sys

from . import sqrt, sqtranspile, render
from .tim2 import Texture

BANK = lambda v: (int(v) >> 24) & 0xFF
IDX = lambda v: int(v) & 0xFFFFFF


class Runner:
    def __init__(self, disc):
        self.disc = disc
        self.font = disc.font
        self.layers = {}        # nombre -> dict de props (incluye rows RGBA)
        self.frames = []        # PNGs compuestos, uno por talk
        self.last_talk = None
        self.stop = False
        self.R = self._root()

    # --- comandos de escena (los que llaman las escenas) -------------------
    def _texture(self, image):
        if image is None or BANK(image) != 0x02:
            return None
        try:
            return Texture(self.disc.textures.container[IDX(image)]).rgba()
        except Exception:
            return None

    def cmd_reset(self, *a):
        self.layers.clear()

    def cmd_set(self, name, props):
        lyr = self.layers.setdefault(str(name), {})
        p = dict(props) if props else {}
        if "image" in p:
            rows = self._texture(p["image"])
            if rows is not None:
                lyr["rows"] = rows
        for k in ("x", "y", "level", "opacity", "show"):
            if k in p:
                lyr[k] = p[k]

    def cmd_talk(self, name, _unused, text, voice=None):
        self.last_talk = (name, text)
        self.frames.append(self._compose(name, text))

    def cmd_next(self, scene_id=None, *a):
        self.stop = True

    def cmd_isjump(self, *a):
        return False        # primera pasada: no venimos de un jump

    def _compose(self, name, text):
        sc = render.Scene(640, 448)
        # nivel mayor = mas al fondo (los datos: stage=200 detras, chars=160)
        for lname, l in sorted(self.layers.items(), key=lambda kv: -kv[1].get("level", 0)):
            if not l.get("rows") or l.get("show", 1) in (0, False):
                continue
            ly = render.Layer().loadImage(l["rows"])
            ly.setPos(l.get("x", 0) + 320 - len(l["rows"][0])//8, l.get("y", 0))
            ly.setLevel(-l.get("level", 0))
            ly.setOpacity(l.get("opacity", 100))
            sc.add(ly)
        win = render.MessageWindow(self.font, x=32, y=340, h=96)
        win.ShowNamePlate(str(name) if name else 0)
        win.write(str(text))
        sc.window = win
        return sc.compose()

    # --- root table con stubs ----------------------------------------------
    def _root(self):
        R = _Root(self)
        R.update(sqrt.new_root())
        R["set"] = self.cmd_set
        R["talk"] = self.cmd_talk
        R["reset"] = self.cmd_reset
        R["next"] = self.cmd_next
        R["isJump"] = self.cmd_isjump
        return R

    def run(self, scene_index):
        src = self.disc.scenes[int(scene_index)]
        ns = {k: getattr(sqrt, k) for k in dir(sqrt) if not k.startswith("__")}
        ns["R"] = self.R
        py = sqtranspile.transpile(src)
        exec(compile(py, f"<scene {scene_index}>", "exec"), ns)
        return self.frames


class _Root(dict):
    """Root table: lo que falta devuelve un stub que registra y no rompe."""
    def __init__(self, runner):
        super().__init__(); self._runner = runner; self.missing = set()
    def __missing__(self, key):
        self.missing.add(key)
        return lambda *a, **k: None      # native no implementado: no-op


def run_scene(disc_path, scene_index, out):
    import znt
    disc = znt.open(disc_path)
    r = Runner(disc)
    frames = r.run(scene_index)
    if not frames:
        print(f"escena {scene_index}: corrió sin talks (0 frames)")
    else:
        frames[0].png(out)
        print(f"escena {scene_index}: {len(frames)} frames, primero -> {out}")
    if r.R.missing:
        print("natives no implementados (stub):", ", ".join(sorted(r.R.missing)))
    return out


def demo():
    """Self-check sin assets: los comandos de escena manejan capas y frames."""
    class FakeCont:
        def __getitem__(self, i): raise KeyError
    class FakeDisc:
        class textures: container = FakeCont()
        font = None
    r = Runner.__new__(Runner)
    r.disc = None; r.layers = {}; r.frames = []; r.last_talk = None
    r.cmd_set("bg", sqrt.Table({"level": 200, "x": 0}))
    assert "bg" in r.layers and r.layers["bg"]["level"] == 200
    r.cmd_reset()
    assert r.layers == {}
    assert r.cmd_isjump() is False
    print("demo OK")


def cli(argv):
    if not argv or argv[0] == "demo": return demo()
    run_scene(argv[0], argv[1], argv[2])


if __name__ == "__main__":
    cli(sys.argv[1:])
