"""Cuantización a 256 colores para las texturas del player de PS2.

Una imagen RGBA de 640x448 pesa 1.1 MB: con 4 MB de VRAM entran pocas, y hay que
leerlas del DVD. En 8bpp + CLUT pesa 287 KB (4x menos de VRAM y 4x menos de disco).

`quantize` devuelve (clut, indices): 256 entradas RGBA (1024 bytes) y un byte por
píxel. El CLUT sale **en el orden que espera el GS** (CSM1, ver `swizzle_clut`), así
el ELF lo sube tal cual sin reordenar nada.

Método: median cut. Si la imagen tiene 256 colores distintos o menos —el caso normal
del arte plano de una VN— se usan tal cual y no se pierde nada. Si tiene más, se
agrupa a 5 bits por canal (incluido el alfa) y se parte el espacio en 256 cajas,
cada una representada por el promedio real de sus píxeles.

Sólo stdlib. Self-check: `python3 -m znt.quant`.
"""

PAL = 256


def swizzle_clut(clut):
    """Intercambia las entradas 8-15 con las 16-23 de cada grupo de 32.

    El GS lee el CLUT de una textura de 8 bits en ese orden (CSM1); si se sube
    derecho, los colores salen cambiados por bloques. Es su propio inverso."""
    out = bytearray(clut)
    for base in range(0, PAL, 32):
        for k in range(8):
            a = (base + 8 + k) * 4
            b = (base + 16 + k) * 4
            out[a:a+4], out[b:b+4] = clut[b:b+4], clut[a:a+4]
    return bytes(out)


def _counts(rgba, bits):
    """{clave -> [suma_r, suma_g, suma_b, suma_a, n]} agrupando a `bits` por canal."""
    sh = 8 - bits
    acc = {}
    mv = memoryview(rgba)
    for i in range(0, len(rgba), 4):
        r, g, b, a = mv[i], mv[i+1], mv[i+2], mv[i+3]
        k = (r >> sh, g >> sh, b >> sh, a >> sh) if bits < 8 else (r, g, b, a)
        e = acc.get(k)
        if e is None: acc[k] = [r, g, b, a, 1]
        else:
            e[0] += r; e[1] += g; e[2] += b; e[3] += a; e[4] += 1
    return acc


def _split(items):
    """Median cut: parte `items` en <=256 cajas. Devuelve la lista de cajas."""
    def stats(box):
        lo = [255] * 4; hi = [0] * 4; n = 0
        for it in box:
            for c in range(4):
                v = it[c] // it[4]
                if v < lo[c]: lo[c] = v
                if v > hi[c]: hi[c] = v
            n += it[4]
        rng = [hi[c] - lo[c] for c in range(4)]
        ch = max(range(4), key=lambda c: rng[c])
        return rng[ch] * n, ch                      # cajas grandes y pobladas primero

    boxes = [(items, *stats(items))]
    while len(boxes) < PAL:
        i = max(range(len(boxes)), key=lambda k: boxes[k][1])
        box, score, ch = boxes[i]
        if score == 0 or len(box) < 2:
            break                                   # no queda nada que valga la pena partir
        box = sorted(box, key=lambda it: it[ch] // it[4])
        half = sum(it[4] for it in box) // 2
        acc = j = 0
        while j < len(box) - 1 and acc + box[j][4] <= half:
            acc += box[j][4]; j += 1
        a, b = box[:j] or box[:1], box[j:] or box[-1:]
        boxes[i] = (a, *stats(a)); boxes.append((b, *stats(b)))
    return [b[0] for b in boxes]


def is_lossless(rgba):
    """¿La imagen entra en 256 colores exactos? (arte plano de VN: casi siempre sí)"""
    return len(_counts(rgba, 8)) <= PAL


def quantize(w, h, rgba):
    """RGBA crudo -> (clut de 1024 bytes ya en orden del GS, indices de w*h bytes)."""
    exact = _counts(rgba, 8)
    if len(exact) <= PAL:                           # arte plano: sin pérdida
        keys = list(exact)
        pal = [k for k in keys]
        index = {k: i for i, k in enumerate(keys)}
        bits = 8
    else:
        acc = _counts(rgba, 5)
        items = [(v[0], v[1], v[2], v[3], v[4], k) for k, v in acc.items()]
        boxes = _split(items)
        pal, index = [], {}
        for i, box in enumerate(boxes):
            n = sum(it[4] for it in box) or 1
            pal.append(tuple(sum(it[c] for it in box) // n for c in range(4)))
            for it in box:
                index[it[5]] = i
        bits = 5

    clut = bytearray(1024)
    for i, c in enumerate(pal):
        clut[i*4:i*4+4] = bytes(c)

    sh = 8 - bits
    mv = memoryview(rgba)
    idx = bytearray(w * h)
    for p in range(w * h):
        i = p * 4
        k = (mv[i] >> sh, mv[i+1] >> sh, mv[i+2] >> sh, mv[i+3] >> sh) if bits < 8 else \
            (mv[i], mv[i+1], mv[i+2], mv[i+3])
        idx[p] = index[k]
    return swizzle_clut(bytes(clut)), bytes(idx)


def unquantize(w, h, clut, idx):
    """Deshace `quantize` (para verificar). Devuelve RGBA crudo."""
    pal = swizzle_clut(clut)                        # el intercambio es su propio inverso
    return b"".join(pal[i*4:i*4+4] for i in idx)


def demo():
    px = b"".join(bytes((x * 4 % 256, y * 4 % 256, 0, 255)) for y in range(32) for x in range(32))
    clut, idx = quantize(32, 32, px)
    assert len(clut) == 1024 and len(idx) == 32 * 32
    out = unquantize(32, 32, clut, idx)
    e = sum(abs(a - b) for a, b in zip(px, out)) / len(px)
    assert e < 6, e
    flat = b"".join(bytes((1, 2, 3, 255)) for _ in range(64))
    c2, i2 = quantize(8, 8, flat)
    assert unquantize(8, 8, c2, i2) == flat
    assert swizzle_clut(swizzle_clut(clut)) == clut
    print("demo OK")


if __name__ == "__main__":
    demo()
