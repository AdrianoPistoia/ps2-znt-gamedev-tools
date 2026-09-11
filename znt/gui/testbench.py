#!/usr/bin/env python3
"""Live test bench — a frontend to *use and drive* the real engine.

It reimplements nothing: it drives the actual `engine`. You load a scene, step
through the dialogue, and **inject animations live** onto the real layers (pick
a layer + movement curve or action-offset + parameters and watch it move), with
an inspector of each layer's state. Useful for eyeballing the curves
(accel/decel) and offsets (wave/jump/fall/vibrate) on the game's sprites.

    python -m znt testbench <disc> [scene]      # tkinter window (needs a display)

The core (`Bench`) is headless and does not import tkinter: it can be scripted without UI.
"""
import sys

from ..engine import Engine, Action, CURVES

ACTIONS = ("wave", "waveonce", "jump", "jumponce", "fall", "vibrate")


class Bench:
    """API to drive the engine live. No UI: the window sits on top of it."""
    def __init__(self, disc):
        self.e = Engine(disc)
        self.scene = None

    def load(self, scene, jump=True):
        self.e.R["isJump"] = (lambda *a: True) if jump else (lambda *a: False)
        self.e.load(int(scene)); self.scene = int(scene)

    def advance(self):
        self.e.advance()

    def reset(self):
        if self.scene is not None:
            self.load(self.scene)

    def layer_names(self):
        return sorted(self.e.layers, key=lambda n: -self.e.layers[n].level)

    def inject_move(self, name, x=None, y=None, time=500, curve="linear"):
        """Fire a movement tween on a layer (to test the curves)."""
        l = self.e.layers.get(name)
        if not l: return
        if x is not None: l.target("x", x, frm=l.x, dur=time, curve=curve)
        if y is not None: l.target("y", y, frm=l.y, dur=time, curve=curve)

    def inject_action(self, name, kind, **params):
        """Apply an action-offset (wave/jump/fall/vibrate...) to a layer live."""
        l = self.e.layers.get(name)
        if l is not None:
            l.action = Action(kind, params.get("vibration", 16), params.get("cycle", 320),
                              params.get("wait", 40), params.get("distance", 120),
                              params.get("falltime", 600))

    def clear_action(self, name):
        l = self.e.layers.get(name)
        if l: l.action = None

    def tick(self, dt):
        self.e.tick(dt)

    def frame(self):
        return self.e.frame()

    def inspect(self):
        """Each layer's state as readable lines (for the inspector)."""
        out = []
        for n in self.layer_names():
            l = self.e.layers[n]
            tw = ",".join(f"{k}:{int(t.t/t.dur*100)}%({t.curve})" for k, t in l.tw.items())
            act = ""
            if l.action:
                a = l.action
                act = f" act={a.kind}({a.ox:+.0f},{a.oy:+.0f}){'·done' if a.done else ''}"
            out.append(f"{n:8} x={l.x:6.0f} y={l.y:5.0f} op={l.opacity:3.0f} "
                       f"lv={l.level:3} {'vis' if l.show else 'hid'} "
                       f"{'tw['+tw+']' if tw else '':<22}{act}")
        return out

    @property
    def status(self):
        e = self.e
        st = "done" if e.done else ("talk" if e.waiting else "running")
        return f"scene {self.scene} · {st} · {e.speaker or '—'}: {e.text[:40]}"


# --- tkinter UI (optional; the engine does not import it) -------------------
def run_window(disc, scene=None):
    import tkinter as tk
    from tkinter import ttk
    import base64

    b = Bench(disc)
    dt = 33   # ~30fps
    dirty = {"f": True}                     # request a re-render after each control
    def mark(): dirty["f"] = True

    root = tk.Tk(); root.title("znt · test bench")
    root.configure(bg="#0d1017")
    left = tk.Frame(root, bg="#0d1017"); left.grid(row=0, column=0, padx=8, pady=8)
    right = tk.Frame(root, bg="#0d1017"); right.grid(row=0, column=1, padx=8, pady=8, sticky="n")

    canvas = tk.Canvas(left, width=b.e.W, height=b.e.H, highlightthickness=1,
                       highlightbackground="#2a3350", bg="black")
    canvas.pack()
    item = canvas.create_image(0, 0, anchor="nw")
    imgref = {}

    def mono(w): return dict(bg="#141a28", fg="#cfe3ff", insertbackground="#cfe3ff",
                             relief="flat", font=("monospace", 10))

    # --- controls ----------------------------------------------------------
    def row(parent):
        f = tk.Frame(parent, bg="#0d1017"); f.pack(fill="x", pady=2); return f
    def label(parent, t):
        tk.Label(parent, text=t, bg="#0d1017", fg="#8aa0c8",
                 font=("monospace", 9)).pack(side="left")

    r = row(right); label(r, "scene "); scene_var = tk.StringVar(value=str(scene or 1000))
    tk.Entry(r, textvariable=scene_var, width=6, **mono(r)).pack(side="left")
    jump_var = tk.BooleanVar(value=True)
    tk.Checkbutton(r, text="jump-in", variable=jump_var, bg="#0d1017", fg="#8aa0c8",
                   selectcolor="#141a28", font=("monospace", 9)).pack(side="left")

    def load():
        try:
            b.load(int(scene_var.get()), jump=jump_var.get()); refresh_layers(); mark()
        except Exception as ex:
            status_var.set(f"error: {ex}")
    def adv(): b.advance(); refresh_layers(); mark()
    def rst(): b.reset(); refresh_layers(); mark()

    r = row(right)
    for t, fn in (("Load", load), ("Advance ▸", adv), ("Reset", rst)):
        tk.Button(r, text=t, command=fn, bg="#1b2440",
                  fg="#cfe3ff", relief="flat", font=("monospace", 9),
                  activebackground="#26335c").pack(side="left", padx=2)

    tk.Label(right, text="—— animate a layer ——", bg="#0d1017", fg="#4f6089",
             font=("monospace", 9)).pack(pady=(10, 2))
    r = row(right); label(r, "layer "); layer_var = tk.StringVar()
    layer_box = ttk.Combobox(r, textvariable=layer_var, width=10, state="readonly")
    layer_box.pack(side="left")

    r = row(right); label(r, "move x→ ")
    movex = tk.Scale(r, from_=-320, to=320, orient="horizontal", length=150,
                     bg="#0d1017", fg="#cfe3ff", troughcolor="#141a28",
                     highlightthickness=0, font=("monospace", 8))
    movex.set(0); movex.pack(side="left")
    r = row(right); label(r, "curve "); curve_var = tk.StringVar(value="accel")
    ttk.Combobox(r, textvariable=curve_var, width=8, values=CURVES,
                 state="readonly").pack(side="left")
    label(r, " t(ms) "); time_var = tk.StringVar(value="600")
    tk.Entry(r, textvariable=time_var, width=6, **mono(r)).pack(side="left")

    def do_move():
        if layer_var.get():
            b.inject_move(layer_var.get(), x=movex.get(), time=int(time_var.get()),
                          curve=curve_var.get())
    tk.Button(right, text="Move along the curve", command=do_move, bg="#1b2440",
              fg="#cfe3ff", relief="flat", font=("monospace", 9),
              activebackground="#26335c").pack(fill="x", pady=2)

    r = row(right); label(r, "action "); act_var = tk.StringVar(value="jump")
    ttk.Combobox(r, textvariable=act_var, width=10, values=ACTIONS,
                 state="readonly").pack(side="left")
    r = row(right); label(r, "vib "); vib = tk.Scale(r, from_=0, to=60, orient="horizontal",
        length=90, bg="#0d1017", fg="#cfe3ff", troughcolor="#141a28", highlightthickness=0,
        font=("monospace", 8)); vib.set(18); vib.pack(side="left")
    label(r, "cycle "); cyc = tk.Scale(r, from_=60, to=1200, orient="horizontal",
        length=90, bg="#0d1017", fg="#cfe3ff", troughcolor="#141a28", highlightthickness=0,
        font=("monospace", 8)); cyc.set(340); cyc.pack(side="left")

    def do_action():
        if layer_var.get():
            b.inject_action(layer_var.get(), act_var.get(), vibration=vib.get(),
                            cycle=cyc.get(), distance=140, falltime=cyc.get())
    def stop_action():
        if layer_var.get(): b.clear_action(layer_var.get()); mark()
    r = row(right)
    tk.Button(r, text="Apply action", command=do_action, bg="#1b2440", fg="#cfe3ff",
              relief="flat", font=("monospace", 9), activebackground="#26335c").pack(side="left", padx=2)
    tk.Button(r, text="Stop", command=stop_action, bg="#2a1b2b", fg="#e8b0c0",
              relief="flat", font=("monospace", 9), activebackground="#3c2640").pack(side="left")

    status_var = tk.StringVar(value="load a scene")
    tk.Label(right, textvariable=status_var, bg="#0d1017", fg="#8aa0c8",
             font=("monospace", 9), wraplength=280, justify="left").pack(pady=(10, 2))
    inspector = tk.Text(right, width=52, height=12, **mono(right)); inspector.pack()

    def refresh_layers():
        layer_box["values"] = b.layer_names()
        if b.layer_names() and not layer_var.get():
            layer_var.set(b.layer_names()[0])

    def loop():
        b.tick(dt)
        # only re-render if something moves or there was a change (dirty). Idle,
        # the frame does not change -> no re-encode (idle 60fps for free).
        if b.e.animating() or dirty.pop("f", False):
            fb = b.frame()
            imgref["i"] = tk.PhotoImage(data=base64.b64encode(fb.png_bytes(1)))  # level 1: fast encode
            canvas.itemconfig(item, image=imgref["i"])
            status_var.set(b.status)
            inspector.delete("1.0", "end"); inspector.insert("1.0", "\n".join(b.inspect()))
        root.after(dt, loop)

    canvas.bind("<Button-1>", lambda e: adv())
    root.bind("<space>", lambda e: adv())
    if scene is not None:
        load()
    loop()
    root.mainloop()


def demo():
    """Headless self-check of the core: inject animations and verify the state."""
    class FakeCont:
        def __getitem__(self, i): raise KeyError
    class FakeScenes:
        def __getitem__(self, i):
            return ('reset();\nset("hero",{x=0,y=0,level=10,show=1});\n'
                    'talk("H", null, "hola", null);\n')
    class FakeDisc:
        class textures: container = FakeCont()
        scenes = FakeScenes(); font = None
    b = Bench(FakeDisc())
    b.load(0)
    assert "hero" in b.layer_names(), b.layer_names()
    # inject a jump action and check the offset changes over time
    b.inject_action("hero", "jump", vibration=10, cycle=400)
    b.tick(100)
    assert b.e.layers["hero"].action.oy > 0, b.e.layers["hero"].action.oy
    # inject a curved move and check the tween starts
    b.inject_move("hero", x=100, time=400, curve="accel")
    assert "x" in b.e.layers["hero"].tw and b.e.layers["hero"].tw["x"].curve == "accel"
    lines = b.inspect()
    assert any("hero" in ln and "act=jump" in ln for ln in lines), lines
    assert "talk" in b.status
    print("demo OK")


def cli(argv):
    if not argv or argv[0] == "demo":
        return demo()
    import znt
    disc = znt.open(argv[0])
    run_window(disc, int(argv[1]) if len(argv) > 1 else None)


if __name__ == "__main__":
    cli(sys.argv[1:])
