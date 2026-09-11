"""znt — access SDK for Zero no Tsukaima: KtHC (PS2, SLPS-25709).

Layer 2 of the roadmap (2 -> 1 -> 3): opens the game and gives typed access to
its systems (Squirrel scenes, TIM2 textures, font) plus repack. It does not run
the game logic; that is layer 1.

    import znt
    disc  = znt.open("iso")            # dir with the disc's .HD/.BIN pairs
    src   = disc.scenes[1]             # Squirrel source (str)
    tex   = disc.textures[12]          # Texture -> .png("bg.png")
    font  = disc.font                  # atlas + character->glyph mapping

    disc.scenes.set(1, new_src.encode("cp932"))
    disc.scenes.repack()               # rewrites SCENE_ID.HD/.BIN
"""
import os

from .container import Container, kind
from .codec import decompress, compress_store
from .tim2 import Texture
from .font import Font

__all__ = ["open", "Disc", "Container", "Texture", "Font",
           "decompress", "compress_store", "kind"]

# Names of the pairs on the disc (see README). Everything else is opened by name.
SCENES, TEXTURES, NORMAL = "SCENE_ID", "SCENEDAT", "NORMAL"
FONT_ATLAS, FONT_MAP = 6, 5      # NORMAL entries: #0006 atlas, #0005 mapping


class Disc:
    """A directory with the .HD/.BIN pairs extracted from the ISO."""

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
        """SCENE_ID: ~1920 scenes, each `c[i]` is Squirrel source (str)."""
        return _Scenes(self.container(SCENES))

    @property
    def textures(self):
        """SCENEDAT: ~1104 textures, each `c[i]` is a Texture."""
        return _Textures(self.container(TEXTURES))

    @property
    def normal(self):
        """NORMAL: a mix of textures, the font and string tables."""
        return self.container(NORMAL)

    @property
    def font(self):
        n = self.normal
        return Font(n.data(FONT_ATLAS), n.data(FONT_MAP))


class _View:
    """Wraps a Container to type `c[i]` according to the system."""
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
    """Opens a directory with the .HD/.BIN pairs extracted from the disc."""
    return Disc(path)
