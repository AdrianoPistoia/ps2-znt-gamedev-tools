#!/usr/bin/env python3
"""CLI unificada del SDK.

  python -m znt demo                                  # self-check de todo
  python -m znt container info|unpack|pack ...        # par .HD/.BIN crudo
  python -m znt extract SCENE_ID.HD SCENE_ID.BIN out/ [.nut]   # descomprime
  python -m znt tim2 info|png ...
  python -m znt font info|png|widths ...
"""
import os, sys

from . import (container, codec, tim2, font, scriptscan, render, sqparse,
               sqtranspile, sqrt, sqrun, vn, engine, frontends, image, vnstudio, psf, vniso)
# El front interactivo (znt.gui) se importa de forma perezosa: el core no depende de él.


def extract(hd, bn, outdir, ext=".bin"):
    """Descomprime cada entrada de un par a un archivo suelto."""
    os.makedirs(outdir, exist_ok=True)
    c = container.Container(hd, bn)
    ok = bad = 0
    for i in range(len(c)):
        if len(c.raw(i)) < 8:
            continue
        d, err = codec.decompress(c.raw(i))
        if d is None:
            bad += 1
            sys.stderr.write(f"  #{i}: {err}\n")
            continue
        open(f"{outdir}/{i:04d}{ext}", "wb").write(d)
        ok += 1
    print(f"{ok} extraidas, {bad} fallaron -> {outdir}/")


def demo(*a):
    for m in (codec, container, tim2, font, scriptscan, render, sqparse, sqrt,
              sqtranspile, sqrun, vn, engine, frontends, image, vnstudio, psf, vniso):
        print(f"{m.__name__}:", end=" ")
        m.demo()
    try:                                  # el front es opcional
        from . import gui
        print("znt.gui:", end=" "); gui.demo()
    except ImportError:
        print("znt.gui: (ausente — core headless OK)")


def main(argv):
    if not argv or argv[0] == "demo":
        return demo()
    group, rest = argv[0], argv[1:]
    if group == "extract":
        return extract(*rest)
    if group == "scan":
        return scriptscan.cli(rest)
    if group == "render":
        return render.cli(rest)
    if group == "sqparse":
        return sqparse.cli(rest)
    if group == "sqtranspile":
        return sqtranspile.cli(rest)
    if group == "sqrun":
        return sqrun.cli(rest)
    if group == "vn":
        return vn.cli(rest)
    if group == "iso":
        return vniso.cli(rest)
    if group == "record":
        return frontends.record_cli(*rest)
    if group in ("play", "testbench", "studio"):    # front interactivo (opcional)
        try:
            from . import gui
        except ImportError:
            sys.exit("El front interactivo (znt.gui) no está disponible en esta distribución.")
        if group == "play":
            return gui.play(*rest)
        if group == "testbench":
            return gui.testbench.cli(rest)
        return gui.run_editor(rest[0] if rest else None)
    if group == "container":
        return {"unpack": container.unpack, "pack": container.pack,
                "info": container.info, "demo": container.demo}[rest[0]](*rest[1:])
    mod = {"tim2": tim2, "font": font}.get(group)
    if mod:
        return mod.cli(rest)
    sys.exit(__doc__)


def cli_entry():
    """Punto de entrada del comando `znt` (console_scripts)."""
    main(sys.argv[1:])


if __name__ == "__main__":
    main(sys.argv[1:])
