#!/usr/bin/env python3
"""Motor de dibujo de la capa 1: implementa en el host las dos clases nativas del
engine (`Layer`, `MessageWindow`) sobre un framebuffer RGB, y compone una escena
a PNG. Sin dependencias: usa el lector TIM2 y la fuente de la capa 2.

Es la mitad "sin incognitas" del runtime off-console. La VM Squirrel (que decide
QUE se dibuja) va aparte; aca esta el COMO. El driver `demo_scene` prueba el
pipeline con un frame armado a mano.

Resolucion nativa del juego: 512x448 (PS2 NTSC). Se puede cambiar.
"""
import struct, sys, zlib

from .tim2 import Texture
from .font import CELL_W, CELL_H

SCREEN_W, SCREEN_H = 512, 448


class Framebuffer:
    """Lienzo RGB. Se compone contra un fondo opaco; el alfa se mezcla al vuelo."""

    def __init__(self, w=SCREEN_W, h=SCREEN_H, bg=(0, 0, 0)):
        self.w, self.h = w, h
        self.buf = bytearray(bytes(bg) * (w * h))

    def blit_rgba(self, rows, x, y, opacity=100, tint=None):
        """Mezcla filas RGBA en (x,y). opacity 0..100. tint = (r,g,b) 0..100."""
        op = max(0, min(100, opacity))
        if op == 0 or not rows:
            return
        sh = len(rows); sw = len(rows[0]) // 4
        tr, tg, tb = tint if tint else (100, 100, 100)
        for j in range(sh):
            py = y + j
            if py < 0 or py >= self.h:
                continue
            row = rows[j]
            base = py * self.w
            for i in range(sw):
                px = x + i
                if px < 0 or px >= self.w:
                    continue
                r, g, b, a = row[i*4:i*4+4]
                a = a * op // 100
                if a == 0:
                    continue
                o = base * 3 + px * 3
                if a >= 255 and tint is None:
                    self.buf[o:o+3] = bytes((r, g, b))
                    continue
                r = r * tr // 100; g = g * tg // 100; b = b * tb // 100
                ia = 255 - a
                self.buf[o]   = (self.buf[o]   * ia + r * a) // 255
                self.buf[o+1] = (self.buf[o+1] * ia + g * a) // 255
                self.buf[o+2] = (self.buf[o+2] * ia + b * a) // 255

    def fill_rect(self, x, y, w, h, color, opacity=100):
        a = max(0, min(100, opacity)) * 255 // 100
        cr, cg, cb = color; ia = 255 - a
        for py in range(max(0, y), min(self.h, y + h)):
            base = py * self.w
            for px in range(max(0, x), min(self.w, x + w)):
                o = base * 3 + px * 3
                self.buf[o]   = (self.buf[o]   * ia + cr * a) // 255
                self.buf[o+1] = (self.buf[o+1] * ia + cg * a) // 255
                self.buf[o+2] = (self.buf[o+2] * ia + cb * a) // 255

    def png(self, path):
        raw = bytearray()
        for y in range(self.h):
            raw.append(0)
            raw += self.buf[y*self.w*3:(y+1)*self.w*3]
        def ch(tag, data):
            c = tag + data
            return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))
        open(path, "wb").write(b"\x89PNG\r\n\x1a\n"
            + ch(b"IHDR", struct.pack(">IIBBBBB", self.w, self.h, 8, 2, 0, 0, 0))
            + ch(b"IDAT", zlib.compress(bytes(raw), 6)) + ch(b"IEND", b""))
        return self.w, self.h


class Layer:
    """Equivalente en el host de la clase nativa `Layer` (ver docs/engine_api.md).

    Modela los metodos que las escenas usan; los que aun no dibujan quedan como
    stubs que no rompen el flujo (setAffineOrigin, setActionOffset, etc.)."""

    def __init__(self, foreground=True, disc=None):
        self.foreground = foreground
        self.disc = disc                 # para loadImage por indice de textura
        self._rows = None                # RGBA cacheado de la imagen cargada
        self.x = self.y = 0
        self.level = 0
        self.opacity = 100
        self.color = None                # (r,g,b) tint 0..100, None = sin tinte
        self.visible = True

    def loadImage(self, image):
        """image: filas RGBA ya listas, una Texture, o un indice de SCENEDAT."""
        if isinstance(image, list):
            self._rows = image
        elif isinstance(image, Texture):
            self._rows = image.rgba()
        elif self.disc is not None:
            self._rows = Texture(self.disc.textures.container[int(image)]).rgba()
        else:
            raise ValueError("loadImage necesita un disc para resolver por indice")
        return self

    def setPos(self, x, y): self.x, self.y = int(x), int(y); return self
    def setLevel(self, n): self.level = int(n); return self
    def setOpacity(self, a): self.opacity = int(a); return self
    def getOpacity(self): return self.opacity
    def setColor(self, r, g, b, a=None): self.color = (int(r), int(g), int(b)); return self
    def show(self, v=True): self.visible = bool(v); return self

    def draw(self, fb):
        if self.visible and self._rows:
            fb.blit_rgba(self._rows, self.x, self.y, self.opacity, self.color)

    # stubs: aceptan la llamada, todavia no afectan el frame estatico
    def setZoom(self, *a): return self
    def setRotate(self, *a): return self
    def setActionOffset(self, *a): return self
    def setAffineOrigin(self, *a): return self
    def stopAction(self, *a): return self


class MessageWindow:
    """Equivalente en el host de `MessageWindow`: caja semitransparente + texto
    monoespaciado con la fuente del juego (celdas de 24x26)."""

    def __init__(self, font, x=32, y=340, mode=1, w=None, h=96):
        self.font = font
        self.x, self.y, self.w, self.h = x, y, (w or SCREEN_W - 2*x), h
        self.name = None
        self.lines = []
        self.visible = True

    def ShowNamePlate(self, name):
        self.name = None if name in (0, None, "") else str(name)
        return self

    def write(self, text):
        self.lines = str(text).split("\n")
        return self

    def clear(self): self.lines = []; self.name = None; return self
    def showCursor(self, *a): return self
    def fore(self, *a): return self
    def back(self, *a): return self

    def _glyph(self, ch):
        cell = self.font.cell(ch)
        if not cell:
            return None
        # 1bpp (0/255) -> RGBA blanco con alfa = intensidad
        return [b"".join(bytes((255, 255, 255, v)) for v in row) for row in cell]

    def _draw_text(self, fb, text, x, y):
        cx = x
        for ch in text:
            if ch == " ":
                cx += CELL_W // 2
                continue
            g = self._glyph(ch)
            if g:
                fb.blit_rgba(g, cx, y)
            cx += CELL_W

    def draw(self, fb):
        if not self.visible:
            return
        fb.fill_rect(self.x, self.y, self.w, self.h, (0, 0, 40), 65)   # caja azulada
        ty = self.y + 8
        if self.name:
            self._draw_text(fb, self.name, self.x + 8, self.y - CELL_H - 2)
        for line in self.lines:
            self._draw_text(fb, line, self.x + 12, ty)
            ty += CELL_H + 2


class Scene:
    """Reune capas + un cuadro de dialogo y compone el frame."""

    def __init__(self, w=SCREEN_W, h=SCREEN_H):
        self.fb = Framebuffer(w, h)
        self.layers = []
        self.window = None

    def add(self, layer):
        self.layers.append(layer); return layer

    def compose(self):
        for lyr in sorted(self.layers, key=lambda l: l.level):
            lyr.draw(self.fb)
        if self.window:
            self.window.draw(self.fb)
        return self.fb


def demo_scene(disc_path, out, bg=10, name="ルイズ",
               text="ゼロの使い魔へようこそ。\nこれはレンダラのテストです。"):
    """Compone un frame real: fondo de SCENEDAT + cuadro de dialogo con la fuente
    del juego. Prueba el pipeline de render de punta a punta con assets reales."""
    import znt
    global SCREEN_W, SCREEN_H
    SCREEN_W, SCREEN_H = 640, 448
    disc = znt.open(disc_path)
    sc = Scene(640, 448)
    sc.add(Layer(foreground=False).loadImage(
        Texture(disc.textures.container[int(bg)]).rgba()).setLevel(0))
    win = MessageWindow(disc.font, x=32, y=340, h=96)
    win.ShowNamePlate(name)
    win.write(text)
    sc.window = win
    w, h = sc.compose().png(out)
    print(f"frame {w}x{h} -> {out}")
    return out


def demo():
    """Self-check sin assets: blit RGBA con alfa y clipping, y PNG valido."""
    fb = Framebuffer(4, 2, bg=(0, 0, 0))
    # una fila RGBA: rojo opaco, verde a medio alfa, fuera de rango (clip)
    row = bytes((255, 0, 0, 255)) + bytes((0, 255, 0, 128))
    fb.blit_rgba([row], 0, 0)
    assert fb.buf[0:3] == bytes((255, 0, 0)), fb.buf[0:3]
    # verde a 128/255 sobre negro -> ~ (0,128,0)
    assert fb.buf[3] == 0 and 120 <= fb.buf[4] <= 130, fb.buf[3:6]
    # blit con y fuera de rango no rompe
    fb.blit_rgba([row], 0, 5)
    import io, tempfile, os
    p = tempfile.mktemp(suffix=".png")
    w, h = fb.png(p)
    assert (w, h) == (4, 2) and open(p, "rb").read(8) == b"\x89PNG\r\n\x1a\n"
    os.remove(p)
    print("demo OK")


def cli(argv):
    if not argv or argv[0] == "demo":
        return demo()
    disc_path, out = argv[0], argv[1]
    bg = int(argv[2]) if len(argv) > 2 else 10
    demo_scene(disc_path, out, bg)


if __name__ == "__main__":
    cli(sys.argv[1:])
