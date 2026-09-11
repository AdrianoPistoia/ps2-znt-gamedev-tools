#!/usr/bin/env python3
"""Layer 3 — authoring: a simple VN format (.vn) and a self-contained HTML player.

The author writes scenes as text plus their own PNG assets; `build` compiles them
into a single-file HTML player (scene JSON + a tiny JS engine + assets embedded
as data URIs) that plays in the browser: click to advance, buttons to choose.
It reuses the layer-1 scene model (background + sprites + dialogue box) but runs
in the browser so it can be shared with no deps.

Format (one directive per line):

    title: My Story
    character saito "Saito" color=#6cd
    character louise "Louise" color=#e79

    scene intro
      bg grad:#1a2340,#3a5a8a          # or  bg room.png  or  bg #223
      show saito right
      saito: Hi. I'm Saito.
      louise: Silence, dog!
      * An awkward silence filled the room.
      choice
        - Apologize -> peace
        - Talk back  -> fight

    scene peace
      narrator: You made peace.
      end

  python -m znt vn build story.vn player.html
  python -m znt vn demo
"""
import sys, os, json, base64, html


POS_NAMES = ("left", "center", "right")
POS = {"left": -180, "center": 0, "right": 180}      # sprite x per preset (px from center)


def _sprite_line(chars, rest):
    """`ana ana.png` (base sprite) or `ana happy happy.png` (expression)."""
    parts = rest.split()
    c = chars.setdefault(parts[0], {"name": parts[0], "color": "#ccc"})
    if len(parts) >= 3:
        c.setdefault("expr", {})[parts[1]] = " ".join(parts[2:])
    elif len(parts) == 2:
        c["sprite"] = parts[1]


def groups(steps):
    """Runs of steps sharing a group: [(name, from, to)]."""
    out, cur = [], None
    for i, s in enumerate(steps):
        g = s.get("group")
        if g and cur and cur[0] == g:
            cur[2] = i
        else:
            if cur: out.append(tuple(cur))
            cur = [g, i, i] if g else None
    if cur: out.append(tuple(cur))
    return out


def sprite_file(char, expr=None):
    """Sprite file for that expression (or the base one if missing/unknown)."""
    return (char.get("expr") or {}).get(expr) or char.get("sprite")


def parse(text):
    title = "Visual Novel"
    chars = {"narrator": {"name": "", "color": "#cccccc"}}
    scenes = {}          # id -> list of steps
    order = []
    cur = None; group = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("title:"):
            title = line[6:].strip(); continue
        if line.startswith("character "):
            _, rest = line.split(" ", 1)
            cid, rest = rest.split(" ", 1)
            name, color = rest, "#cccccc"
            if "color=" in rest:
                pre, color = rest.rsplit("color=", 1)
                name = pre.strip(); color = color.strip()
            elif rest.rstrip().rsplit(None, 1)[-1].startswith("#"):   # bare color at the end
                name, color = rest.rstrip().rsplit(None, 1)
            chars[cid] = {"name": name.strip().strip('"'), "color": color}
            continue
        if line.startswith("sprite "):                # character art (top-level)
            _sprite_line(chars, line[7:])
            continue
        if line.startswith("scene "):
            cur = line[6:].strip(); scenes[cur] = []; order.append(cur); group = None; continue
        if cur is None:
            raise SyntaxError(f"step outside a scene: {line!r}")
        if line.startswith("group "):                 # group name … endgroup: one click in Play
            group = line[6:].strip().replace(" ", "_"); continue
        if line == "endgroup":
            group = None; continue
        step = _step(line, chars)
        if step:
            if group: step["group"] = group
            scenes[cur].append(step)
    if not scenes:
        raise SyntaxError("no scenes")
    return {"title": title, "characters": chars, "scenes": scenes,
            "start": order[0], "order": order}


def _step(line, chars):
    head = line.split(" ", 1)[0]
    arg = line[len(head):].strip()
    if head == "bg":                     # bg <spec> [fade=ms]
        parts = arg.split()
        step = {"op": "bg", "spec": _bg(parts[0])}
        for p in parts[1:]:
            if p.startswith("fade="):
                try: step["fade"] = int(p[5:])
                except ValueError: pass
        return step
    if head == "show":
        parts = arg.split()
        cid = parts[0]; pos = None; step = {"op": "show", "id": cid}
        for p in parts[1:]:
            if "=" in p:                       # x/y/z/zoom/opacity + tint : layer
                k, v = p.split("=", 1)
                if k in ("x", "y", "z", "zoom", "opacity"):
                    try: step[k] = int(v)
                    except ValueError: pass
                elif k == "tint":
                    step["tint"] = v
            elif p in POS_NAMES:
                pos = p
            else:                              # a bare word: expression
                step["expr"] = p
        if pos:
            step["pos"] = pos
        return step
    if head == "sprite":                 # sprite <char> [expression] <file.png>
        _sprite_line(chars, arg)
        return None
    if head == "animate":
        parts = arg.split()
        target, kind = parts[0], parts[1]
        params = {}
        for kv in parts[2:]:
            if "=" in kv:
                k, v = kv.split("=", 1)
                try: params[k] = int(v)
                except ValueError:
                    try: params[k] = float(v)
                    except ValueError: params[k] = v
        return {"op": "animate", "id": target, "kind": kind, "params": params}
    if head == "bgm":
        return {"op": "bgm", "stop": True} if arg.strip() == "stop" else {"op": "bgm", "file": arg.strip()}
    if head == "se":
        return {"op": "se", "file": arg.strip()}
    if head == "hide":
        return {"op": "hide", "id": arg}
    if head == "goto":
        return {"op": "goto", "target": arg}
    if head == "end":
        return {"op": "end"}
    if head == "choice":
        return {"op": "choice", "options": []}
    if line.startswith("- "):            # option of the previous choice (linked at build time)
        label, target = line[2:].rsplit("->", 1)
        return {"op": "_option", "label": label.strip(), "target": target.strip()}
    if head == "*":
        return {"op": "say", "who": "narrator", "text": arg}
    if head.endswith(":") or (":" in line and line.split(":", 1)[0].strip() in chars):
        who, text = line.split(":", 1)
        return {"op": "say", "who": who.strip(), "text": text.strip()}
    raise SyntaxError(f"unrecognized step: {line!r}")


def _bg(arg):
    if arg.startswith("grad:"):
        a, b = (arg[5:].split(",") + ["#000"])[:2]
        return {"kind": "grad", "a": a.strip(), "b": b.strip()}
    if arg.startswith("#"):
        return {"kind": "solid", "color": arg}
    return {"kind": "img", "file": arg}          # embedded on export (render_html)


def _asset(fname, base_dir):
    if not fname:
        return None
    path = os.path.join(base_dir, fname)
    with open(path, "rb") as f:
        data = f.read()
    ext = fname.rsplit(".", 1)[-1].lower()
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "webp": "image/webp", "gif": "image/gif", "ogg": "audio/ogg",
            "mp3": "audio/mpeg", "wav": "audio/wav", "m4a": "audio/mp4"}.get(ext, "application/octet-stream")
    return f"data:{mime};base64," + base64.b64encode(data).decode()


def _link_choices(model):
    """Attaches each '- option' to the immediately preceding 'choice' and drops it from the flow."""
    for sid, steps in model["scenes"].items():
        out = []
        for s in steps:
            if s["op"] == "_option":
                if not out or out[-1]["op"] != "choice":
                    raise SyntaxError(f"option without a choice in scene {sid}")
                out[-1]["options"].append({"label": s["label"], "target": s["target"]})
            else:
                out.append(s)
        model["scenes"][sid] = out
    return model


STEP_OPS = ["bg", "show", "hide", "say", "animate", "bgm", "se", "choice", "goto", "end"]


def default_step(op, model):
    """New step with default values (shared by the frontends)."""
    chars = [c for c in model["characters"] if c != "narrator"] or ["narrator"]
    return {
        "bg": {"op": "bg", "spec": {"kind": "grad", "a": "#101828", "b": "#304060"}},
        "show": {"op": "show", "id": chars[0], "pos": "center"},
        "hide": {"op": "hide", "id": chars[0]},
        "say": {"op": "say", "who": chars[0], "text": "..."},
        "animate": {"op": "animate", "id": chars[0], "kind": "jump",
                    "params": {"vib": 18, "cycle": 340}},
        "bgm": {"op": "bgm", "file": ""},
        "se": {"op": "se", "file": ""},
        "choice": {"op": "choice", "options": []},
        "goto": {"op": "goto", "target": model["order"][0]},
        "end": {"op": "end"},
    }[op]


def blank_model(title="New VN"):
    """Minimal valid project to start from in the editor."""
    return {"title": title,
            "characters": {"narrator": {"name": "", "color": "#cccccc"}},
            "scenes": {"inicio": [{"op": "end"}]},
            "order": ["inicio"], "start": "inicio"}


_IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


_SND_EXTS = {".wav", ".ogg", ".mp3"}

def list_assets(base, kind="img"):
    """Assets in the project directory, sorted ([] if it does not exist).
    kind: "img" (default), "audio" or "all"."""
    exts = {"img": _IMG_EXTS, "audio": _SND_EXTS}.get(kind, _IMG_EXTS | _SND_EXTS)
    try:
        names = os.listdir(base)
    except OSError:
        return []
    return sorted(f for f in names if os.path.splitext(f)[1].lower() in exts)


def validate(model, base=None):
    """List of project problems (empty = OK): references to missing scenes or
    characters, scenes with no exit, and (if `base` is given) missing assets."""
    probs = []
    scenes, chars = model["scenes"], model["characters"]
    for sid in model.get("order", scenes):
        has_exit = False
        for s in scenes[sid]:
            op = s["op"]
            if op in ("show", "hide", "animate") and s.get("id") not in chars:
                probs.append(f"scene {sid}: character '{s.get('id')}' does not exist")
            elif op == "show" and s.get("expr") and s["expr"] not in (chars[s["id"]].get("expr") or {}):
                probs.append(f"scene {sid}: {s['id']} has no expression '{s['expr']}'")
            if op == "say" and s.get("who") not in chars:
                probs.append(f"scene {sid}: character '{s.get('who')}' does not exist")
            if op == "goto":
                has_exit = True
                if s["target"] not in scenes:
                    probs.append(f"scene {sid}: goto to missing '{s['target']}'")
            if op == "end":
                has_exit = True
            if op == "choice":
                has_exit = True
                for o in s.get("options", []):
                    if o["target"] not in scenes:
                        probs.append(f"scene {sid}: option to missing '{o['target']}'")
            if base and op == "bg" and s["spec"].get("kind") == "img":
                if not os.path.exists(os.path.join(base, s["spec"]["file"])):
                    probs.append(f"scene {sid}: missing background '{s['spec']['file']}'")
            if base and op in ("bgm", "se") and s.get("file"):
                if not os.path.exists(os.path.join(base, s["file"])):
                    probs.append(f"scene {sid}: missing audio '{s['file']}'")
        if not has_exit:
            probs.append(f"scene {sid}: no exit (end/goto/choice)")
    if base:
        for cid, c in chars.items():
            if c.get("sprite") and not os.path.exists(os.path.join(base, c["sprite"])):
                probs.append(f"character {cid}: missing sprite '{c['sprite']}'")
            for ex, f in (c.get("expr") or {}).items():
                if not os.path.exists(os.path.join(base, f)):
                    probs.append(f"character {cid}: missing sprite for '{ex}': '{f}'")
    return probs


def duplicate_scene(model, sid):
    """Duplicates a scene (deep-copied content) with a unique id, right after the original."""
    import copy
    scenes = model["scenes"]
    base = f"{sid}_copy"; new = base; i = 2
    while new in scenes:
        new = f"{base}{i}"; i += 1
    scenes[new] = copy.deepcopy(scenes[sid])
    model["order"].insert(model["order"].index(sid) + 1, new)
    return new


def duplicate_step(steps, i):
    """Inserts a copy of step i right after it."""
    import copy
    steps.insert(i + 1, copy.deepcopy(steps[i]))


def move_scene(model, sid, delta):
    """Moves a scene within the order. False if it would fall out of range."""
    o = model["order"]; i = o.index(sid); j = i + delta
    if 0 <= j < len(o):
        o[i], o[j] = o[j], o[i]
        return True
    return False


def rename_character(model, old, new):
    """Renames a character and repoints all its references. False if not applicable."""
    chars = model["characters"]
    if old not in chars or new in chars or old == "narrator" or not new:
        return False
    chars[new] = chars.pop(old)
    for steps in model["scenes"].values():
        for s in steps:
            if s["op"] in ("show", "hide", "animate") and s.get("id") == old:
                s["id"] = new
            elif s["op"] == "say" and s.get("who") == old:
                s["who"] = new
    return True


def to_text(model):
    """Serializes a model (as returned by parse) back to .vn text."""
    out = [f"title: {model['title']}"]
    for cid, c in model["characters"].items():
        if cid == "narrator":
            continue
        line = f'character {cid} "{c["name"]}"'
        if c.get("color"): line += f' color={c["color"]}'
        out.append(line)
        if c.get("sprite"): out.append(f'sprite {cid} {c["sprite"]}')
        for ex, f in (c.get("expr") or {}).items():
            out.append(f'sprite {cid} {ex} {f}')
    out.append("")
    for sid in model.get("order", model["scenes"]):
        out.append(f"scene {sid}")
        cur_g = None
        for s in model["scenes"][sid]:
            g = s.get("group")
            if g != cur_g:                              # markers around each run
                if cur_g: out.append("  endgroup")
                if g: out.append(f"  group {g}")
                cur_g = g
            out.append("  " + _step_text(s))
        if cur_g: out.append("  endgroup")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def _step_text(s):
    op = s["op"]
    if op == "bg":
        sp = s["spec"]; fade = f" fade={s['fade']}" if s.get("fade") else ""
        if sp["kind"] == "grad": return f"bg grad:{sp['a']},{sp['b']}" + fade
        if sp["kind"] == "solid": return f"bg {sp['color']}" + fade
        return f"bg {sp.get('file', '?.png')}" + fade   # see note in build()
    if op == "show":
        t = f"show {s['id']}" + (f" {s['expr']}" if s.get("expr") else "") \
            + (f" {s['pos']}" if s.get("pos") else "")
        if "x" in s: t += f" x={s['x']}"
        if "y" in s: t += f" y={s['y']}"
        if "z" in s: t += f" z={s['z']}"
        if "zoom" in s: t += f" zoom={s['zoom']}"
        if "opacity" in s: t += f" opacity={s['opacity']}"
        if "tint" in s: t += f" tint={s['tint']}"
        return t
    if op == "hide": return f"hide {s['id']}"
    if op == "say":
        return f"* {s['text']}" if s["who"] == "narrator" else f"{s['who']}: {s['text']}"
    if op == "animate":
        kv = " ".join(f"{k}={v}" for k, v in s.get("params", {}).items())
        return f"animate {s['id']} {s['kind']} {kv}".rstrip()
    if op == "choice":
        return "choice\n" + "\n".join(f"    - {o['label']} -> {o['target']}"
                                      for o in s.get("options", []))
    if op == "bgm": return "bgm stop" if s.get("stop") else f"bgm {s['file']}"
    if op == "se": return f"se {s['file']}"
    if op == "goto": return f"goto {s['target']}"
    if op == "end": return "end"
    return f"# ? {op}"


def _embed(model, base_dir):
    """Copy of the model with assets embedded as data URIs (for the HTML)."""
    import copy
    m = copy.deepcopy(model)
    def dat(f):
        try: return _asset(f, base_dir)
        except OSError: return None
    for c in m["characters"].values():
        if c.get("sprite"):
            c["spriteData"] = dat(c["sprite"])
        if c.get("expr"):                          # one image per expression
            c["exprData"] = {ex: dat(f) for ex, f in c["expr"].items()}
    for steps in m["scenes"].values():
        for s in steps:
            if s["op"] == "bg" and s["spec"].get("kind") == "img":
                s["spec"]["data"] = dat(s["spec"]["file"])
            elif s["op"] in ("bgm", "se") and s.get("file"):
                s["data"] = dat(s["file"])
    return m


def build(vn_path, out_html):
    text = open(vn_path, encoding="utf-8").read()
    model = _link_choices(parse(text))
    base = os.path.dirname(os.path.abspath(vn_path))
    open(out_html, "w", encoding="utf-8").write(render_html(model, base))
    n = sum(len(v) for v in model["scenes"].values())
    print(f"{len(model['scenes'])} scenes, {n} steps -> {out_html}")
    return out_html


def render_html(model, base_dir="."):
    data = json.dumps(_embed(model, base_dir), ensure_ascii=False)
    return _TEMPLATE.replace("/*DATA*/", data).replace("__TITLE__", html.escape(model["title"]))


_TEMPLATE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cinzel:wght@500;700&family=Zen+Kaku+Gothic+New:wght@400;500;700&display=swap">
<style>
  /* Committed dark world (game): indigo night + amber lamplight. Single theme. */
  :root{
    --ground:#0b0e1c; --stage:#05060f;
    --box-a:#141b3aee; --box-b:#0a0e22f2;
    --edge:#31406e; --amber:#e8b04b; --amber-soft:#f0c579;
    --ink:#eef1fb; --muted:#9aa6c8; --rose:#e58aa8;
    --disp:"Cinzel",Georgia,serif;
    --body:"Zen Kaku Gothic New","Hiragino Kaku Gothic ProN",system-ui,sans-serif;
    color-scheme:dark;
  }
  *{box-sizing:border-box}
  body{margin:0;background:
        radial-gradient(120% 90% at 50% 0%,#141a33 0%,var(--ground) 60%,#05060d 100%);
       font:16px/1.6 var(--body);color:var(--ink);
       display:flex;min-height:100vh;align-items:center;justify-content:center;padding:16px}
  #stage{position:relative;width:min(96vw,912px);aspect-ratio:640/448;
         background:var(--stage);border-radius:12px;overflow:hidden;user-select:none;
         box-shadow:0 24px 70px #000c,0 0 0 1px #ffffff10 inset}
  #bg2{position:absolute;inset:0;background-size:cover;background-position:center;opacity:0;pointer-events:none}
  #bg{position:absolute;inset:0;background-size:cover;background-position:center;
      transition:opacity .4s,background .4s}
  #vignette{position:absolute;inset:0;pointer-events:none;
      background:radial-gradient(130% 100% at 50% 38%,transparent 55%,#000 140%)}
  .sprite{position:absolute;bottom:0;height:90%;display:flex;align-items:flex-end;
          justify-content:center;transition:opacity .3s ease,transform .3s ease}
  .sprite img{height:100%;filter:drop-shadow(0 6px 16px #000a)}
  .ph{width:min(44%,240px);height:96%;border-radius:120px 120px 18px 18px;
      display:flex;align-items:center;justify-content:center;font-family:var(--disp);
      font-size:min(10vw,72px);font-weight:700;color:#fff2d8;
      background:linear-gradient(180deg,#ffffff2a,#0000006a);
      box-shadow:0 0 0 1px #ffffff22 inset,0 10px 30px #0007}
  .left{left:3%}.center{left:50%;transform:translateX(-50%)}.right{right:3%}
  #box{position:absolute;left:3.5%;right:3.5%;bottom:4%;min-height:25%;
       background:linear-gradient(180deg,var(--box-a),var(--box-b));
       border:1px solid var(--edge);border-top:2px solid var(--amber);
       border-radius:4px 4px 10px 10px;padding:26px 26px 20px;
       box-shadow:0 14px 40px #0008,0 0 0 1px #00000060}
  #who{position:absolute;top:-17px;left:20px;font-family:var(--disp);font-weight:700;
       font-size:.95rem;letter-spacing:.08em;padding:4px 16px;color:#0b0e1c;
       background:linear-gradient(180deg,var(--amber-soft),var(--amber));
       border-radius:3px;box-shadow:0 3px 10px #0007;min-height:1px}
  #who:empty{opacity:0}
  #text{white-space:pre-wrap;text-wrap:pretty;font-size:clamp(15px,2.3vw,20px);max-width:64ch}
  #cursor{position:absolute;right:18px;bottom:12px;color:var(--amber);
          opacity:.85;animation:blink 1.1s steps(2,start) infinite}
  @keyframes blink{50%{opacity:0}}
  #choices{position:absolute;inset:0;display:flex;flex-direction:column;gap:12px;
           align-items:center;justify-content:center;
           background:radial-gradient(80% 80% at 50% 50%,#0a0e22cc,#02030acc)}
  #choices button{font:500 1rem/1.3 var(--body);color:var(--ink);cursor:pointer;
           background:linear-gradient(180deg,#1a2450,#111a3c);
           border:1px solid var(--edge);border-left:3px solid var(--amber);
           padding:14px 26px;border-radius:6px;min-width:min(70%,420px);text-align:left;
           transition:background .15s,transform .1s}
  #choices button:hover,#choices button:focus-visible{background:#223066;transform:translateX(3px)}
  #choices button:focus-visible{outline:2px solid var(--amber-soft);outline-offset:2px}
  #end{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
       font-family:var(--disp);font-weight:700;letter-spacing:.12em;font-size:2rem;
       color:var(--amber-soft);background:#03040acc}
  #hint{position:absolute;top:10px;right:14px;font-size:.7rem;letter-spacing:.1em;
        text-transform:uppercase;color:var(--muted);opacity:.55}
  /* CSS approximation of the engine actions (Python is the source of truth) */
  @keyframes vn-jump{0%,100%{transform:translateY(0)}50%{transform:translateY(-6%)}}
  @keyframes vn-fall{0%{transform:translateY(-30%);opacity:.2}100%{transform:translateY(0);opacity:1}}
  @keyframes vn-shake{0%,100%{transform:translate(0,0)}25%{transform:translate(-1.5%,1%)}75%{transform:translate(1.5%,-1%)}}
  @keyframes vn-wave{0%,100%{transform:translateX(0)}25%{transform:translateX(2%)}75%{transform:translateX(-2%)}}
  .center.sprite[style*="vn-"]{transform-origin:bottom center}
  @media (prefers-reduced-motion:reduce){#cursor{animation:none}*{transition:none!important}}
</style></head><body>
<div id="stage">
  <div id="bg"></div><div id="bg2"></div>
  <div id="sprites"></div>
  <div id="box"><div id="who"></div><div id="text"></div><div id="cursor">▼</div></div>
  <div id="choices" hidden></div>
  <div id="end" hidden></div>
  <div id="hint">click / space</div>
  <audio id="bgm" loop></audio>
</div>
<script>
const M = /*DATA*/;
const $ = s => document.querySelector(s);
const sprites = {};   // id -> element
let scene, ip;

function bgCss(spec){
  if(spec.kind==="img") return `center/cover url(${spec.data})`;
  if(spec.kind==="grad") return `linear-gradient(160deg,${spec.a},${spec.b})`;
  return spec.color;
}
function setBg(spec, fade){
  const bg = $("#bg"), old = $("#bg2");
  if(fade && bg.style.background){          // crossfade: the old one fades out on top of the new one
    old.style.transition = "none"; old.style.background = bg.style.background; old.style.opacity = 1;
    void old.offsetWidth;
    old.style.transition = `opacity ${fade}ms linear`; old.style.opacity = 0;
  }
  bg.style.background = bgCss(spec);
}
function charColor(id){ return (M.characters[id]||{}).color || "#ccc"; }
function show(id,pos,expr){
  const c = M.characters[id]||{};
  let el = sprites[id];
  const was = !!el;
  if(!el){ el = document.createElement("div"); el.className="sprite"; $("#sprites").appendChild(el); sprites[id]=el; }
  if(pos || !was) el.className = "sprite "+(pos||"center");   // no pos: stays where it is
  const img = (c.exprData||{})[expr] || c.spriteData;
  if(img){ el.innerHTML = `<img src="${img}">`; }
  else { const nm=c.name||id;
         el.innerHTML = `<div class="ph" style="background:${charColor(id)}">${(nm[0]||"?").toUpperCase()}</div>`; }
  el.style.opacity=1; el.style.animation="";
}
function hide(id){ if(sprites[id]) sprites[id].style.opacity=0; }
function playBgm(s){
  const a=$("#bgm");
  if(s.stop){ a.pause(); return; }
  if(s.data){ a.src=s.data; a.play().catch(()=>{}); }
}
function animate(id,kind){        // CSS approximation of the engine actions
  const el = sprites[id]; if(!el) return;
  const css = {jump:"vn-jump .5s 2", jumponce:"vn-jump .5s 1", vibrate:"vn-shake .4s 3",
               wave:"vn-wave 1s 2", fall:"vn-fall .6s 1"}[kind];
  if(css){ el.style.animation="none"; void el.offsetWidth; el.style.animation=css; }
}

function enter(id){ scene = M.scenes[id]; ip = 0; step(); }

function step(){
  $("#choices").hidden = true;
  while(ip < scene.length){
    const s = scene[ip++];
    if(s.op==="bg"){ setBg(s.spec, s.fade); continue; }
    if(s.op==="show"){ show(s.id, s.pos, s.expr); continue; }
    if(s.op==="animate"){ animate(s.id,s.kind); continue; }
    if(s.op==="hide"){ hide(s.id); continue; }
    if(s.op==="bgm"){ playBgm(s); continue; }
    if(s.op==="se"){ if(s.data){ try{ new Audio(s.data).play().catch(()=>{});}catch(e){} } continue; }
    if(s.op==="goto"){ return enter(s.target); }
    if(s.op==="end"){ return theEnd(); }
    if(s.op==="say"){ return say(s); }
    if(s.op==="choice"){ return choose(s); }
  }
  theEnd();
}

let typing=null, full="";
function say(s){
  const c = M.characters[s.who]||{name:s.who,color:"#ccc"};
  $("#who").textContent = c.name; $("#who").style.color = c.color;
  full = s.text; const t=$("#text"); t.textContent="";
  clearInterval(typing); let i=0;
  typing = setInterval(()=>{ t.textContent = full.slice(0,++i); if(i>=full.length) clearInterval(typing); }, 18);
  $("#cursor").hidden=false;
}
function finishType(){ if(typing){ clearInterval(typing); typing=null; $("#text").textContent=full; return true; } return false; }

function choose(s){
  const box=$("#choices"); box.innerHTML=""; box.hidden=false; $("#cursor").hidden=true;
  s.options.forEach(o=>{ const b=document.createElement("button"); b.textContent=o.label;
    b.onclick=()=>{ box.hidden=true; enter(o.target); }; box.appendChild(b); });
}
function theEnd(){ $("#end").hidden=false; $("#end").textContent="The End"; $("#cursor").hidden=true; }

function advance(){
  if(!$("#choices").hidden || !$("#end").hidden) return;
  if(finishType()) return;   // first click completes the text, the second advances
  step();
}
$("#stage").addEventListener("click", advance);
addEventListener("keydown", e=>{ if(e.key===" "||e.key==="Enter"){ e.preventDefault(); advance(); } });
enter(M.start);
</script></body></html>"""


DEMO_VN = """\
title: The Familiar of Zero — SDK Demo
character saito "Saito" color=#7cc4ff
character louise "Louise" color=#ff9ec2

scene intro
  bg grad:#101830,#2a4a80
  * A tower of the Academy of Magic. Midnight.
  show louise left
  louise: Awake again, dog?
  show saito right
  saito: Couldn't sleep. And you?
  louise: ...that's none of your business.
  choice
    - Press gently -> closer
    - Change the subject -> subject

scene closer
  louise: ...I miss home. Happy now?
  saito: Thanks for telling me.
  goto ending

scene subject
  saito: Nice night, isn't it?
  louise: Hmpf.
  goto ending

scene ending
  * Outside, the breeze stirred the curtains.
  end
"""


def _ops_selfcheck():
    # validate: catches gotos/characters/dead-ends
    bad = _link_choices(parse(
        'title: t\ncharacter a "A"\n'
        'scene uno\n  show b left\n  goto ninguna\n'
        'scene dos\n  a: hola\n'))
    probs = validate(bad)
    assert any("ninguna" in p for p in probs), probs
    assert any("'b'" in p for p in probs), probs
    assert any("dos" in p and "no exit" in p for p in probs), probs
    assert validate(_link_choices(parse(DEMO_VN))) == []
    # rename_character: moves and repoints references
    mm = _link_choices(parse('title: t\ncharacter x "X"\nscene s\n  show x left\n'
                             '  x: hola\n  animate x jump\n  end\n'))
    assert rename_character(mm, "x", "y") is True
    assert "y" in mm["characters"] and "x" not in mm["characters"]
    stp = mm["scenes"]["s"]
    assert stp[0]["id"] == "y" and stp[1]["who"] == "y" and stp[2]["id"] == "y", stp
    assert rename_character(mm, "nope", "z") is False and rename_character(mm, "y", "y") is False
    # duplicate_scene: copy with a unique id, inserted right after
    dm = _link_choices(parse('title: t\ncharacter a "A"\nscene uno\n  a: hola\n  end\n'))
    nid = duplicate_scene(dm, "uno")
    assert nid in dm["scenes"] and nid != "uno"
    assert dm["scenes"][nid] == dm["scenes"]["uno"] and dm["scenes"][nid] is not dm["scenes"]["uno"]
    assert dm["order"].index(nid) == dm["order"].index("uno") + 1
    assert duplicate_scene(dm, "uno") != nid          # unique id the 2nd time too
    # duplicate_step: copy inserted right after
    stp = [{"op": "end"}]
    duplicate_step(stp, 0)
    assert len(stp) == 2 and stp[0] == stp[1] and stp[0] is not stp[1]
    # move_scene: reorders within order, respects the edges
    om = _link_choices(parse('title: t\nscene a\n  end\nscene b\n  end\nscene c\n  end\n'))
    assert om["order"] == ["a", "b", "c"]
    assert move_scene(om, "a", 1) and om["order"] == ["b", "a", "c"]
    assert move_scene(om, "a", -1) and om["order"] == ["a", "b", "c"]
    assert move_scene(om, "a", -1) is False and move_scene(om, "c", 1) is False
    # list_assets: project images, sorted; missing dir -> []
    import tempfile, os as _os
    d = tempfile.mkdtemp()
    for f in ("b.jpg", "a.png", "note.txt"):
        open(_os.path.join(d, f), "w").close()
    assert list_assets(d) == ["a.png", "b.jpg"], list_assets(d)
    assert list_assets(_os.path.join(d, "nope")) == []
    # blank_model: minimal valid project and round-trip
    bm = blank_model()
    assert bm["order"] and bm["start"] == bm["order"][0]
    assert "narrator" in bm["characters"]
    assert validate(bm) == []                          # starts with no problems
    assert list(_link_choices(parse(to_text(bm)))["scenes"]) == bm["order"]
    # audio: bgm/se in the .vn + round-trip
    au = _link_choices(parse('title: t\ncharacter a "A"\nscene s\n'
                             '  bgm tema.ogg\n  a: hola\n  se golpe.wav\n  bgm stop\n  end\n'))
    sts = au["scenes"]["s"]
    assert sts[0] == {"op": "bgm", "file": "tema.ogg"}, sts[0]
    assert sts[2] == {"op": "se", "file": "golpe.wav"}, sts[2]
    assert sts[3].get("stop") is True, sts[3]
    txt = to_text(au)
    assert "bgm tema.ogg" in txt and "se golpe.wav" in txt and "bgm stop" in txt, txt
    assert _link_choices(parse(txt))["scenes"]["s"][3].get("stop") is True


def demo():
    import tempfile
    _ops_selfcheck()
    model = _link_choices(parse(DEMO_VN))
    assert model["start"] == "intro"
    assert model["characters"]["louise"]["color"] == "#ff9ec2"
    ch = [s for s in model["scenes"]["intro"] if s["op"] == "choice"][0]
    assert len(ch["options"]) == 2 and ch["options"][0]["target"] == "closer"
    says = [s for s in model["scenes"]["intro"] if s["op"] == "say"]
    assert says[0]["who"] == "narrator" and says[1]["who"] == "louise"
    h = render_html(model)
    assert "<title>" in h and "M.start" in h and "The Familiar of Zero" in h
    assert "/*DATA*/" not in h        # the JSON was injected
    print("demo OK")


def cli(argv):
    if not argv or argv[0] == "demo":
        return demo()
    if argv[0] == "build":
        return build(argv[1], argv[2])
    if argv[0] == "demo-build":       # generates the example player
        open("_demo.vn", "w", encoding="utf-8").write(DEMO_VN)
        return build("_demo.vn", argv[1] if len(argv) > 1 else "vn_demo.html")
    print(__doc__)


if __name__ == "__main__":
    cli(sys.argv[1:])
