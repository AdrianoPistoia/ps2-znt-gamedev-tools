#!/usr/bin/env python3
"""Codec de Zero no Tsukaima (SLPS-25709).

Portado de la rutina en 0x0011c264-0x0011c5e8 del ELF. No es un LZ sobre la
salida: los opcodes de match referencian una lista move-to-front de las 6
posiciones de token mas recientes del *stream de entrada*, y repiten parte de
su payload.

  T >> 5 == 7  (0xE0-0xFF)  corrida de (T & 0x1F) + 1 literales
  T >> 5 == 6  (0xC0-0xDF)  RLE: byte siguiente, (T & 0x1F) + 2 veces
  T >> 5 <= 5  (0x00-0xBF)  replay del token en recent[T >> 5]

Ambos casos productores empujan su posicion al frente de la lista; el replay
mueve al frente la entrada que uso.

Tras la pasada LZ viene un de-interleave (0x0011c560): el buffer guarda `cnt`
planos contiguos de n = usize // cnt bytes y se transponen. Con cnt == 1 es
identidad.

`compress_store` es la direccion inversa minima: codifica cualquier buffer como
corridas de literales, sin comprimir. El decoder del juego lo acepta igual (solo
usa el opcode 0xE0-0xFF), asi sirve para reinsertar entradas modificadas sin
tener que reimplementar el compresor original.
"""
import struct


# 0x0011c1e0 inicializa los 6 slots apuntando a seis buffers de 8 bytes
# ($gp-0x7a30 .. $gp-0x7a08). Contienen un token RLE de cero, de modo que un
# replay contra un slot todavia no usado emite ceros. Se modela prefijando esos
# buffers al stream y arrancando la lista con sus posiciones.
PRIMER = b"\xc0\x00" + b"\x00" * 6      # un buffer de 8 bytes
NSLOT = 6


def lz(src, usize):
    src = PRIMER * NSLOT + src
    out = bytearray()
    recent = [k * len(PRIMER) for k in range(NSLOT)]
    i = NSLOT * len(PRIMER)
    while i < len(src) and len(out) < usize:
        T = src[i]
        cls = T >> 5
        if cls == 7:                                   # literales
            n = (T & 0x1F) + 1
            recent = [i] + recent[:5]
            out += src[i+1:i+1+n]
            i += 1 + n
        elif cls == 6:                                 # RLE
            n = (T & 0x1F) + 2
            recent = [i] + recent[:5]
            out += bytes([src[i+1]]) * n
            i += 2
        else:                                          # replay
            p = recent[cls]
            recent = [p] + recent[:cls] + recent[cls+1:]
            U = src[p]
            if U >> 5 == 6:                            # el referido era RLE
                out += bytes([src[p+1]]) * ((T & 0x1F) + 2)
            elif U >> 5 == 7:                          # el referido eran literales
                off = (T & 0x1F) >> 2
                cnt = ((T & 0x1F) & 3) + 1
                out += src[p+1+off:p+1+off+cnt]
            # si el token referido no produce (es otro replay), el ASM no emite
            # nada y avanza igual: bnel en 0x0011c500 -> 0x0011c34c
            i += 1
    return bytes(out[:usize]), i, None


def deinterleave(buf, cnt):
    """0x0011c560: transponer cnt planos de n = len // cnt bytes."""
    if cnt <= 1:
        return buf
    n = len(buf) // cnt
    out = bytearray()
    for i in range(n):
        out += bytes(buf[i + j*n] for j in range(cnt))
    out += buf[n*cnt:]
    return bytes(out)


def decompress(entry):
    """entry = una entrada cruda del .BIN, con su header de 8 bytes."""
    usize, cnt = struct.unpack('<II', entry[:8])
    raw, used, err = lz(entry[8:], usize)
    if err:
        return None, err
    if len(raw) != usize:
        return None, f"largo {len(raw)} != usize {usize}"
    return deinterleave(raw, cnt), None


def compress_store(data):
    """Codifica `data` como una entrada valida usando solo corridas de literales.

    No comprime (sale >= al original), pero el decoder del juego la lee bien.
    Es la ruta minima para reinsertar una entrada modificada; ver README.
    """
    body = bytearray()
    for i in range(0, len(data), 32):
        chunk = data[i:i+32]
        body.append(0xE0 | (len(chunk) - 1))          # 0xE0-0xFF: len literales
        body += chunk
    return struct.pack('<II', len(data), 1) + bytes(body)   # cnt=1: sin interleave


def demo():
    # literales: 0xE0 | (n-1)
    assert lz(bytes([0xE3]) + b"hola", 4)[0] == b"hola"
    # RLE: 0xC0 | (n-2)
    assert lz(bytes([0xC1, 0x41]), 3)[0] == b"AAA"
    # replay de un RLE: recent[0] apunta al token en 0
    assert lz(bytes([0xC1, 0x41, 0x00]), 5)[0] == b"AAA" + b"AA"
    # replay de literales: off=(n>>2), cnt=(n&3)+1
    assert lz(bytes([0xE3]) + b"abcd" + bytes([0x05]), 6)[0] == b"abcd" + b"bc"
    # de-interleave: 2 planos de 3
    assert deinterleave(b"ADBECF"[:6], 1) == b"ADBECF"
    assert deinterleave(b"ABCDEF", 2) == b"ADBECF"
    # round-trip del compresor 'store' para varios largos, incluyendo bordes
    for n in (0, 1, 31, 32, 33, 64, 1000):
        data = bytes((i * 37 + 11) & 0xFF for i in range(n))
        got, err = decompress(compress_store(data))
        assert err is None and got == data, (n, err)
    print("demo OK")


if __name__ == "__main__":
    demo()
