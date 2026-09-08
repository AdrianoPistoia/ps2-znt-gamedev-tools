"""ADPCM de la SPU2 (PS1/PS2 "VAG") desde WAV PCM, con la cabecera de 16 bytes que
espera `audsrv_load_adpcm`: u32 "APCM" | u32 channels<<8 | loop<<16 | u32 pitch | u32 0.
Los `se` del blob van en este formato (un canal de la SPU2 cada uno, encima del BGM).

Bloque: 16 bytes = u8 (shift | filter<<4), u8 flags, 14 bytes = 28 nibbles (bajo primero).
Decodificado: s = (nibble<<12 >> shift) + (s1*c0 + s2*c1 + 32) >> 6, con 5 filtros fijos.
Sólo stdlib. Self-check: `python3 -m znt.adpcm`."""
import struct

FILTERS = ((0, 0), (60, 0), (115, -52), (98, -55), (122, -60))
MAGIC = b"APCM"


def _clamp(v):
    return -32768 if v < -32768 else 32767 if v > 32767 else v


def _encode_block(xs, s1, s2, f, sh):
    """Codifica 28 muestras con filtro f y shift sh. Devuelve (nibbles, s1, s2, error²)."""
    c0, c1 = FILTERS[f]; step = 1 << (12 - sh); nibs = []; err = 0
    for x in xs:
        pred = (s1 * c0 + s2 * c1 + 32) >> 6
        n = int(round((x - pred) / step))
        n = -8 if n < -8 else 7 if n > 7 else n
        dec = _clamp(pred + n * step)
        err += (dec - x) ** 2
        s2, s1 = s1, dec
        nibs.append(n & 0xF)
    return nibs, s1, s2, err


def encode(samples):
    """Muestras mono de 16 bits -> bloques ADPCM (sin cabecera). El último lleva flag END."""
    out = bytearray(); s1 = s2 = 0
    blocks = [samples[i:i + 28] for i in range(0, len(samples), 28)] or [[]]
    for bi, blk in enumerate(blocks):
        xs = list(blk) + [0] * (28 - len(blk))
        best = None
        for f, (c0, c1) in enumerate(FILTERS):
            # shift estimado por el residuo máximo con la historia real, y el vecino por si acaso
            p1, p2 = s1, s2; mx = 1
            for x in xs:
                pred = (p1 * c0 + p2 * c1 + 32) >> 6; r = abs(x - pred); mx = max(mx, r); p2, p1 = p1, x
            sh = 12
            while sh > 0 and mx > 7 * (1 << (12 - sh)): sh -= 1
            for s in (sh, sh - 1) if sh > 0 else (sh,):
                nibs, n1, n2, err = _encode_block(xs, s1, s2, f, s)
                if best is None or err < best[0]: best = (err, f, s, nibs, n1, n2)
        _, f, sh, nibs, s1, s2 = best
        flags = 1 if bi == len(blocks) - 1 else 0             # END en el último bloque (one-shot)
        out += bytes([sh | (f << 4), flags])
        out += bytes(nibs[i] | (nibs[i + 1] << 4) for i in range(0, 28, 2))
    return bytes(out)


def decode(body):
    """Bloques ADPCM -> muestras (como la SPU2). Para verificación."""
    out = []; s1 = s2 = 0
    for i in range(0, len(body) - 15, 16):
        sh = body[i] & 0xF; c0, c1 = FILTERS[(body[i] >> 4) & 7]
        for j in range(28):
            n = (body[i + 2 + j // 2] >> (4 * (j & 1))) & 0xF
            n = n - 16 if n > 7 else n
            s = _clamp(((n << 12) >> sh) + ((s1 * c0 + s2 * c1 + 32) >> 6))
            out.append(s); s2, s1 = s1, s
    return out


def wav_pcm(data):
    """WAV PCM (8/16 bits, 1..N canales) -> (rate, muestras mono de 16 bits)."""
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("no es WAV")
    i = 12; fmt = None; pcm = b""
    while i + 8 <= len(data):
        tag, sz = data[i:i + 4], struct.unpack_from("<I", data, i + 4)[0]
        if tag == b"fmt ": fmt = struct.unpack_from("<HHIIHH", data, i + 8)
        elif tag == b"data": pcm = data[i + 8:i + 8 + sz]
        i += 8 + sz + (sz & 1)
    if not fmt or fmt[0] != 1: raise ValueError("WAV no PCM")
    ch, rate, bits = fmt[1], fmt[2], fmt[5]
    if bits == 16: s = struct.unpack(f"<{len(pcm) // 2}h", pcm[:len(pcm) // 2 * 2])
    elif bits == 8: s = [(b - 128) << 8 for b in pcm]
    else: raise ValueError(f"WAV de {bits} bits")
    if ch > 1: s = [sum(s[k:k + ch]) // ch for k in range(0, len(s) - ch + 1, ch)]
    return rate, list(s)


def from_wav(data, loop=False):
    """WAV PCM -> .adp de audsrv (cabecera + bloques)."""
    rate, s = wav_pcm(data)
    pitch = min(rate * 4096 // 48000, 0x3FFF)
    return MAGIC + struct.pack("<III", (1 << 8) | (int(loop) << 16), pitch, 0) + encode(s)


def demo():
    import math
    sine = [int(12000 * math.sin(2 * math.pi * 440 * i / 22050)) for i in range(1000)]
    body = encode(sine); out = decode(body)[:1000]
    err = sum((a - b) ** 2 for a, b in zip(sine, out)); sig = sum(a * a for a in sine)
    snr = 10 * math.log10(sig / max(err, 1))
    assert snr > 30, snr
    assert len(body) == 16 * 36 and body[-15] == 1
    print("demo OK")


if __name__ == "__main__":
    demo()
