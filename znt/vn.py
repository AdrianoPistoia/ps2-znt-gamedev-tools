#!/usr/bin/env python3
"""Capa 3 — autoría: un formato de VN simple (.vn) y un player HTML autocontenido.

El autor escribe escenas en texto y assets PNG propios; `build` compila a un
player HTML de una sola pieza (JSON de escenas + un motorcito JS + assets
embebidos como data URI), que se juega en el browser: click para avanzar,
botones para elegir. Reusa el modelo de escena de la capa 1 (fondo + sprites +
cuadro de diálogo), pero corre en el browser para ser compartible sin deps.

Formato (línea por línea):

    title: Mi Historia
    character saito "Saito" color=#6cd
    character louise "Louise" color=#e79

    scene intro
      bg grad:#1a2340,#3a5a8a          # o  bg fondo.png  o  bg #223
      show saito right
      saito: Hola. Soy Saito.
      louise: ¡Silencio, perro!
      * Un silencio incómodo llenó la sala.
      choice
        - Disculparse -> paz
        - Contestar   -> pelea

    scene paz
      narrator: Hiciste las paces.
      end

  python -m znt vn build historia.vn player.html
  python -m znt vn demo
"""
import sys, os, json, base64, html


def parse(text):
    title = "Visual Novel"
    chars = {"narrator": {"name": "", "color": "#cccccc"}}
    scenes = {}          # id -> lista de pasos
    order = []
    cur = None
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
            chars[cid] = {"name": name.strip().strip('"'), "color": color}
            continue
        if line.startswith("scene "):
            cur = line[6:].strip(); scenes[cur] = []; order.append(cur); continue
        if cur is None:
            raise SyntaxError(f"paso fuera de una escena: {line!r}")
        step = _step(line, chars)
        if step:
            scenes[cur].append(step)
    if not scenes:
        raise SyntaxError("no hay escenas")
    return {"title": title, "characters": chars, "scenes": scenes,
            "start": order[0], "order": order}


def _step(line, chars):
    head = line.split(" ", 1)[0]
    arg = line[len(head):].strip()
    if head == "bg":
        return {"op": "bg", "spec": _bg(arg)}
    if head == "show":
        parts = arg.split()
        cid = parts[0]; pos = "center"; step = {"op": "show", "id": cid}
        for p in parts[1:]:
            if "=" in p:                       # x/y/z/zoom/opacity + tint : capa
                k, v = p.split("=", 1)
                if k in ("x", "y", "z", "zoom", "opacity"):
                    try: step[k] = int(v)
                    except ValueError: pass
                elif k == "tint":
                    step["tint"] = v
            else:
                pos = p
        step["pos"] = pos
        return step
    if head == "sprite":                 # sprite <char> <file.png>: define arte del personaje
        cid, f = arg.split(None, 1)
        chars.setdefault(cid, {"name": cid, "color": "#ccc"})["sprite"] = f.strip()
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
    if head == "hide":
        return {"op": "hide", "id": arg}
    if head == "goto":
        return {"op": "goto", "target": arg}
    if head == "end":
        return {"op": "end"}
    if head == "choice":
        return {"op": "choice", "options": []}
    if line.startswith("- "):            # opción de un choice previo (se enlaza al armar)
        label, target = line[2:].rsplit("->", 1)
        return {"op": "_option", "label": label.strip(), "target": target.strip()}
    if head == "*":
        return {"op": "say", "who": "narrator", "text": arg}
    if head.endswith(":") or (":" in line and line.split(":", 1)[0].strip() in chars):
        who, text = line.split(":", 1)
        return {"op": "say", "who": who.strip(), "text": text.strip()}
    raise SyntaxError(f"paso no reconocido: {line!r}")


def _bg(arg):
    if arg.startswith("grad:"):
        a, b = (arg[5:].split(",") + ["#000"])[:2]
        return {"kind": "grad", "a": a.strip(), "b": b.strip()}
    if arg.startswith("#"):
        return {"kind": "solid", "color": arg}
    return {"kind": "img", "file": arg}          # se embebe al exportar (render_html)


def _asset(fname, base_dir):
    if not fname:
        return None
    path = os.path.join(base_dir, fname)
    with open(path, "rb") as f:
        data = f.read()
    ext = fname.rsplit(".", 1)[-1].lower()
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "webp": "image/webp", "gif": "image/gif"}.get(ext, "application/octet-stream")
    return f"data:{mime};base64," + base64.b64encode(data).decode()


def _link_choices(model):
    """Une cada '- opción' al 'choice' inmediatamente anterior y las saca del flujo."""
    for sid, steps in model["scenes"].items():
        out = []
        for s in steps:
            if s["op"] == "_option":
                if not out or out[-1]["op"] != "choice":
                    raise SyntaxError(f"opción sin choice en escena {sid}")
                out[-1]["options"].append({"label": s["label"], "target": s["target"]})
            else:
                out.append(s)
        model["scenes"][sid] = out
    return model


def validate(model, base=None):
    """Lista de problemas del proyecto (vacía = OK): referencias a escenas o
    personajes inexistentes, escenas sin salida, y (si se da `base`) assets faltantes."""
    probs = []
    scenes, chars = model["scenes"], model["characters"]
    for sid in model.get("order", scenes):
        has_exit = False
        for s in scenes[sid]:
            op = s["op"]
            if op in ("show", "hide", "animate") and s.get("id") not in chars:
                probs.append(f"escena {sid}: personaje '{s.get('id')}' no existe")
            if op == "say" and s.get("who") not in chars:
                probs.append(f"escena {sid}: personaje '{s.get('who')}' no existe")
            if op == "goto":
                has_exit = True
                if s["target"] not in scenes:
                    probs.append(f"escena {sid}: goto a '{s['target']}' inexistente")
            if op == "end":
                has_exit = True
            if op == "choice":
                has_exit = True
                for o in s.get("options", []):
                    if o["target"] not in scenes:
                        probs.append(f"escena {sid}: opción a '{o['target']}' inexistente")
            if base and op == "bg" and s["spec"].get("kind") == "img":
                if not os.path.exists(os.path.join(base, s["spec"]["file"])):
                    probs.append(f"escena {sid}: falta el fondo '{s['spec']['file']}'")
        if not has_exit:
            probs.append(f"escena {sid}: sin salida (end/goto/choice)")
    if base:
        for cid, c in chars.items():
            if c.get("sprite") and not os.path.exists(os.path.join(base, c["sprite"])):
                probs.append(f"personaje {cid}: falta el sprite '{c['sprite']}'")
    return probs


def duplicate_scene(model, sid):
    """Duplica una escena (contenido deep-copy) con id único, tras la original."""
    import copy
    scenes = model["scenes"]
    base = f"{sid}_copia"; new = base; i = 2
    while new in scenes:
        new = f"{base}{i}"; i += 1
    scenes[new] = copy.deepcopy(scenes[sid])
    model["order"].insert(model["order"].index(sid) + 1, new)
    return new


def duplicate_step(steps, i):
    """Inserta una copia del paso i justo después."""
    import copy
    steps.insert(i + 1, copy.deepcopy(steps[i]))


def rename_character(model, old, new):
    """Renombra un personaje y reapunta todas sus referencias. False si no aplica."""
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
    """Serializa un modelo (el que devuelve parse) de vuelta a texto .vn."""
    out = [f"title: {model['title']}"]
    for cid, c in model["characters"].items():
        if cid == "narrator":
            continue
        line = f'character {cid} "{c["name"]}"'
        if c.get("color"): line += f' color={c["color"]}'
        out.append(line)
        if c.get("sprite"): out.append(f'sprite {cid} {c["sprite"]}')
    out.append("")
    for sid in model.get("order", model["scenes"]):
        out.append(f"scene {sid}")
        for s in model["scenes"][sid]:
            out.append("  " + _step_text(s))
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def _step_text(s):
    op = s["op"]
    if op == "bg":
        sp = s["spec"]
        if sp["kind"] == "grad": return f"bg grad:{sp['a']},{sp['b']}"
        if sp["kind"] == "solid": return f"bg {sp['color']}"
        return f"bg {sp.get('file', '?.png')}"          # ver nota en build()
    if op == "show":
        t = f"show {s['id']} {s.get('pos','center')}"
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
    if op == "goto": return f"goto {s['target']}"
    if op == "end": return "end"
    return f"# ? {op}"


def _embed(model, base_dir):
    """Copia el modelo con los assets embebidos como data URI (para el HTML)."""
    import copy
    m = copy.deepcopy(model)
    for c in m["characters"].values():
        if c.get("sprite"):
            c["spriteData"] = _asset(c["sprite"], base_dir)
    for steps in m["scenes"].values():
        for s in steps:
            if s["op"] == "bg" and s["spec"].get("kind") == "img":
                s["spec"]["data"] = _asset(s["spec"]["file"], base_dir)
    return m


def build(vn_path, out_html):
    text = open(vn_path, encoding="utf-8").read()
    model = _link_choices(parse(text))
    base = os.path.dirname(os.path.abspath(vn_path))
    open(out_html, "w", encoding="utf-8").write(render_html(model, base))
    n = sum(len(v) for v in model["scenes"].values())
    print(f"{len(model['scenes'])} escenas, {n} pasos -> {out_html}")
    return out_html


def render_html(model, base_dir="."):
    data = json.dumps(_embed(model, base_dir), ensure_ascii=False)
    return _TEMPLATE.replace("/*DATA*/", data).replace("__TITLE__", html.escape(model["title"]))


_TEMPLATE = r"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cinzel:wght@500;700&family=Zen+Kaku+Gothic+New:wght@400;500;700&display=swap">
<style>
  /* Mundo oscuro comprometido (juego): noche indigo + candil ambar. Un solo tema. */
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
  /* aproximación CSS de las acciones del engine (Python es la fuente de verdad) */
  @keyframes vn-jump{0%,100%{transform:translateY(0)}50%{transform:translateY(-6%)}}
  @keyframes vn-fall{0%{transform:translateY(-30%);opacity:.2}100%{transform:translateY(0);opacity:1}}
  @keyframes vn-shake{0%,100%{transform:translate(0,0)}25%{transform:translate(-1.5%,1%)}75%{transform:translate(1.5%,-1%)}}
  @keyframes vn-wave{0%,100%{transform:translateX(0)}25%{transform:translateX(2%)}75%{transform:translateX(-2%)}}
  .center.sprite[style*="vn-"]{transform-origin:bottom center}
  @media (prefers-reduced-motion:reduce){#cursor{animation:none}*{transition:none!important}}
</style></head><body>
<div id="stage">
  <div id="bg"></div>
  <div id="sprites"></div>
  <div id="box"><div id="who"></div><div id="text"></div><div id="cursor">▼</div></div>
  <div id="choices" hidden></div>
  <div id="end" hidden></div>
  <div id="hint">click / espacio</div>
</div>
<script>
const M = /*DATA*/;
const $ = s => document.querySelector(s);
const sprites = {};   // id -> elemento
let scene, ip;

function setBg(spec){
  const bg = $("#bg");
  if(spec.kind==="img"){ bg.style.background = `center/cover url(${spec.data})`; }
  else if(spec.kind==="grad"){ bg.style.background = `linear-gradient(160deg,${spec.a},${spec.b})`; }
  else { bg.style.background = spec.color; }
}
function charColor(id){ return (M.characters[id]||{}).color || "#ccc"; }
function show(id,pos){
  const c = M.characters[id]||{};
  let el = sprites[id];
  if(!el){ el = document.createElement("div"); el.className="sprite"; $("#sprites").appendChild(el); sprites[id]=el; }
  el.className = "sprite "+(pos||"center");
  if(c.spriteData){ el.innerHTML = `<img src="${c.spriteData}">`; }
  else { const nm=c.name||id;
         el.innerHTML = `<div class="ph" style="background:${charColor(id)}">${(nm[0]||"?").toUpperCase()}</div>`; }
  el.style.opacity=1; el.style.animation="";
}
function hide(id){ if(sprites[id]) sprites[id].style.opacity=0; }
function animate(id,kind){        // aproximación CSS de las acciones del engine
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
    if(s.op==="bg"){ setBg(s.spec); continue; }
    if(s.op==="show"){ show(s.id,s.pos); continue; }
    if(s.op==="animate"){ animate(s.id,s.kind); continue; }
    if(s.op==="hide"){ hide(s.id); continue; }
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
function theEnd(){ $("#end").hidden=false; $("#end").textContent="Fin"; $("#cursor").hidden=true; }

function advance(){
  if(!$("#choices").hidden || !$("#end").hidden) return;
  if(finishType()) return;   // primer click completa el texto, el segundo avanza
  step();
}
$("#stage").addEventListener("click", advance);
addEventListener("keydown", e=>{ if(e.key===" "||e.key==="Enter"){ e.preventDefault(); advance(); } });
enter(M.start);
</script></body></html>"""


DEMO_VN = """\
title: El Familiar de Cero — Demo SDK
character saito "Saito" color=#7cc4ff
character louise "Louise" color=#ff9ec2

scene intro
  bg grad:#101830,#2a4a80
  * Una torre de la Academia de Magia. Media noche.
  show louise left
  louise: ¿Otra vez despierto, perro?
  show saito right
  saito: No podía dormir. ¿Y vos?
  louise: ...eso no es asunto tuyo.
  choice
    - Insistir con cuidado -> acerca
    - Cambiar de tema -> tema

scene acerca
  louise: ...Extraño mi casa. ¿Contento?
  saito: Gracias por contarme.
  goto fin

scene tema
  saito: Linda noche, ¿no?
  louise: Hmpf.
  goto fin

scene fin
  * Afuera, la brisa movió las cortinas.
  end
"""


def _ops_selfcheck():
    # validate: detecta gotos/personajes/dead-ends
    bad = _link_choices(parse(
        'title: t\ncharacter a "A"\n'
        'scene uno\n  show b left\n  goto ninguna\n'
        'scene dos\n  a: hola\n'))
    probs = validate(bad)
    assert any("ninguna" in p for p in probs), probs
    assert any("'b'" in p for p in probs), probs
    assert any("dos" in p and "salida" in p for p in probs), probs
    assert validate(_link_choices(parse(DEMO_VN))) == []
    # rename_character: mueve y reapunta referencias
    mm = _link_choices(parse('title: t\ncharacter x "X"\nscene s\n  show x left\n'
                             '  x: hola\n  animate x jump\n  end\n'))
    assert rename_character(mm, "x", "y") is True
    assert "y" in mm["characters"] and "x" not in mm["characters"]
    stp = mm["scenes"]["s"]
    assert stp[0]["id"] == "y" and stp[1]["who"] == "y" and stp[2]["id"] == "y", stp
    assert rename_character(mm, "nope", "z") is False and rename_character(mm, "y", "y") is False
    # duplicate_scene: copia con id único, insertada después
    dm = _link_choices(parse('title: t\ncharacter a "A"\nscene uno\n  a: hola\n  end\n'))
    nid = duplicate_scene(dm, "uno")
    assert nid in dm["scenes"] and nid != "uno"
    assert dm["scenes"][nid] == dm["scenes"]["uno"] and dm["scenes"][nid] is not dm["scenes"]["uno"]
    assert dm["order"].index(nid) == dm["order"].index("uno") + 1
    assert duplicate_scene(dm, "uno") != nid          # id único la 2da vez
    # duplicate_step: copia insertada después
    stp = [{"op": "end"}]
    duplicate_step(stp, 0)
    assert len(stp) == 2 and stp[0] == stp[1] and stp[0] is not stp[1]


def demo():
    import tempfile
    _ops_selfcheck()
    model = _link_choices(parse(DEMO_VN))
    assert model["start"] == "intro"
    assert model["characters"]["louise"]["color"] == "#ff9ec2"
    ch = [s for s in model["scenes"]["intro"] if s["op"] == "choice"][0]
    assert len(ch["options"]) == 2 and ch["options"][0]["target"] == "acerca"
    says = [s for s in model["scenes"]["intro"] if s["op"] == "say"]
    assert says[0]["who"] == "narrator" and says[1]["who"] == "louise"
    h = render_html(model)
    assert "<title>" in h and "M.start" in h and "El Familiar de Cero" in h
    assert "/*DATA*/" not in h        # el JSON se inyectó
    print("demo OK")


def cli(argv):
    if not argv or argv[0] == "demo":
        return demo()
    if argv[0] == "build":
        return build(argv[1], argv[2])
    if argv[0] == "demo-build":       # genera el player de ejemplo
        open("_demo.vn", "w", encoding="utf-8").write(DEMO_VN)
        return build("_demo.vn", argv[1] if len(argv) > 1 else "vn_demo.html")
    print(__doc__)


if __name__ == "__main__":
    cli(sys.argv[1:])
