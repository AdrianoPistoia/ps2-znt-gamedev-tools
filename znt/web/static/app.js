/* VN Studio (web) — comportamiento del editor.
 * El servidor Python es la fuente de verdad: acá sólo pintamos su estado y
 * mandamos ops. La lógica pura (layout, snap, geometría) vive en logic.js. */
"use strict";
const $ = s => document.querySelector(s);
let S = null;              // estado del servidor
let SG = null;             // stage actual (layout que manda Python)
let ASSETS = [], AUDIO = [];
let SEL = null;            // capa seleccionada (sólo del cliente)

const api = {
  model: () => fetch("/api/model").then(r => r.json()),
  op: o => fetch("/api/op", {method:"POST", headers:{"Content-Type":"application/json"},
                             body: JSON.stringify(o)}).then(r => r.json()),
  stage: (sc, st) => fetch(`/api/stage?scene=${encodeURIComponent(sc)}&step=${st}`).then(r => r.json()),
  assets: () => fetch("/api/assets").then(r => r.json()),
};
async function op(o){ S = await api.op(o); await refresh(); }

/* ---------- paneles: splitters con memoria ---------- */
const PANES = {
  out: {var:"--outw", min:170, other:520, axis:"x"},
  ins: {var:"--insw", min:220, other:470, axis:"x"},
  tl:  {var:"--tlh", min:90,  other:300, axis:"y"},
};
function setPane(k, px){
  const p = PANES[k];
  const total = p.axis === "x" ? innerWidth : innerHeight;
  const v = VNS.clampPane(px, total, p.min, p.other);
  document.documentElement.style.setProperty(p.var, v + "px");
  try { localStorage.setItem("vns" + k, v); } catch (e) {}
  layoutStage();
}
for (const [k, p] of Object.entries(PANES)) {
  const saved = (() => { try { return parseInt(localStorage.getItem("vns" + k), 10); } catch (e) { return NaN; } })();
  if (saved > 0) setPane(k, saved);
  const el = document.querySelector(`[data-pane="${k}"]`);
  el.addEventListener("pointerdown", e => {
    el.classList.add("drag"); el.setPointerCapture(e.pointerId);
    const move = ev => setPane(k, k === "out" ? ev.clientX
                              : k === "ins" ? innerWidth - ev.clientX
                              : innerHeight - ev.clientY);
    const up = () => { el.classList.remove("drag");
                       el.removeEventListener("pointermove", move);
                       el.removeEventListener("pointerup", up); };
    el.addEventListener("pointermove", move); el.addEventListener("pointerup", up);
    e.preventDefault();
  });
}

/* ---------- viewport: el stage entra entero y centrado ---------- */
function layoutStage(){
  const vp = $("#viewport").getBoundingClientRect();
  const r = VNS.fitRect(vp.width - 28, vp.height - 28, SG ? SG.w : 640, SG ? SG.h : 448);
  Object.assign($("#stagewrap").style, {width: r.w + "px", height: r.h + "px"});
  $("#m-zoom").textContent = r.scale ? Math.round(r.scale * 100) + "%" : "";
}
addEventListener("resize", layoutStage);

/* ---------- listas ---------- */
function stepText(s){
  switch(s.op){
    case "bg": { const p = s.spec||{};
      return "bg " + (p.kind==="grad" ? `grad:${p.a},${p.b}` : p.kind==="solid" ? p.color : p.file); }
    case "show": return `show ${s.id} ${s.pos||"center"}` +
      ["x","y","z","zoom","opacity"].map(k=> k in s ? ` ${k}=${s[k]}`:"").join("") + (s.tint?` tint=${s.tint}`:"");
    case "hide": return `hide ${s.id}`;
    case "say": return s.who==="narrator" ? `* ${s.text}` : `${s.who}: ${s.text}`;
    case "animate": return `animate ${s.id} ${s.kind} ` +
      Object.entries(s.params||{}).map(([k,v])=>`${k}=${v}`).join(" ");
    case "bgm": return s.stop ? "bgm stop" : `bgm ${s.file||""}`;
    case "se": return `se ${s.file||""}`;
    case "choice": return `choice (${(s.options||[]).length})`;
    case "goto": return `goto ${s.target}`;
    default: return s.op;
  }
}

function renderLists(){
  const sc = $("#scenes"); sc.innerHTML = "";
  S.model.order.forEach(id => {
    const li = document.createElement("li");
    li.innerHTML = `<span>${id}</span><span class="grow"></span><span class="n">${S.model.scenes[id].length}</span>`;
    li.style.cssText = "display:flex";
    if (id === S.scene) li.className = "sel";
    li.onclick = () => op({op:"select", scene:id, step:-1});
    sc.appendChild(li);
  });
  renderTimeline(); renderLayers();
  const steps = S.model.scenes[S.scene] || [];
  $("#b-undo").disabled = !S.can_undo; $("#b-redo").disabled = !S.can_redo;
  $("#probs").textContent = (S.problems||[]).join("\n");
  $("#m-count").textContent = S.model.order.length;
  $("#m-scene").textContent = S.play
    ? `▶ ${S.scene}${S.play.done ? " · fin" : ""} — Esc para salir`
    : `${S.scene} · paso ${S.step < 0 ? "—" : S.step + 1}/${steps.length}`;
  $("#m-op").textContent = S.step >= 0 && steps[S.step] ? steps[S.step].op : "";
  $("#m-path").textContent = S.path || "(sin guardar)";
  $("#b-play").classList.toggle("on", !!S.play);
}

/* ---------- capas del escenario ---------- */
function selectLayer(id){
  SEL = SEL === id ? null : id;
  renderLayers(); markSelection();
}
function markSelection(){
  document.querySelectorAll("#stage .layer").forEach(
    el => el.classList.toggle("sel", el.dataset.id === SEL));
  $("#m-sel").textContent = SEL ? `⬚ ${SEL}` : "";
}
function renderLayers(){
  const ul = $("#layers"); ul.innerHTML = "";
  const rows = SG ? VNS.outlineRows(SG.layers) : [];
  if (SEL && !rows.some(r => r.id === SEL)) SEL = null;    // ya no está en escena
  rows.forEach(r => {
    const li = document.createElement("li");
    li.innerHTML = `<span class="chip" style="background:${r.color}"></span>` +
      `<span>${r.name}</span><span class="grow"></span>` +
      `<span class="n">${r.sprite ? "🖼" : "●"} z${r.z}</span>`;
    if (r.id === SEL) li.className = "sel";
    li.title = "click: seleccionar · doble click: ir al paso que la muestra";
    li.onclick = () => selectLayer(r.id);
    li.ondblclick = () => {
      const i = VNS.showStepIndex(S.model.scenes[S.scene] || [], r.id, S.step);
      if (i >= 0) op({op:"select", scene:S.scene, step:i});
    };
    ul.appendChild(li);
  });
  $("#m-layers").textContent = rows.length || "";
}

/* ---------- timeline: los pasos como clips en pistas ---------- */
const TLV = { cw: 118, lh: 22, gap: 2, ruler: 18 };
try { TLV.cw = parseInt(localStorage.getItem("vnscw"), 10) || TLV.cw; } catch (e) {}
const trackX = e => {
  const r = $("#tlbody .tl-track").getBoundingClientRect();
  return e.clientX - r.left + $("#tlbody .tl-track").scrollLeft;
};

function renderTimeline(){
  const steps = S.model.scenes[S.scene] || [];
  const keep = $("#tlbody .tl-track"), sx = keep ? keep.scrollLeft : 0;
  const lab = VNS.LANES.map(l => `<div>${l.key}</div>`).join("");
  const H = TLV.ruler + VNS.LANES.length * TLV.lh;
  $("#tlbody").innerHTML =
    `<div class="tl-labels">${lab}</div>` +
    `<div class="tl-track"><div class="tl-inner" style="height:${H}px;` +
    `width:${Math.max(steps.length + 1, 8) * TLV.cw}px"></div></div>`;
  const inner = $("#tlbody .tl-inner");

  const ruler = document.createElement("div");
  ruler.className = "tl-ruler"; ruler.style.width = "100%";
  steps.forEach((_, i) => {
    const t = document.createElement("div");
    t.className = "tl-tick"; t.style.left = (i * TLV.cw) + "px";
    t.style.width = TLV.cw + "px"; t.textContent = i + 1;
    ruler.appendChild(t);
  });
  inner.appendChild(ruler);

  steps.forEach((st, i) => {
    const r = VNS.clipRect(st, i, TLV), c = document.createElement("div");
    c.className = "clip" + (i === S.step ? " sel" : "");
    c.dataset.i = i;
    Object.assign(c.style, {left: r.x + "px", top: (TLV.ruler + r.y) + "px",
                            width: r.w + "px", height: r.h + "px",
                            background: VNS.LANES[r.lane].color});
    c.textContent = stepText(st); c.title = stepText(st);
    inner.appendChild(c);
  });

  if (S.step >= 0) {
    const ph = document.createElement("div");
    ph.className = "playhead"; ph.style.left = (S.step * TLV.cw) + "px";
    inner.appendChild(ph);
  }
  $("#tlbody .tl-track").scrollLeft = sx;
}

/* arrastrar un clip lo reordena; arrastrar la regla mueve el playhead */
$("#tlbody").addEventListener("pointerdown", e => {
  const steps = S.model.scenes[S.scene] || [];
  const c = e.target.closest(".clip");
  if (c) {
    const i = +c.dataset.i, x0 = trackX(e), left0 = i * TLV.cw;
    let moved = false;
    c.setPointerCapture(e.pointerId); c.classList.add("drag");
    const move = ev => { moved = true; c.style.left = (left0 + trackX(ev) - x0) + "px"; };
    const up = async ev => {
      c.classList.remove("drag");
      c.removeEventListener("pointermove", move); c.removeEventListener("pointerup", up);
      const to = VNS.dropIndex(left0 + trackX(ev) - x0, TLV, steps.length);
      await op({op:"select", scene:S.scene, step:i});
      if (moved && to !== i) op({op:"move_step_to", to});
    };
    c.addEventListener("pointermove", move); c.addEventListener("pointerup", up);
    e.preventDefault(); return;
  }
  if (!steps.length) return;
  const seek = ev => {                        // scrub: elegí paso arrastrando
    const i = VNS.dropIndex(trackX(ev), TLV, steps.length);
    if (i !== S.step) op({op:"select", scene:S.scene, step:i});
  };
  const t = $("#tlbody .tl-track");
  t.setPointerCapture(e.pointerId);
  const up = () => { t.removeEventListener("pointermove", seek); t.removeEventListener("pointerup", up); };
  t.addEventListener("pointermove", seek); t.addEventListener("pointerup", up);
  seek(e);
});
$("#tlbody").addEventListener("dblclick", () => $("#b-probar").click());
$("#tlbody").addEventListener("wheel", e => {   // Ctrl+rueda: zoom del timeline
  if (!e.ctrlKey) return;
  e.preventDefault();
  TLV.cw = Math.max(48, Math.min(260, TLV.cw - Math.sign(e.deltaY) * 12));
  try { localStorage.setItem("vnscw", TLV.cw); } catch (err) {}
  renderTimeline();
}, {passive:false});

function renderStage(){
  const st = $("#stage"); st.innerHTML = "";
  $("#stagewrap").style.background = VNS.bgStyle(SG.bg);
  for (const l of SG.layers) {
    const d = document.createElement("div");
    d.className = "layer"; d.dataset.id = l.id;
    Object.assign(d.style, VNS.layerStyle(l, SG));
    if (l.url) d.innerHTML = `<img src="${l.url}" alt="">`;
    else d.innerHTML = `<div class="ph" style="background:${l.color}">${(l.name||l.id)[0]||"?"}</div>`;
    st.appendChild(d);
  }
  const say = SG.say;
  $("#dbox").hidden = !say;
  if (say){ $("#who").textContent = say.name || ""; $("#who").style.color = say.color;
            $("#text").textContent = say.text; }
  const ch = $("#choices"); ch.hidden = !(SG.choices && SG.choices.length);
  ch.innerHTML = "";
  (SG.choices||[]).forEach((o, i) => {
    const b = document.createElement("button"); b.textContent = o.label;
    if (S.play) b.onclick = () => op({op:"play_choose", i});
    ch.appendChild(b);
  });
  $("#m-bgm").textContent = SG.bgm ? `♪ ${SG.bgm}` : "";
  $("#vptag").textContent = S.play ? "PLAY" : "";
  markSelection();
  layoutStage();
}

/* ---------- inspector ---------- */
function field(label, el){
  const r = document.createElement("div"); r.className = "row";
  const l = document.createElement("label"); l.textContent = label;
  r.append(l, el); return r;
}
function input(v){ const e = document.createElement("input"); e.value = v ?? ""; return e; }
function select(v, opts){
  const e = document.createElement("select");
  opts.forEach(o => { const x = document.createElement("option"); x.value = x.textContent = o;
                      if (o === v) x.selected = true; e.appendChild(x); });
  return e;
}
function upload(req, accept){
  const f = document.createElement("input");
  f.type = "file"; f.accept = accept || "image/*";
  f.onchange = () => {
    const file = f.files[0]; if (!file) return;
    const rd = new FileReader();
    rd.onload = () => op(Object.assign({name: file.name,
                                        data: rd.result.split(",")[1]}, req));  // sin data: URI
    rd.readAsDataURL(file);
  };
  f.click();
}
/* selector de asset + botón "…" para traer uno del sistema */
function picker(cur, list, onpick, apply, accept){
  const sel = select(cur, [""].concat(list.includes(cur) || !cur ? list : list.concat(cur)));
  sel.querySelector('option[value=""]').textContent = "(ninguno)";
  sel.onchange = () => onpick(sel.value);
  const b = document.createElement("button");
  b.textContent = "…"; b.title = "elegir un archivo de tu compu";
  b.style.flex = "0 0 auto";
  b.onclick = () => upload({op:"upload", apply}, accept);
  const w = document.createElement("div");
  w.style.cssText = "display:flex;gap:4px;flex:1"; w.append(sel, b);
  return w;
}
/* editar el personaje del paso: id (renombra y reapunta), nombre y color */
function charFields(cid){
  const c = S.model.characters[cid]; if (!c) return null;
  const w = document.createElement("div");
  const nid = input(cid), nm = input(c.name), col = input(c.color || "#7cc4ff");
  col.type = "color"; col.style.padding = "0";
  const b = document.createElement("button"); b.textContent = "Aplicar personaje";
  b.onclick = async () => {
    const id = nid.value.trim() || cid;
    if (id !== cid) await op({op:"rename_char", old: cid, new: id});
    op({op:"set_char", id, name: nm.value, color: col.value});
  };
  w.append(field("id", nid), field("nombre", nm), field("color", col), b);
  return w;
}

function renderProps(){
  const box = $("#props"); box.innerHTML = "";
  const steps = S.model.scenes[S.scene] || [];
  if (!(S.step >= 0 && S.step < steps.length)) { box.innerHTML = '<div class="hint">(elegí un paso en el timeline)</div>'; return; }
  const s = steps[S.step], chars = Object.keys(S.model.characters), f = {};
  const add = (k, label, el) => { f[k] = el; box.appendChild(field(label, el)); };

  if (s.op === "bg") {
    const p = s.spec||{};
    add("bg","fondo", input(p.kind==="grad" ? `grad:${p.a},${p.b}` : p.kind==="solid" ? p.color : (p.file||"")));
    box.appendChild(field("imagen", picker(p.file || "", ASSETS,
      v => op({op:"set_props", props:{bg: v || "#000000"}}), "bg", "image/*")));
    box.insertAdjacentHTML("beforeend", '<div class="hint">grad:#a,#b · #rrggbb · archivo.png</div>');
  } else if (s.op === "show" || s.op === "hide") {
    add("id","personaje", select(s.id, chars));
    const cf = charFields(s.id); if (cf) box.appendChild(cf);
    if (s.op === "show") {
      add("pos","pos", select(s.pos||"center", ["left","center","right"]));
      add("z","z", input(s.z)); add("zoom","zoom %", input(s.zoom));
      add("opacity","opac %", input(s.opacity)); add("tint","tinte", input(s.tint));
      /* el sprite es del PERSONAJE (no del paso): se aplica al instante */
      const cur = (S.model.characters[s.id] || {}).sprite || "";
      const sel = select(cur, [""].concat(ASSETS));
      sel.querySelector('option[value=""]').textContent = "(placeholder)";
      sel.onchange = () => op({op:"set_sprite", id: s.id, file: sel.value});
      const pick = document.createElement("button");           // elegir del sistema
      pick.textContent = "…"; pick.title = "elegir una imagen de tu compu";
      pick.style.flex = "0 0 auto";
      pick.onclick = () => upload({op:"upload_sprite", id: s.id});
      const wrap = document.createElement("div");
      wrap.style.cssText = "display:flex;gap:4px;flex:1";
      wrap.append(sel, pick);
      box.appendChild(field("sprite", wrap));
      const zf = document.createElement("div");
      zf.style.cssText = "display:flex;gap:4px;flex:1";
      [["▲ al frente", true], ["▼ al fondo", false]].forEach(([t, front]) => {
        const b = document.createElement("button"); b.textContent = t;
        b.onclick = () => op({op:"set_z", id: s.id, front}); zf.appendChild(b);
      });
      box.appendChild(field("orden", zf));
      box.insertAdjacentHTML("beforeend",
        '<div class="hint">la imagen elegida se copia junto al .vn · arrastrá el sprite en el escenario</div>');
    }
  } else if (s.op === "say") {
    add("who","quién", select(s.who, chars)); add("text","texto", input(s.text));
    const cf = charFields(s.who); if (cf) box.appendChild(cf);
  } else if (s.op === "animate") {
    add("id","personaje", select(s.id, chars.filter(c=>c!=="narrator")));
    add("kind","tipo", select(s.kind, ["linear","accel","decel","move","wave","waveonce","jump","jumponce","fall","vibrate"]));
    add("params","params", input(Object.entries(s.params||{}).map(([k,v])=>`${k}=${v}`).join(" ")));
  } else if (s.op === "bgm" || s.op === "se") {
    box.appendChild(field("archivo", picker(s.file || "", AUDIO,
      v => op({op:"set_props", props:{file: v}}), "file", "audio/*")));
    if (s.op === "bgm") { const c = document.createElement("input"); c.type="checkbox"; c.checked=!!s.stop;
                          c.style.width="auto"; add("stop","detener", c); }
  } else if (s.op === "goto") {
    add("target","a", select(s.target, S.model.order));
  } else if (s.op === "choice") {
    const t = document.createElement("textarea"); t.rows = 4;
    t.value = (s.options||[]).map(o=>`${o.label} -> ${o.target}`).join("\n");
    add("options","opciones", t);
    box.insertAdjacentHTML("beforeend", '<div class="hint">etiqueta -&gt; escena (una por línea)</div>');
  } else { box.innerHTML = '<div class="hint">(sin propiedades)</div>'; return; }

  const b = document.createElement("button"); b.textContent = "Aplicar";
  b.style.marginTop = "8px";
  b.onclick = () => {
    const props = {};
    for (const [k, el] of Object.entries(f)) {
      let v = el.type === "checkbox" ? el.checked : el.value;
      if (k === "options") v = v.split("\n").filter(x=>x.includes("->"))
            .map(x => ({label:x.split("->")[0].trim(), target:x.split("->")[1].trim()}));
      else if (k === "params") { const o={}; v.split(/\s+/).filter(Boolean).forEach(kv=>{
            const [a,bb]=kv.split("="); const n=Number(bb); o[a]= isNaN(n)?bb:n; }); v=o; }
      else if (["z","zoom","opacity","x","y"].includes(k)) { if (v==="") continue; v = parseInt(v,10); }
      props[k] = v;
    }
    op({op:"set_props", props});
  };
  box.appendChild(b);
}

async function refresh(){
  SG = S.play ? S.play : await api.stage(S.scene, S.step);
  const as = await api.assets(); ASSETS = as.assets; AUDIO = as.audio;
  renderLists(); renderStage(); renderProps();
}

/* ---------- toolbar ---------- */
const ask = (msg, def="") => { const v = prompt(msg, def); return v && v.trim() ? v.trim() : null; };
const stepCount = () => (S.model.scenes[S.scene] || []).length;
$("#b-new").onclick = () => { if (confirm("¿Descartar el proyecto actual?")) op({op:"new_project"}); };
$("#b-open").onclick = () => { const p = ask("ruta del .vn a abrir:", S.path || ""); if (p) op({op:"open_project", path:p}); };
$("#b-play").onclick = () => op(S.play ? {op:"play_stop"} : {op:"play", scene:S.scene});
$("#b-undo").onclick = () => op({op:"undo"});
$("#b-redo").onclick = () => op({op:"redo"});
$("#b-validate").onclick = () => op({op:"validate"});
$("#b-save").onclick = () => op({op:"save"});
$("#b-export").onclick = () => op({op:"export"});
$("#b-char").onclick = () => { const id = ask("id del personaje:"); if(!id) return;
  op({op:"add_char", id, name: ask("nombre visible:", id) || id, color: ask("color #hex:", "#7cc4ff") || "#7cc4ff"}); };
$("#b-scene-add").onclick = () => { const n = ask("id de la escena nueva:"); if(n) op({op:"add_scene", name:n}); };
$("#b-scene-dup").onclick = () => op({op:"dup_scene"});
$("#b-scene-ren").onclick = () => { const n = ask("nuevo id:", S.scene); if(n) op({op:"rename_scene", name:n}); };
$("#b-scene-up").onclick = () => op({op:"move_scene", delta:-1});
$("#b-scene-dn").onclick = () => op({op:"move_scene", delta:1});
$("#b-step-add").onclick = () => op({op:"add_step", kind: $("#newop").value});
$("#b-step-dup").onclick = () => op({op:"dup_step"});
$("#b-step-up").onclick = () => op({op:"move_step", delta:-1});
$("#b-step-dn").onclick = () => op({op:"move_step", delta:1});
$("#b-step-del").onclick = () => op({op:"del_step"});
$("#b-prev").onclick = () => op({op:"select", scene:S.scene, step: Math.max(-1, S.step - 1)});
$("#b-next").onclick = () => op({op:"select", scene:S.scene, step: Math.min(stepCount() - 1, S.step + 1)});
/* preview AUTORITATIVO: lo renderiza Python con el engine real y llega como APNG */
$("#b-probar").onclick = () => {
  const a = $("#anim");
  a.src = `/api/anim?scene=${encodeURIComponent(S.scene)}&step=${S.step}&ms=1200&_=${Date.now()}`;
  a.hidden = false;
};
$("#anim").onclick = () => { $("#anim").hidden = true; $("#anim").removeAttribute("src"); };

addEventListener("keydown", e => {
  const t = e.target.tagName;
  if (t === "INPUT" || t === "TEXTAREA" || t === "SELECT") return;
  if (e.key === "Escape" && S.play) { op({op:"play_stop"}); return; }
  if (S.play && (e.key === " " || e.key === "Enter") && !(SG.choices||[]).length && !SG.done) {
    e.preventDefault(); op({op:"play_advance"}); return; }
  if (e.ctrlKey && e.key === "z") { e.preventDefault(); op({op:"undo"}); }
  else if (e.ctrlKey && (e.key === "y" || (e.shiftKey && e.key === "Z"))) { e.preventDefault(); op({op:"redo"}); }
  else if (e.ctrlKey && e.key === "s") { e.preventDefault(); op({op:"save"}); }
  else if (e.key === "ArrowLeft") { e.preventDefault(); $("#b-prev").click(); }
  else if (e.key === "ArrowRight") { e.preventDefault(); $("#b-next").click(); }
  else if (e.key === " ") { e.preventDefault(); $("#b-play").click(); }
});

/* ---------- arrastrar sprites: 60fps en el cliente, sync al soltar ---------- */
let drag = null;
const stRect = () => $("#stagewrap").getBoundingClientRect();

function showGuides(gx, gy){
  const v = $("#gv"), h = $("#gh");
  v.hidden = gx === null; h.hidden = gy === null;
  if (gx !== null) v.style.left = (gx / SG.w * 100) + "%";
  if (gy !== null) h.style.top  = (gy / SG.h * 100) + "%";
}

$("#stage").addEventListener("pointerdown", e => {
  if (S.play) {                            // en Play el click avanza el diálogo
    if (!SG.done && !(SG.choices||[]).length) op({op:"play_advance"});
    return;
  }
  const el = e.target.closest(".layer"); if (!el || !SG) return;
  const l = SG.layers.find(x => x.id === el.dataset.id); if (!l) return;
  if (SEL !== l.id) { SEL = l.id; renderLayers(); markSelection(); }
  const p = VNS.stageXY(e.clientX, e.clientY, stRect(), SG);
  const zoom = (l.zoom == null ? 100 : l.zoom) / 100;
  const left = SG.w/2 + l.x - l.w*zoom/2, top = SG.h - l.h*zoom + l.y;
  drag = { l, el, gdx: p.x - left, gdy: p.y - top };
  el.setPointerCapture(e.pointerId);
  e.preventDefault();
});

$("#stage").addEventListener("pointermove", e => {
  if (!drag) return;
  const p = VNS.stageXY(e.clientX, e.clientY, stRect(), SG);
  let d = VNS.dragTo(drag.l, SG, drag.gdx, drag.gdy, p.x, p.y);
  let gx = null, gy = null;
  if (!e.shiftKey) {                       // Shift = libre, sin imán
    const t = VNS.snapTargets(SG.layers, drag.l.id);
    const sx = VNS.snap(d.x, t.xs, 12), sy = VNS.snap(d.y, t.ys, 12);
    d = { x: sx.v, y: sy.v };
    if (sx.hit) gx = SG.w/2 + d.x;
    if (sy.hit) gy = SG.h + d.y;
  }
  drag.l.x = d.x; drag.l.y = d.y;
  Object.assign(drag.el.style, VNS.layerStyle(drag.l, SG));
  showGuides(gx, gy);
});

const endDrag = async () => {
  if (!drag) return;
  const l = drag.l; drag = null; showGuides(null, null);
  await op({op:"set_layer_pos", id: l.id, x: Math.round(l.x), y: Math.round(l.y)});
};
$("#stage").addEventListener("pointerup", endDrag);
$("#stage").addEventListener("pointercancel", endDrag);

(async () => {
  S = await api.model();
  $("#newop").innerHTML = S.step_ops.map(o => `<option>${o}</option>`).join("");
  $("#newop").value = "say";
  await refresh();
})();
