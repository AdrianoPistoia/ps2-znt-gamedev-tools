#!/usr/bin/env python3
"""Contenedor .HD/.BIN de Zero no Tsukaima (SLPS-25709).

Formato: X.HD es un uint32[] little-endian de tamanos. X.BIN es la
concatenacion de las entradas, cada una rellenada a 2048 bytes.
Verificado byte-exacto en los cinco pares del disco.

`Container` envuelve un par .HD/.BIN y da acceso perezoso a cada entrada, en
crudo (comprimida) o descomprimida, mas repack: las entradas intactas se
reescriben byte-a-byte y solo las modificadas se recodifican con el compresor
'store' de `codec`.
"""
import os, struct, glob

from . import codec

SECTOR = 2048


def sizes(hd):
    d = open(hd, "rb").read()
    assert len(d) % 4 == 0, f"{hd}: tamano no multiplo de 4"
    return list(struct.unpack(f"<{len(d)//4}I", d))


def read_entries(hd, bn):
    """Lee el par a una lista de entradas crudas (comprimidas), sin padding."""
    sz = sizes(hd)
    out = []
    with open(bn, "rb") as f:
        off = 0
        for s in sz:
            f.seek(off)
            out.append(f.read(s))
            off += -(-s // SECTOR) * SECTOR
    assert off == os.path.getsize(bn), f"sobran/faltan bytes: {off} vs {os.path.getsize(bn)}"
    return out


def write_entries(entries, hd, bn):
    """Reescribe el par desde una lista de entradas crudas."""
    with open(bn, "wb") as f:
        for d in entries:
            f.write(d + b"\0" * (-len(d) % SECTOR))
    open(hd, "wb").write(struct.pack(f"<{len(entries)}I", *(len(d) for d in entries)))


def unpack(hd, bn, out):
    os.makedirs(out, exist_ok=True)
    entries = read_entries(hd, bn)
    for i, e in enumerate(entries):
        open(f"{out}/{i:04d}.bin", "wb").write(e)
    print(f"{len(entries)} entradas -> {out}/")


def pack(src, hd, bn):
    files = sorted(glob.glob(f"{src}/*.bin"))
    assert files, f"{src}: sin entradas"
    write_entries([open(p, "rb").read() for p in files], hd, bn)
    print(f"{len(files)} entradas -> {hd} + {bn} ({os.path.getsize(bn)} bytes)")


def info(hd, bn):
    sz = sizes(hd)
    padded = sum(-(-s // SECTOR) * SECTOR for s in sz)
    real = os.path.getsize(bn)
    print(f"entradas   {len(sz)}")
    print(f"tamanos    min={min(sz)} max={max(sz)} suma={sum(sz)}")
    print(f"con padding {padded} | .BIN real {real} | {'OK' if padded == real else 'MISMATCH'}")


def kind(data):
    """Clasifica una entrada ya descomprimida por su contenido."""
    if not data:
        return "empty"
    if data[:4] == b"TIM2":
        return "tim2"
    if data[:2] == b"BM":
        return "bmp"
    try:
        data.decode("cp932")
        return "text"        # fuente Squirrel o tabla de strings
    except UnicodeDecodeError:
        return "binary"


class Container:
    """Un par .HD/.BIN. `c[i]` da la entrada i descomprimida (bytes)."""

    def __init__(self, hd, bn):
        self.hd, self.bn = hd, bn
        self._raw = read_entries(hd, bn)
        self._staged = {}       # i -> bytes descomprimidos pendientes de repack

    def __len__(self):
        return len(self._raw)

    def raw(self, i):
        """Entrada cruda (comprimida) tal como esta en el .BIN."""
        return self._raw[i]

    def data(self, i):
        """Entrada descomprimida. Lanza si el codec falla."""
        if i in self._staged:
            return self._staged[i]
        if len(self._raw[i]) < 8:
            return b""
        d, err = codec.decompress(self._raw[i])
        if err:
            raise ValueError(f"#{i}: {err}")
        return d

    def kind(self, i):
        return kind(self.data(i))

    def __getitem__(self, i):
        return self.data(int(i))

    def set(self, i, data):
        """Reemplaza el contenido descomprimido de la entrada i (para repack)."""
        self._staged[int(i)] = bytes(data)

    def repack(self, hd=None, bn=None):
        """Reescribe el par. Entradas intactas byte-a-byte; las modificadas via
        compress_store. Si no se dan rutas, sobreescribe el par original."""
        entries = list(self._raw)
        for i, data in self._staged.items():
            entries[i] = codec.compress_store(data)
        write_entries(entries, hd or self.hd, bn or self.bn)
        self._raw = entries
        self._staged.clear()


def demo():
    """Self-check: read/write y repack (con set) son consistentes."""
    import tempfile, shutil
    d = tempfile.mkdtemp()
    try:
        blobs = [codec.compress_store(b"hola"), codec.compress_store(b""),
                 codec.compress_store(b"x" * 5000), codec.compress_store(b"y" * 2048)]
        hd, bn = f"{d}/a.HD", f"{d}/a.BIN"
        write_entries(blobs, hd, bn)
        assert read_entries(hd, bn) == blobs
        assert os.path.getsize(bn) % SECTOR == 0
        c = Container(hd, bn)
        assert c.data(0) == b"hola" and c.data(2) == b"x" * 5000
        c.set(0, b"chau mundo")
        c.repack()
        c2 = Container(hd, bn)
        assert c2.data(0) == b"chau mundo"      # modificada
        assert c2.data(2) == b"x" * 5000        # intacta
        assert c2.raw(2) == blobs[2]            # intacta byte-a-byte
        print("demo OK")
    finally:
        shutil.rmtree(d)


if __name__ == "__main__":
    import sys
    cmd, *a = sys.argv[1:] or ["demo"]
    {"unpack": unpack, "pack": pack, "info": info, "demo": demo}[cmd](*a)
