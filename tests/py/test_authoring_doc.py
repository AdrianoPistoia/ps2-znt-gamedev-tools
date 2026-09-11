"""docs/authoring.md has to name every op the parser accepts and every parameter
the runtime understands: if something is added to the format and not to the doc, this fails."""
import os, re
from znt import vn, engine, vnstudio
doc = open(os.path.join(os.path.dirname(__file__), "..", "..", "docs", "authoring.md"), encoding="utf-8").read()
code = "\n".join(re.findall(r"```(.*?)```", doc, re.S))            # only the example blocks
for op in vn.STEP_OPS:                                              # bg show hide say animate bgm se choice goto end
    assert re.search(rf"^\s*{op}\b", code, re.M) or (op == "say" and ": " in code), f"missing op {op}"
for kw in ("sprite", "character", "title:", "group", "endgroup", "fade=", "bgm stop", "-> "):
    assert kw in code, f"missing {kw}"
for k in ("x=", "y=", "z=", "zoom=", "opacity=", "tint="):          # show parameters
    assert k in code, f"missing show parameter {k}"
for c in engine.CURVES:
    assert c in doc, f"missing curve {c}"
for a in vnstudio.ACTIONS:
    assert a in doc, f"missing action {a}"
for p in vn.POS_NAMES:
    assert p in code, f"missing position {p}"
# the doc's example parses
example = re.search(r"## Minimal example\s*```(.*?)```", doc, re.S)
assert example and vn.parse(example.group(1))["scenes"], "the minimal example does not parse"
print("AUTHORING DOC GREEN")
