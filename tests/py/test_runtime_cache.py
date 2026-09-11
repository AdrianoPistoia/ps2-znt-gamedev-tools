import time
from znt import vn, vnstudio

m = vn._link_choices(vn.parse(
    'title: t\ncharacter a "Ana" color=#e79ab0\ncharacter b "Leo" color=#5a86d8\n'
    'scene s\n  bg grad:#101828,#304060\n  show a left\n  show b right\n  a: Hola.\n  end\n'))
rt = vnstudio.VNRuntime(m); rt.enter("s")

f1 = rt.frame(); n1 = rt._base_builds          # 1st composition: builds the cached background
f2 = rt.frame(); n2 = rt._base_builds
assert bytes(f1.buf) == bytes(f2.buf), "the frame must be identical"
assert n2 == n1, f"must not recompose the static background ({n1} -> {n2})"

rt.stage["a"].x += 5                            # changing a static layer -> invalidates
rt.frame()
assert rt._base_builds == n1 + 1, "must rebuild after moving a static layer"

# with an animated layer the cache is reused between ticks
rt.stage["a"].target("x", 200, frm=rt.stage["a"].x, dur=400)
rt.frame()                     # starting the animation changes WHAT is cached: 1 legitimate rebuild
n3 = rt._base_builds
for _ in range(5):
    rt.tick(30); rt.frame()
assert rt._base_builds == n3, "animating must NOT recompose the background every frame"

t = time.perf_counter()
for _ in range(10): rt.frame()
ms = (time.perf_counter() - t) / 10 * 1000
print(f"CACHE GREEN  ({ms:.1f} ms/frame while animating)")
