"""Interactive (tkinter) frontends for znt — ALL optional.

This subpackage is the **frontend**: the live window (`window.play`), the test
bench (`testbench`) and the VN Studio editor (`studio.run_editor`). The headless
engine (the rest of `znt`) imports nothing from here: you can **delete
`znt/gui/` entirely** and the core keeps working (data, codec, render, runtime,
transpiler, `record` to APNG, and the VN `VNRuntime`).

tkinter is imported lazily (inside the functions), so importing this package
does not require a display.
"""
from . import studio, testbench, window

run_editor = studio.run_editor
play = window.play


def demo():
    """Headless self-check of the frontends (engine Bench, no display)."""
    testbench.demo()      # prints "demo OK"
