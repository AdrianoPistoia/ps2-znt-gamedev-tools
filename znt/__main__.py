#!/usr/bin/env python3
"""Unified SDK CLI.

  python -m znt demo                                  # self-check of everything
  python -m znt container info|unpack|pack ...        # raw .HD/.BIN pair
  python -m znt extract SCENE_ID.HD SCENE_ID.BIN out/ [.nut]   # decompress
  python -m znt web [project.vn] [--port N] [--restart|--stop]   # web editor
  python -m znt tim2 info|png ...
  python -m znt font info|png|widths ...
"""
import os, sys

from . import (container, codec, tim2, font, scriptscan, render, sqparse,
               sqtranspile, sqrt, sqrun, vn, engine, frontends, image, vnstudio, psf, vniso, adpcm, quant)
# The interactive front end (znt.gui) is imported lazily: the core does not depend on it.


def extract(hd, bn, outdir, ext=".bin"):
    """Decompresses each entry of a pair to a separate file."""
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
    print(f"{ok} extracted, {bad} failed -> {outdir}/")


def demo(*a):
    for m in (codec, container, tim2, font, scriptscan, render, sqparse, sqrt,
              sqtranspile, sqrun, vn, engine, frontends, image, vnstudio, psf, vniso, adpcm, quant):
        print(f"{m.__name__}:", end=" ")
        m.demo()
    for name, mod in (("znt.gui", "gui"), ("znt.web", "web")):   # optional front ends
        try:
            m = __import__(f"znt.{mod}", fromlist=["demo"])
            print(f"{name}:", end=" "); m.demo()
        except ImportError:
            print(f"{name}: (absent — headless core OK)")


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
    if group == "web":                             # web front end (optional)
        try:
            from .web import server as websrv
        except ImportError:
            sys.exit("The web front end (znt.web) is not available in this distribution.")
        return websrv.cli(rest)
    if group in ("play", "testbench", "studio"):    # interactive front end (optional)
        try:
            from . import gui
        except ImportError:
            sys.exit("The interactive front end (znt.gui) is not available in this distribution.")
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
    """Entry point of the `znt` command (console_scripts)."""
    main(sys.argv[1:])


if __name__ == "__main__":
    main(sys.argv[1:])
