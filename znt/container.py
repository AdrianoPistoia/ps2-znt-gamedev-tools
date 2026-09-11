#!/usr/bin/env python3
""".HD/.BIN container of Zero no Tsukaima (SLPS-25709).

Format: X.HD is a little-endian uint32[] of sizes. X.BIN is the concatenation
of the entries, each padded to 2048 bytes. Verified byte-exact on the five
pairs of the disc.

`Container` wraps an .HD/.BIN pair and gives lazy access to each entry, raw
(compressed) or decompressed, plus repack: untouched entries are rewritten
byte-for-byte and only modified ones are re-encoded with the 'store'
compressor from `codec`.
"""
import os, struct, glob

from . import codec

SECTOR = 2048


def sizes(hd):
    d = open(hd, "rb").read()
    assert len(d) % 4 == 0, f"{hd}: size not a multiple of 4"
    return list(struct.unpack(f"<{len(d)//4}I", d))


def read_entries(hd, bn):
    """Reads the pair into a list of raw (compressed) entries, without padding."""
    sz = sizes(hd)
    out = []
    with open(bn, "rb") as f:
        off = 0
        for s in sz:
            f.seek(off)
            out.append(f.read(s))
            off += -(-s // SECTOR) * SECTOR
    assert off == os.path.getsize(bn), f"extra/missing bytes: {off} vs {os.path.getsize(bn)}"
    return out


def write_entries(entries, hd, bn):
    """Rewrites the pair from a list of raw entries."""
    with open(bn, "wb") as f:
        for d in entries:
            f.write(d + b"\0" * (-len(d) % SECTOR))
    open(hd, "wb").write(struct.pack(f"<{len(entries)}I", *(len(d) for d in entries)))


def unpack(hd, bn, out):
    os.makedirs(out, exist_ok=True)
    entries = read_entries(hd, bn)
    for i, e in enumerate(entries):
        open(f"{out}/{i:04d}.bin", "wb").write(e)
    print(f"{len(entries)} entries -> {out}/")


def pack(src, hd, bn):
    files = sorted(glob.glob(f"{src}/*.bin"))
    assert files, f"{src}: no entries"
    write_entries([open(p, "rb").read() for p in files], hd, bn)
    print(f"{len(files)} entries -> {hd} + {bn} ({os.path.getsize(bn)} bytes)")


def info(hd, bn):
    sz = sizes(hd)
    padded = sum(-(-s // SECTOR) * SECTOR for s in sz)
    real = os.path.getsize(bn)
    print(f"entries    {len(sz)}")
    print(f"sizes      min={min(sz)} max={max(sz)} sum={sum(sz)}")
    print(f"padded {padded} | actual .BIN {real} | {'OK' if padded == real else 'MISMATCH'}")


def kind(data):
    """Classifies an already-decompressed entry by its content."""
    if not data:
        return "empty"
    if data[:4] == b"TIM2":
        return "tim2"
    if data[:2] == b"BM":
        return "bmp"
    try:
        data.decode("cp932")
        return "text"        # Squirrel source or string table
    except UnicodeDecodeError:
        return "binary"


class Container:
    """An .HD/.BIN pair. `c[i]` gives entry i decompressed (bytes)."""

    def __init__(self, hd, bn):
        self.hd, self.bn = hd, bn
        self._raw = read_entries(hd, bn)
        self._staged = {}       # i -> decompressed bytes pending repack

    def __len__(self):
        return len(self._raw)

    def raw(self, i):
        """Raw (compressed) entry exactly as it is in the .BIN."""
        return self._raw[i]

    def data(self, i):
        """Decompressed entry. Raises if the codec fails."""
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
        """Replaces the decompressed content of entry i (for repack)."""
        self._staged[int(i)] = bytes(data)

    def repack(self, hd=None, bn=None):
        """Rewrites the pair. Untouched entries byte-for-byte; modified ones via
        compress_store. If no paths are given, overwrites the original pair."""
        entries = list(self._raw)
        for i, data in self._staged.items():
            entries[i] = codec.compress_store(data)
        write_entries(entries, hd or self.hd, bn or self.bn)
        self._raw = entries
        self._staged.clear()


def demo():
    """Self-check: read/write and repack (with set) are consistent."""
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
        assert c2.data(0) == b"chau mundo"      # modified
        assert c2.data(2) == b"x" * 5000        # untouched
        assert c2.raw(2) == blobs[2]            # untouched byte-for-byte
        print("demo OK")
    finally:
        shutil.rmtree(d)


if __name__ == "__main__":
    import sys
    cmd, *a = sys.argv[1:] or ["demo"]
    {"unpack": unpack, "pack": pack, "info": info, "demo": demo}[cmd](*a)
