"""Encoder WAV -> ADPCM de SPU2 con la cabecera de 16 bytes que espera audsrv
(audsrv_load_adpcm): u32 magic, u32 (channels<<8 | loop<<16), u32 pitch, u32 0.
Los efectos (`se`) del blob van así; el BGM sigue en WAV PCM."""
import math, struct
from znt import adpcm, vn, vniso

def wav(samples, rate, ch=1, bits=16):
    if bits == 16: data = b"".join(struct.pack("<h", s) for s in samples)
    else: data = bytes(((s >> 8) + 128) & 0xFF for s in samples)
    fmt = struct.pack("<HHIIHH", 1, ch, rate, rate * ch * bits // 8, ch * bits // 8, bits)
    return b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " + struct.pack("<I", 16) + fmt + b"data" + struct.pack("<I", len(data)) + data

n = 4410; rate = 22050
sine = [int(12000 * math.sin(2 * math.pi * 440 * i / rate)) for i in range(n)]
adp = adpcm.from_wav(wav(sine, rate))
magic, flags, pitch, zero = struct.unpack("<4sIII", adp[:16])
assert magic == b"APCM" and (flags >> 8) & 0xFF == 1 and (flags >> 16) & 0xFF == 0 and zero == 0, (magic, hex(flags))
assert pitch == rate * 4096 // 48000, pitch
body = adp[16:]
assert len(body) % 16 == 0 and len(body) == 16 * math.ceil(n / 28), len(body)
assert body[-15] == 1, "el último bloque lleva flag END (1)"
assert all(body[i + 1] == 0 for i in range(0, len(body) - 16, 16)), "los demás bloques sin flags"
# round-trip: decodificar como la SPU2 y comparar (SNR alto)
out = adpcm.decode(body)[:n]
err = sum((a - b) ** 2 for a, b in zip(sine, out)); sig = sum(a * a for a in sine)
snr = 10 * math.log10(sig / max(err, 1))
assert snr > 30, f"SNR {snr:.1f} dB"
# estéreo 44.1k de 16 bits y mono de 8 bits también entran (se mezclan a mono 16)
st = wav([v for s in sine for v in (s, -s // 2)], 44100, ch=2)
assert struct.unpack("<I", adpcm.from_wav(st)[8:12])[0] == 44100 * 4096 // 48000
assert len(adpcm.from_wav(wav(sine, rate, bits=8))) == len(adp)
# el blob: `se` va como ADPCM (magic APCM), `bgm` queda WAV
import tempfile, os
d = tempfile.mkdtemp(); open(f"{d}/g.wav", "wb").write(wav(sine, rate)); open(f"{d}/t.wav", "wb").write(wav(sine, rate))
m = vn._link_choices(vn.parse('title: T\ncharacter a "A"\nscene s\n  bgm t.wav\n  se g.wav\n  a: h\n  end\n'))
blob = vniso.compile_blob(m, base=d, font=None); r = vniso.read_blob(blob)
auds = {nm: blob[off:off + ln] for nm, ln, off in r["audios"]}
assert auds["t.wav"][:4] == b"RIFF" and auds["g.wav"][:4] == b"APCM", {k: v[:4] for k, v in auds.items()}
print("ADPCM GREEN")
