"""Frentes interactivos (tkinter) de znt — TODOS opcionales.

Este subpaquete es el **front**: la ventana en vivo (`window.play`), el banco de
pruebas (`testbench`) y el editor VN Studio (`studio.run_editor`). El motor
headless (el resto de `znt`) no importa nada de acá: se puede **borrar
`znt/gui/` entero** y el core sigue funcionando (data, codec, render, runtime,
transpilador, `record` a APNG, y el runtime `VNRuntime` de VN).

tkinter se importa de forma perezosa (dentro de las funciones), así que importar
este paquete no requiere un display.
"""
from . import studio, testbench, window

run_editor = studio.run_editor
play = window.play


def demo():
    """Self-check headless de los frentes (Bench del engine, sin display)."""
    testbench.demo()      # imprime "demo OK"
