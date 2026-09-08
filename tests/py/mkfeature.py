"""Arma una VN de prueba con TODO lo que el player PS2 tiene que hacer (fondo imagen +
crossfade, sprite PNG con alfa, tween en x/y, tipeo, bgm WAV y se ADPCM) y la compila a
ps2/ZNTVN.VNP: `python3 tests/py/mkfeature.py <dir>`. checklist.sh la bootea en PCSX2."""
import sys, os, math, struct, zlib, subprocess
d = sys.argv[1]; os.makedirs(d, exist_ok=True)

def png(path, w, h, f):
    ch = lambda t, b: struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b))
    raw = b"".join(b"\0" + b"".join(bytes(f(x, y)) for x in range(w)) for y in range(h))
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                           + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b""))
def wav(path, samples, rate=22050):
    data = b"".join(struct.pack("<h", s) for s in samples)
    open(path, "wb").write(b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " + struct.pack("<I", 16)
                           + struct.pack("<HHIIHH", 1, 1, rate, rate * 2, 2, 16) + b"data" + struct.pack("<I", len(data)) + data)

png(f"{d}/fondo.png", 640, 448, lambda x, y: (x * 255 // 639, 40, y * 255 // 447, 255))
png(f"{d}/ana.png", 192, 320, lambda x, y: (240, 200, 60, 255 if (x - 96) ** 2 + (y - 90) ** 2 < 70 ** 2 or y > 160 else 0))
wav(f"{d}/golpe.wav", [int(9000 * math.sin(2 * math.pi * 660 * i / 22050) * (1 - i / 6000)) for i in range(6000)])
wav(f"{d}/tema.wav", [int(4000 * math.sin(2 * math.pi * 220 * i / 22050)) for i in range(22050)])
open(f"{d}/f.vn", "w").write('''title: Features
character ana "Ana" color=#e79ab0
sprite ana ana.png
scene s
  bg grad:#103060,#000000
  bgm tema.wav
  show ana left
  animate ana move x=-100 y=-120 curve=decel time=3000
  bg fondo.png fade=9000
  se golpe.wav
  ana: Tipeo, crossfade, tween en x e y, BGM y SE. Todo junto.
  end
''')
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "ps2", "ZNTVN.VNP")
subprocess.run([sys.executable, "-m", "znt", "iso", "build", f"{d}/f.vn", out], check=True, stdout=subprocess.DEVNULL)
print("blob de features ->", os.path.normpath(out))
