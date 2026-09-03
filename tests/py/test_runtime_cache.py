import time
from znt import vn, vnstudio

m = vn._link_choices(vn.parse(
    'title: t\ncharacter a "Ana" color=#e79ab0\ncharacter b "Leo" color=#5a86d8\n'
    'scene s\n  bg grad:#101828,#304060\n  show a left\n  show b right\n  a: Hola.\n  end\n'))
rt = vnstudio.VNRuntime(m); rt.enter("s")

f1 = rt.frame(); n1 = rt._base_builds          # 1ª composición: arma el fondo cacheado
f2 = rt.frame(); n2 = rt._base_builds
assert bytes(f1.buf) == bytes(f2.buf), "el frame debe ser idéntico"
assert n2 == n1, f"no debe recomponer el fondo estático ({n1} -> {n2})"

rt.stage["a"].x += 5                            # cambia una capa estática -> invalida
rt.frame()
assert rt._base_builds == n1 + 1, "debe reconstruir tras mover una capa estática"

# con una capa animada el cache se reusa entre ticks
rt.stage["a"].target("x", 200, frm=rt.stage["a"].x, dur=400)
rt.frame()                     # al empezar la animación cambia QUÉ se cachea: 1 rebuild legítimo
n3 = rt._base_builds
for _ in range(5):
    rt.tick(30); rt.frame()
assert rt._base_builds == n3, "animando NO debe recomponer el fondo en cada frame"

t = time.perf_counter()
for _ in range(10): rt.frame()
ms = (time.perf_counter() - t) / 10 * 1000
print(f"CACHE GREEN  ({ms:.1f} ms/frame animando)")
