"""znt — SDK de acceso a Zero no Tsukaima: KtHC (PS2, SLPS-25709).

Capa 2 del roadmap (2 -> 1 -> 3): abre el juego y da acceso tipado a sus
sistemas (escenas Squirrel, texturas TIM2, fuente) y repack. No ejecuta la
logica del juego; eso es la capa 1.

    import znt
    disc  = znt.open("iso")            # dir con los pares .HD/.BIN del disco
    src   = disc.scenes[1]             # fuente Squirrel (str)
    tex   = disc.textures[12]          # Texture -> .png("bg.png")
    font  = disc.font                  # atlas + mapeo caracter->glifo

    disc.scenes.set(1, nuevo_src.encode("cp932"))
    disc.scenes.repack()               # reescribe SCENE_ID.HD/.BIN
"""
import os

from .container import Container, kind
from .codec import decompress, compress_store
from .tim2 import Texture
from .font import Font

__all__ = ["open", "Disc", "Container", "Texture", "Font",
           "decompress", "compress_store", "kind"]

# Nombres de los pares en el disco (ver README). El resto se abre por nombre.
SCENES, TEXTURES, NORMAL = "SCENE_ID", "SCENEDAT", "NORMAL"
FONT_ATLAS, FONT_MAP = 6, 5      # entradas de NORMAL: #0006 atlas, #0005 mapeo


class Disc:
    """Un directorio con los pares .HD/.BIN extraidos del ISO."""

    def __init__(self, path):
        self.path = path
        self._cache = {}

    def container(self, name):
        if name not in self._cache:
            hd = os.path.join(self.path, f"{name}.HD")
            bn = os.path.join(self.path, f"{name}.BIN")
            self._cache[name] = Container(hd, bn)
        return self._cache[name]

    @property
    def scenes(self):
        """SCENE_ID: ~1920 escenas, cada `c[i]` es fuente Squirrel (str)."""
        return _Scenes(self.container(SCENES))

    @property
    def textures(self):
        """SCENEDAT: ~1104 texturas, cada `c[i]` es una Texture."""
        return _Textures(self.container(TEXTURES))

    @property
    def normal(self):
        """NORMAL: mezcla de texturas, fuente y tablas de strings."""
        return self.container(NORMAL)

    @property
    def font(self):
        n = self.normal
        return Font(n.data(FONT_ATLAS), n.data(FONT_MAP))


class _View:
    """Envuelve un Container para tipar `c[i]` segun el sistema."""
    def __init__(self, container):
        self.container = container
    def __len__(self):
        return len(self.container)
    def set(self, i, data):
        self.container.set(i, data)
    def repack(self, *a):
        self.container.repack(*a)


class _Scenes(_View):
    def __getitem__(self, i):
        return self.container[i].decode("cp932")


class _Textures(_View):
    def __getitem__(self, i):
        return Texture(self.container[i])


def open(path):
    """Abre un directorio con los pares .HD/.BIN extraidos del disco."""
    return Disc(path)
