"""Branching VN for the harness: choice, goto between scenes, hide and end.
`python3 tests/py/mkchoice.py <dir>` compiles it to ps2/ZNTVN.VNP. With ZNT_AUTOPLAY=1 the
ELF picks the LAST option, so the run goes through the goto before ending."""
import sys, os, struct, zlib, subprocess
d = sys.argv[1]; os.makedirs(d, exist_ok=True)

def png(path, w, h, f):
    ch = lambda t, b: struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b))
    raw = b"".join(b"\0" + b"".join(bytes(f(x, y)) for x in range(w)) for y in range(h))
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                           + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b""))

png(f"{d}/ana.png", 192, 320, lambda x, y: (240, 200, 60, 255 if (x-96)**2 + (y-90)**2 < 70**2 or y > 160 else 0))
open(f"{d}/c.vn", "w").write('''title: Branching
character ana "Ana" color=#e79ab0
sprite ana ana.png
scene start
  bg grad:#103060,#000000
  show ana left
  ana: What now?
  choice
    - Go to the tower -> tower
    - Stay here -> stay
scene stay
  * You stayed a while longer.
  goto tower
scene tower
  bg #201040
  hide ana
  * You climbed the tower.
  end
''')
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "ps2", "ZNTVN.VNP")
subprocess.run([sys.executable, "-m", "znt", "iso", "build", f"{d}/c.vn", out], check=True, stdout=subprocess.DEVNULL)
print("branching blob ->", os.path.normpath(out))
