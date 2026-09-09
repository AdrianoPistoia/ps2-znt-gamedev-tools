"""VN de ramificación para el harness: choice, goto entre escenas, hide y end.
`python3 tests/py/mkchoice.py <dir>` la compila a ps2/ZNTVN.VNP. Con ZNT_AUTOPLAY=1 el
ELF elige la ÚLTIMA opción, así el recorrido pasa por el goto antes de terminar."""
import sys, os, struct, zlib, subprocess
d = sys.argv[1]; os.makedirs(d, exist_ok=True)

def png(path, w, h, f):
    ch = lambda t, b: struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b))
    raw = b"".join(b"\0" + b"".join(bytes(f(x, y)) for x in range(w)) for y in range(h))
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                           + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b""))

png(f"{d}/ana.png", 192, 320, lambda x, y: (240, 200, 60, 255 if (x-96)**2 + (y-90)**2 < 70**2 or y > 160 else 0))
open(f"{d}/c.vn", "w").write('''title: Ramificacion
character ana "Ana" color=#e79ab0
sprite ana ana.png
scene inicio
  bg grad:#103060,#000000
  show ana left
  ana: ¿Y ahora?
  choice
    - Ir a la torre -> torre
    - Quedarse acá -> quedarse
scene quedarse
  * Te quedaste un rato más.
  goto torre
scene torre
  bg #201040
  hide ana
  * Subiste a la torre.
  end
''')
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "ps2", "ZNTVN.VNP")
subprocess.run([sys.executable, "-m", "znt", "iso", "build", f"{d}/c.vn", out], check=True, stdout=subprocess.DEVNULL)
print("blob de ramificación ->", os.path.normpath(out))
