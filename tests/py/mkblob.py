"""Generates a test blob k.vnp in the given directory (with a 2x2 PNG sprite, audio and
font) for the C reader: `python3 tests/py/mkblob.py <dir>`. Used by run_all.sh and checklist.sh."""
import sys, struct, zlib
from znt import vn, vniso, psf
d = sys.argv[1]
px = bytes((10, 20, 30, 255)) * 4
raw = b"".join(b"\0" + px[y*8:(y+1)*8] for y in range(2))
chunk = lambda t, b: struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b))
open(d + "/s.png", "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
m = vn._link_choices(vn.parse('title: T\ncharacter a "Ana" color=#e79ab0\nsprite a s.png\nscene one\n  bg grad:#101828,#304060 fade=300\n  show a right x=40 z=5 zoom=150 opacity=80\n  a: Hello.\n  choice\n    - Continue -> two\n    - End -> two\nscene two\n  * bye\n  bgm t.wav\n  animate a move y=-30 time=100\n  end\n'))
open(d + "/t.wav", "wb").write(b"RIFFxxxxWAVE")
open(d + "/k.vnp", "wb").write(vniso.compile_blob(m, base=d, font=psf.find_default()))
