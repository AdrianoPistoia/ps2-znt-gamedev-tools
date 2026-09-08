"""docs/authoring.md tiene que nombrar cada op que el parser acepta y cada parámetro
que el runtime entiende: si se agrega algo al formato y no al doc, esto falla."""
import os, re
from znt import vn, engine, vnstudio
doc = open(os.path.join(os.path.dirname(__file__), "..", "..", "docs", "authoring.md"), encoding="utf-8").read()
code = "\n".join(re.findall(r"```(.*?)```", doc, re.S))            # sólo los bloques de ejemplo
for op in vn.STEP_OPS:                                              # bg show hide say animate bgm se choice goto end
    assert re.search(rf"^\s*{op}\b", code, re.M) or (op == "say" and ": " in code), f"falta la op {op}"
for kw in ("sprite", "character", "title:", "group", "endgroup", "fade=", "bgm stop", "-> "):
    assert kw in code, f"falta {kw}"
for k in ("x=", "y=", "z=", "zoom=", "opacity=", "tint="):          # parámetros de show
    assert k in code, f"falta el parámetro {k} de show"
for c in engine.CURVES:
    assert c in doc, f"falta la curva {c}"
for a in vnstudio.ACTIONS:
    assert a in doc, f"falta la acción {a}"
for p in vn.POS_NAMES:
    assert p in code, f"falta la posición {p}"
# el ejemplo del doc parsea
example = re.search(r"## Ejemplo mínimo\s*```(.*?)```", doc, re.S)
assert example and vn.parse(example.group(1))["scenes"], "el ejemplo mínimo no parsea"
print("AUTHORING DOC GREEN")
