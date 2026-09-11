"""WEB front end for VN Studio — optional and detachable, like `znt.gui`.

Serves the editor over HTTP (stdlib `http.server`): Python remains the source of
truth (model, assets, curves, export) and the browser is the view — it composes
the layers with CSS, so dragging and zooming run at 60fps and the typography is
the system's (none of the Tk/Xft swamp). It does not duplicate the engine.

    python -m znt web [project.vn]

The headless `znt` core imports nothing from here: this package can be deleted.
"""
from . import server

serve = server.serve
Studio = server.Studio


def demo():
    """Self-check of the web front end (headless)."""
    server.demo()
