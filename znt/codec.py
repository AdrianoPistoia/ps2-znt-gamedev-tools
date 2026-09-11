#!/usr/bin/env python3
"""Zero no Tsukaima codec (SLPS-25709).

Ported from the routine at 0x0011c264-0x0011c5e8 in the ELF. It is not an LZ
over the output: match opcodes reference a move-to-front list of the 6 most
recent token positions of the *input stream*, and replay part of their payload.

  T >> 5 == 7  (0xE0-0xFF)  run of (T & 0x1F) + 1 literals
  T >> 5 == 6  (0xC0-0xDF)  RLE: next byte, (T & 0x1F) + 2 times
  T >> 5 <= 5  (0x00-0xBF)  replay of the token at recent[T >> 5]

Both producing cases push their position to the front of the list; a replay
moves the entry it used to the front.

After the LZ pass comes a de-interleave (0x0011c560): the buffer holds `cnt`
contiguous planes of n = usize // cnt bytes and they get transposed. With
cnt == 1 it is the identity.

`compress_store` is the minimal reverse direction: it encodes any buffer as
runs of literals, without compressing. The game's decoder accepts it just the
same (only the 0xE0-0xFF opcode is used), so it serves to reinsert modified
entries without having to reimplement the original compressor.
"""
import struct


# 0x0011c1e0 initializes the 6 slots pointing at six 8-byte buffers
# ($gp-0x7a30 .. $gp-0x7a08). They hold a zero RLE token, so a replay against
# a not-yet-used slot emits zeros. Modeled by prefixing those buffers to the
# stream and seeding the list with their positions.
PRIMER = b"\xc0\x00" + b"\x00" * 6      # one 8-byte buffer
NSLOT = 6


def lz(src, usize):
    src = PRIMER * NSLOT + src
    out = bytearray()
    recent = [k * len(PRIMER) for k in range(NSLOT)]
    i = NSLOT * len(PRIMER)
    while i < len(src) and len(out) < usize:
        T = src[i]
        cls = T >> 5
        if cls == 7:                                   # literals
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
            if U >> 5 == 6:                            # the referenced token was RLE
                out += bytes([src[p+1]]) * ((T & 0x1F) + 2)
            elif U >> 5 == 7:                          # the referenced token was literals
                off = (T & 0x1F) >> 2
                cnt = ((T & 0x1F) & 3) + 1
                out += src[p+1+off:p+1+off+cnt]
            # if the referenced token produces nothing (it is another replay), the ASM
            # emits nothing and advances anyway: bnel at 0x0011c500 -> 0x0011c34c
            i += 1
    return bytes(out[:usize]), i, None


def deinterleave(buf, cnt):
    """0x0011c560: transpose cnt planes of n = len // cnt bytes."""
    if cnt <= 1:
        return buf
    n = len(buf) // cnt
    out = bytearray()
    for i in range(n):
        out += bytes(buf[i + j*n] for j in range(cnt))
    out += buf[n*cnt:]
    return bytes(out)


def decompress(entry):
    """entry = one raw entry from the .BIN, with its 8-byte header."""
    usize, cnt = struct.unpack('<II', entry[:8])
    raw, used, err = lz(entry[8:], usize)
    if err:
        return None, err
    if len(raw) != usize:
        return None, f"length {len(raw)} != usize {usize}"
    return deinterleave(raw, cnt), None


def compress_store(data):
    """Encodes `data` as a valid entry using only runs of literals.

    It does not compress (output is >= the original), but the game's decoder
    reads it fine. This is the minimal route to reinsert a modified entry; see README.
    """
    body = bytearray()
    for i in range(0, len(data), 32):
        chunk = data[i:i+32]
        body.append(0xE0 | (len(chunk) - 1))          # 0xE0-0xFF: literal count
        body += chunk
    return struct.pack('<II', len(data), 1) + bytes(body)   # cnt=1: no interleave


def demo():
    # literals: 0xE0 | (n-1)
    assert lz(bytes([0xE3]) + b"hola", 4)[0] == b"hola"
    # RLE: 0xC0 | (n-2)
    assert lz(bytes([0xC1, 0x41]), 3)[0] == b"AAA"
    # replay of an RLE: recent[0] points at the token at 0
    assert lz(bytes([0xC1, 0x41, 0x00]), 5)[0] == b"AAA" + b"AA"
    # replay of literals: off=(n>>2), cnt=(n&3)+1
    assert lz(bytes([0xE3]) + b"abcd" + bytes([0x05]), 6)[0] == b"abcd" + b"bc"
    # de-interleave: 2 planes of 3
    assert deinterleave(b"ADBECF"[:6], 1) == b"ADBECF"
    assert deinterleave(b"ABCDEF", 2) == b"ADBECF"
    # round-trip of the 'store' compressor for several lengths, including edges
    for n in (0, 1, 31, 32, 33, 64, 1000):
        data = bytes((i * 37 + 11) & 0xFF for i in range(n))
        got, err = decompress(compress_store(data))
        assert err is None and got == data, (n, err)
    print("demo OK")


if __name__ == "__main__":
    demo()
