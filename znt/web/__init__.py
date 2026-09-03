"""Frente WEB de VN Studio — opcional y separable, igual que `znt.gui`.

Sirve el editor por HTTP (stdlib `http.server`): Python sigue siendo la fuente de
verdad (modelo, assets, curvas, export) y el browser es la vista — compone las
capas con CSS, así el arrastre y el zoom van a 60fps y la tipografía es la del
sistema (sin el pantano de Tk/Xft). No duplica el engine.

    python -m znt web [proyecto.vn]

El core headless de `znt` no importa nada de acá: se puede borrar este paquete.
"""
from . import server

serve = server.serve
Studio = server.Studio


def demo():
    """Self-check del front web (headless)."""
    server.demo()
