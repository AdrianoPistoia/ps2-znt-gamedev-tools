#!/usr/bin/env python3
"""Ventana en vivo (tkinter) que reproduce una escena con el `engine` real.
Frontend interactivo — el core no lo importa. tkinter se importa lazy."""
import base64

from ..engine import Engine


class TkWindow:
    """Frontend en vivo. Requiere un display. No lo importa el engine."""
    def __init__(self, engine, scale=1, fps=60):
        self.e = engine; self.scale = scale; self.dt = 1000 // fps
        self._img = None; self._dirty = True

    def _present(self, canvas, item):
        import tkinter as tk
        fb = self.e.frame()
        self._img = tk.PhotoImage(data=base64.b64encode(fb.png_bytes(1)))   # nivel 1: encode rápido
        if self.scale > 1:
            self._img = self._img.zoom(self.scale)
        canvas.itemconfig(item, image=self._img)

    def run(self, scene):
        import tkinter as tk
        self.e.load(scene)
        root = tk.Tk(); root.title("znt engine")
        W, H = self.e.W * self.scale, self.e.H * self.scale
        canvas = tk.Canvas(root, width=W, height=H, highlightthickness=0, bg="black")
        canvas.pack()
        item = canvas.create_image(0, 0, anchor="nw")

        self._dirty = True
        def click(_=None):
            if self.e.waiting and not self.e.animating():
                self.e.advance(); self._dirty = True
        for ev in ("<Button-1>", "<space>", "<Return>"):
            root.bind(ev, click)
        root.bind("<Escape>", lambda _: root.destroy())

        def loop():
            if self.e.done:
                return
            self.e.tick(self.dt)
            if self.e.animating() or self._dirty:      # en reposo no re-renderiza
                self._present(canvas, item); self._dirty = False
            root.after(self.dt, loop)
        loop()
        root.mainloop()


def play(disc_path, scene, scale=1):
    import znt
    TkWindow(Engine(znt.open(disc_path)), scale=int(scale)).run(int(scene))
