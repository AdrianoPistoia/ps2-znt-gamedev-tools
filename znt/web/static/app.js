/* VN Studio (web) — comportamiento del editor.
 * El servidor Python es la fuente de verdad: acá sólo pintamos su estado y
 * mandamos ops. La lógica pura (layout, snap, geometría) vive en logic.js. */
"use strict";
const $ = s => document.querySelector(s);
const API = 4;             // tiene que coincidir con znt/web/server.py
let S = null;              // estado del servidor
let SG = null;             // stage actual (layout que manda Python)
let ASSETS = [], AUDIO = [];
let SEL = null;            // capa seleccionada (sólo del cliente)
let SELS = [], ANCHOR = -1; // selección múltiple de pasos (timeline) y ancla del Shift
let CLIP = [];             // portapapeles de pasos (JSON), vive entre escenas
let GUIDE = "off", SHOWDLG = true;
try { GUIDE = localStorage.getItem("vnsguide") || "off";
      SHOWDLG = localStorage.getItem("vnsdlg") !== "0"; } catch (e) {}

const api = {
  model: () => fetch("/api/model").then(r => r.json()),
  op: o => fetch("/api/op", {method:"POST", headers:{"Content-Type":"application/json"},
                             body: JSON.stringify(o)}).then(r => r.json()),
  stage: (sc, st) => fetch(`/api/stage?scene=${encodeURIComponent(sc)}&step=${st}`).then(r => r.json()),
  assets: () => fetch("/api/assets").then(r => r.json()),
  browse: (p, kind) => fetch(`/api/browse?path=${encodeURIComponent(p||"")}&kind=${kind}`).then(r => r.json()),
};
let toastT = null;
function toast(msg, bad){
  const t = $("#toast");
  t.textContent = msg; t.classList.toggle("bad", !!bad); t.hidden = false;
  clearTimeout(toastT); toastT = setTimeout(() => { t.hidden = true; }, bad ? 7000 : 3000);
}
window.__vns = { busy: 0 };                        // ops en vuelo (lo mira el QA)
async function op(o){
  window.__vns.busy++;
  try {
    let res = null;
    try { res = await api.op(o); }
    catch (e) { res = { error: String(e) }; }       // el server se cayó / red
    const m = VNS.mergeState(S, res);
    S = m.state;
    if (m.error) toast(m.error, true);
    else if (res && res.notice) toast(res.notice);
    await refresh();
  } finally { window.__vns.busy--; }
}

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
    if (id === VNS.playCursor(S).scene) li.className = "sel";
    li.onclick = () => op(S.play ? {op:"play", scene:id, step:0} : {op:"select", scene:id, step:0});
    sc.appendChild(li);
  });
  renderTimeline(); renderLayers();
  const steps = S.model.scenes[S.scene] || [];
  $("#b-undo").disabled = !S.can_undo; $("#b-redo").disabled = !S.can_redo;
  $("#probs").textContent = (S.problems||[]).concat((SG && SG.warnings) || []).join("\n");
  $("#m-count").textContent = S.model.order.length;
  $("#m-scene").textContent = S.play
    ? `▶ ${S.play.scene} · paso ${S.play.step + 1}${S.play.done ? " · fin" : ""} — Esc para salir`
    : `${S.scene} · paso ${S.step < 0 ? "—" : S.step + 1}/${steps.length}`;
  $("#m-op").textContent = S.step >= 0 && steps[S.step] ? steps[S.step].op : "";
  $("#m-path").textContent = S.path || "(sin guardar)";
  $("#m-path").classList.toggle("dirty", !!S.dirty);
  $("#m-path").title = S.dirty ? "hay cambios sin guardar (Ctrl+S)" : "";
  document.title = (S.dirty ? "● " : "") + "VN Studio";
  renderChars(); renderQuickWho();
  $("#b-play").classList.toggle("on", !!S.play);
}

/* ---------- personajes del proyecto (roster) ---------- */
function renderChars(){
  const ul = $("#chars"); ul.innerHTML = "";
  const ids = Object.keys(S.model.characters).filter(c => c !== "narrator");
  ids.forEach(id => {
    const c = S.model.characters[id], li = document.createElement("li");
    li.innerHTML = `<span class="chip" style="background:${c.color || "#888"}"></span>` +
      `<span>${c.name || id}</span><span class="n">${id}</span><span class="grow"></span>` +
      `<span class="x" title="borrar personaje">🗑</span>`;
    li.title = "doble click: renombrar id";
    li.ondblclick = async () => {
      const n = await askOne("Renombrar personaje", "nuevo id", id);
      if (n && n !== id) op({op:"rename_char", old:id, new:n});
    };
    li.querySelector(".x").onclick = async e => {
      e.stopPropagation();
      if (await ask("Borrar personaje", [], `¿Borrar a "${c.name || id}"? Si está en algún paso, no se deja.`))
        op({op:"del_char", id});
    };
    ul.appendChild(li);
  });
  $("#m-chars").textContent = ids.length || "";
}

/* ---------- audio (sólo en Play, y ▶ para escuchar en edición) ---------- */
const assetUrl = f => "/api/asset?f=" + encodeURIComponent(f);
let seSeq = null;
function playAudio(el, f){
  el.setAttribute("src", assetUrl(f)); el.load();
  el.play().catch(() => {});                          // sin gesto o archivo inválido: silencio
}
function syncAudio(){
  const bgm = $("#bgm"), sfx = $("#sfx");
  if (!S.play) { bgm.pause(); bgm.removeAttribute("src"); seSeq = null; return; }
  const want = S.play.bgm ? assetUrl(S.play.bgm) : null;
  if (!want) { bgm.pause(); bgm.removeAttribute("src"); }
  else if (bgm.getAttribute("src") !== want) playAudio(bgm, S.play.bgm);
  if (seSeq === null) seSeq = S.play.se_seq;         // al entrar no se dispara lo viejo
  else if (S.play.se_seq !== seSeq) { seSeq = S.play.se_seq; if (S.play.se) playAudio(sfx, S.play.se); }
}

/* ---------- efecto de tipeo (sólo en Play) ---------- */
let CPS = 40;                                       // caracteres por segundo (0 = sin efecto)
try { const v = localStorage.getItem("vnscps"); if (v !== null) CPS = +v; } catch (e) {}
let typing = null;                                  // {text, t0, raf}
function typeText(text, animate){
  if (typing) cancelAnimationFrame(typing.raf);
  typing = null;
  const el = $("#text");
  if (!animate || !CPS) { el.textContent = text; return; }
  const t0 = performance.now();
  const step = () => {
    const n = VNS.typedChars(text, performance.now() - t0, CPS);
    el.textContent = text.slice(0, n);
    if (n < text.length) typing.raf = requestAnimationFrame(step); else typing = null;
  };
  typing = { text, t0, raf: 0 }; step();
}
const typingDone = () => !typing;
function finishTyping(){                            // click mientras tipea: mostrar todo
  if (!typing) return false;
  cancelAnimationFrame(typing.raf); $("#text").textContent = typing.text; typing = null; return true;
}
function cycleCps(){
  CPS = ({0: 20, 20: 40, 40: 80, 80: 0})[CPS] ?? 40;
  try { localStorage.setItem("vnscps", CPS); } catch (e) {}
  $("#b-cps").textContent = "⌨ " + (CPS ? CPS + " cps" : "sin tipeo");
}

/* ---------- capas del escenario ---------- */
function selectLayer(id){
  SEL = SEL === id ? null : id;
  renderLayers(); markSelection();
}
function markSelection(){
  document.querySelectorAll("#stage .layer").forEach(
    el => el.classList.toggle("sel", el.dataset.id === SEL));
  const l = SG && SEL ? SG.layers.find(x => x.id === SEL) : null;
  const f = $("#frame"); f.hidden = !l || !!S.play;
  if (l && !f.hidden) {
    const st = VNS.layerStyle(l, SG);
    Object.assign(f.style, {left: st.left, top: st.top, width: st.width, height: st.height});
    $("#flabel").textContent =
      `${l.name}  x${Math.round(l.x)} y${Math.round(l.y)}  ${l.zoom == null ? 100 : l.zoom}%`;
  }
  $("#m-sel").textContent = SEL ? `⬚ ${SEL}` : "";
}

/* guías: centro / tercios / zona segura */
function renderGuides(){
  const g = VNS.guides(GUIDE), box = $("#guides"); box.innerHTML = "";
  g.xs.forEach(x => box.insertAdjacentHTML("beforeend",
    `<div class="g" style="left:${x*100}%;top:0;bottom:0;width:1px"></div>`));
  g.ys.forEach(y => box.insertAdjacentHTML("beforeend",
    `<div class="g" style="top:${y*100}%;left:0;right:0;height:1px"></div>`));
  if (g.rect) box.insertAdjacentHTML("beforeend",
    `<div class="safe" style="left:${g.rect.x*100}%;top:${g.rect.y*100}%;` +
    `width:${g.rect.w*100}%;height:${g.rect.h*100}%"></div>`);
  $("#b-guides").classList.toggle("on", GUIDE !== "off");
  $("#b-guides").textContent = "⊞ " + (GUIDE === "off" ? "guías" : GUIDE);
}
function cycleGuides(){
  GUIDE = VNS.nextGuide(GUIDE);
  try { localStorage.setItem("vnsguide", GUIDE); } catch (e) {}
  renderGuides();
}
$("#b-guides").onclick = cycleGuides;
$("#b-overlay").onclick = () => {                 // ojo: apaga los overlays para trabajar
  SHOWDLG = !SHOWDLG;
  try { localStorage.setItem("vnsdlg", SHOWDLG ? "1" : "0"); } catch (e) {}
  renderStage();
};

/* handles: arrastrar una esquina cambia el zoom de la capa */
$("#frame").addEventListener("pointerdown", e => {
  const h = e.target.closest(".hnd"); if (!h || !SEL) return;
  const l = SG.layers.find(x => x.id === SEL); if (!l) return;
  const dir = +h.dataset.h, x0 = e.clientX, z0 = l.zoom == null ? 100 : l.zoom;
  const scale = SG.w / $("#stagewrap").getBoundingClientRect().width;   // px de pantalla -> stage
  h.setPointerCapture(e.pointerId);
  const move = ev => {
    l.zoom = VNS.resizeZoom({w: l.w, h: l.h, zoom: z0}, dir, (ev.clientX - x0) * scale);
    const el = document.querySelector(`#stage .layer[data-id="${l.id}"]`);
    if (el) Object.assign(el.style, VNS.layerStyle(l, SG));
    markSelection();
  };
  const up = () => {
    h.removeEventListener("pointermove", move); h.removeEventListener("pointerup", up);
    op({op:"set_layer", id: l.id, props:{zoom: l.zoom}});
  };
  h.addEventListener("pointermove", move); h.addEventListener("pointerup", up);
  e.preventDefault(); e.stopPropagation();
});
function renderLayers(){
  const ul = $("#layers"); ul.innerHTML = "";
  const rows = SG ? VNS.outlineRows(SG.layers) : [];
  if (SEL && !rows.some(r => r.id === SEL)) SEL = null;    // ya no está en escena
  rows.forEach(r => {
    const li = document.createElement("li");
    li.innerHTML = `<span class="chip" style="background:${r.color}"></span>` +
      `<span>${r.name}${r.expr ? ` <span class="n">· ${r.expr}</span>` : ""}</span><span class="grow"></span>` +
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
  const cur = VNS.playCursor(S);
  const steps = S.model.scenes[cur.scene] || [];
  document.body.classList.toggle("playing", cur.playing);
  if (!SELS.includes(cur.step)) { SELS = cur.step >= 0 ? [cur.step] : []; ANCHOR = cur.step; }
  const keep = $("#tlbody .tl-track"), sx = keep ? keep.scrollLeft : 0;
  const lab = VNS.LANES.map(l => `<div>${l.key}</div>`).join("");
  const H = TLV.ruler + VNS.LANES.length * TLV.lh;
  $("#tlbody").innerHTML =
    `<div class="tl-labels">${lab}</div>` +
    `<div class="tl-track"><div class="tl-inner" style="height:${H}px;` +
    `width:${Math.max(steps.length + 1, 8) * TLV.cw}px"></div></div>`;
  const inner = $("#tlbody .tl-inner");

  VNS.LANES.forEach((_, i) => {
    const ln = document.createElement("div");
    ln.className = "lane" + (i % 2 ? " odd" : "");
    ln.style.top = (TLV.ruler + i * TLV.lh) + "px"; ln.style.height = TLV.lh + "px";
    inner.appendChild(ln);
  });
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
    c.className = "clip" + (cur.playing ? (i === cur.step ? " playing" : "")
                                        : (SELS.includes(i) ? " sel" : ""));
    c.dataset.i = i;
    Object.assign(c.style, {left: r.x + "px", top: (TLV.ruler + r.y) + "px",
                            width: r.w + "px", height: r.h + "px",
                            background: VNS.LANES[r.lane].color});
    c.textContent = stepText(st); c.title = stepText(st);
    inner.appendChild(c);
  });

  if (cur.step >= 0) {
    const ph = document.createElement("div");
    ph.className = "playhead"; ph.style.left = (cur.step * TLV.cw) + "px";
    inner.appendChild(ph);
    if (cur.playing) {                        // que el paso en curso quede a la vista
      const t = $("#tlbody .tl-track"), x = cur.step * TLV.cw;
      if (x < t.scrollLeft || x + TLV.cw > t.scrollLeft + t.clientWidth) t.scrollLeft = x - 40;
    }
  }
  $("#tlbody .tl-track").scrollLeft = sx;
}

/* arrastrar un clip lo reordena; arrastrar la regla mueve el playhead */
$("#tlbody").addEventListener("pointerdown", e => {
  if (S.play) {                               // en Play: saltar a ese paso
    const c = e.target.closest(".clip");
    const n = (S.model.scenes[S.play.scene] || []).length;
    const i = c ? +c.dataset.i : VNS.dropIndex(trackX(e), TLV, n);
    if (n) op({op:"play", scene:S.play.scene, step:i});
    return;
  }
  const steps = S.model.scenes[S.scene] || [];
  const c = e.target.closest(".clip");
  if (c && (e.shiftKey || e.ctrlKey || e.metaKey)) {
    const r = VNS.clickSelect(SELS, ANCHOR, +c.dataset.i, {shift: e.shiftKey, ctrl: e.ctrlKey || e.metaKey});
    SELS = r.sel; ANCHOR = r.anchor;
    op({op:"select", scene:S.scene, step:+c.dataset.i});
    e.preventDefault(); return;
  }
  if (c) {
    const i = +c.dataset.i, x0 = trackX(e), left0 = i * TLV.cw;
    SELS = [i]; ANCHOR = i;
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
  const ov = VNS.stageOverlay({play: !!S.play, choices: SG.choices, say: SG.say,
                               showDialog: SHOWDLG});
  const say = SG.say;
  $("#dbox").hidden = !(ov.dialog && say);
  if (say){ $("#who").textContent = say.name || ""; $("#who").style.color = say.color;
            typeText(say.text, !!S.play); }
  const ch = $("#choices");
  ch.hidden = !ov.choices;
  ch.className = ov.interactive ? "" : "edit";
  ch.style.background = ov.scrim ? `rgba(0,0,0,${ov.scrim})` : "transparent";
  ch.innerHTML = ov.label ? `<div class="tag">${ov.label}</div>` : "";
  (SG.choices||[]).forEach((o, i) => {
    const b = document.createElement("button"); b.textContent = o.label;
    if (ov.interactive) b.onclick = () => op({op:"play_choose", i});
    ch.appendChild(b);
  });
  $("#b-overlay").classList.toggle("on", SHOWDLG);
  $("#b-adv").hidden = $("#b-exit").hidden = $("#b-cps").hidden = !S.play;
  syncAudio();
  $("#m-bgm").textContent = SG.bgm ? `♪ ${SG.bgm}` : "";
  $("#vptag").textContent = S.play
    ? (SG.done ? "▶ PLAY · fin" : "▶ PLAY · click o Espacio = siguiente paso") : "";
  markSelection(); renderGuides();
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
    if (file.size > 12 << 20) return toast(`${file.name} pesa demasiado (máx 12 MB)`, true);
    toast(`subiendo ${file.name}…`);
    const rd = new FileReader();
    rd.onload = () => op(Object.assign({name: file.name,
                                        data: rd.result.split(",")[1]}, req));  // sin data: URI
    rd.onerror = () => toast("no se pudo leer el archivo: " + file.name, true);
    rd.readAsDataURL(file);
  };
  f.click();
}
/* ---------- explorador de archivos del disco ----------
   Estándar: TODO campo que apunte a un archivo lleva su botón 📁. */
let brwDir = null;
async function browseTo(dir, kind, sel){
  const r = await api.browse(dir, kind);
  if (r.error) toast(r.error, true);
  brwDir = r.path;
  $("#brw-path").value = sel || r.pick ? VNS.joinPath(r.path, sel || r.pick) : r.path;
  const cr = $("#brw-crumbs"); cr.innerHTML = "";
  VNS.crumbs(r.path).forEach(c => {
    const b = document.createElement("button"); b.type = "button"; b.textContent = c.name;
    b.onclick = () => browseTo(c.path, kind);
    cr.append(b);
  });
  const ul = $("#brw-list"); ul.innerHTML = "";
  r.dirs.forEach(d => {
    const li = document.createElement("li"); li.className = "dir"; li.textContent = "📁 " + d;
    li.onclick = () => browseTo(VNS.joinPath(r.path, d), kind);
    ul.append(li);
  });
  r.files.forEach(f => {
    const li = document.createElement("li"); li.textContent = "   " + f;
    if (f === (sel || r.pick)) li.className = "sel";
    li.onclick = () => {
      ul.querySelectorAll("li").forEach(x => x.classList.remove("sel"));
      li.classList.add("sel"); $("#brw-path").value = VNS.joinPath(r.path, f);
    };
    li.ondblclick = () => { $("#brw-path").value = VNS.joinPath(r.path, f);
                            $("#brw").close("ok"); };
    ul.append(li);
  });
  $("#brw-up").onclick = () => r.parent && browseTo(r.parent, kind);
  $("#brw-home").onclick = () => browseTo(r.home, kind);
}
/* kind: "vn" | "img" | "audio" | "any". Devuelve la ruta elegida o null. */
function browse(title, kind, start, onUpload){
  const dlg = $("#brw");
  $("#brw-title").textContent = title;
  $("#brw-upload").hidden = !onUpload;
  $("#brw-upload").onclick = () => { dlg.close(""); onUpload(); };
  browseTo(start || brwDir || "", kind);
  dlg.showModal();
  return new Promise(res => dlg.addEventListener("close", () => {
    res(dlg.returnValue === "ok" ? ($("#brw-path").value.trim() || null) : null);
  }, {once:true}));
}
/* botón 📁 para cualquier campo de archivo */
function fileBtn(title, kind, start, onPick, onUpload){
  const b = document.createElement("button");
  b.textContent = "📁"; b.title = "buscar en el disco";
  b.style.flex = "0 0 auto";
  b.onclick = async () => { const p = await browse(title, kind, start, onUpload); if (p) onPick(p); };
  return b;
}

/* selector de asset + botón 📁 (traer del disco) y ⇧ (subir) */
function picker(cur, list, onpick, apply, accept){
  const sel = select(cur, [""].concat(list.includes(cur) || !cur ? list : list.concat(cur)));
  sel.querySelector('option[value=""]').textContent = "(ninguno)";
  sel.onchange = () => onpick(sel.value);
  const kind = accept && accept.startsWith("audio") ? "audio" : "img";
  const b = fileBtn("Elegir archivo", kind, S.path || "",
                    p => op({op:"import_asset", path:p, apply}),
                    () => upload({op:"upload", apply}, accept));
  const w = document.createElement("div");
  w.style.cssText = "display:flex;gap:4px;flex:1"; w.append(sel, b);
  if (kind === "audio") {                            // ▶ escuchar lo elegido
    const pl = document.createElement("button"); pl.textContent = "▶"; pl.title = "escuchar";
    pl.style.flex = "0 0 auto";
    pl.onclick = () => { if (sel.value) playAudio($("#sfx"), sel.value); };
    w.append(pl);
  }
  return w;
}
/* Sección PERSONAJE: el ÚNICO lugar donde se elige y se edita un personaje.
   `assign` cambia a qué personaje apunta el paso; lo demás edita al personaje. */
function charSection(cid, chars, assign, withSprite){
  const sec = sect("Personaje", true);
  const sel = select(cid, chars);
  sel.dataset.role = "char";                        // uno solo por inspector
  sel.onchange = () => assign(sel.value);
  sec.add(field("personaje", sel));
  const c = S.model.characters[cid];
  if (!c) return sec;

  const nm = input(c.name), col = input(c.color || "#7cc4ff");
  col.type = "color"; col.style.padding = "0";
  const apply = () => op({op:"set_char", id: cid, name: nm.value, color: col.value});
  nm.onchange = apply; col.onchange = apply;
  sec.add(field("nombre", nm)); sec.add(field("color", col));

  if (withSprite) {                                 // el sprite es del personaje
    const cur = c.sprite || "";
    const sp = select(cur, [""].concat(ASSETS.includes(cur) || !cur ? ASSETS : ASSETS.concat(cur)));
    sp.querySelector('option[value=""]').textContent = "(placeholder)";
    sp.onchange = () => op({op:"set_sprite", id: cid, file: sp.value});
    const b = fileBtn("Elegir imagen del personaje", "img", S.base || "",
                      pa => op({op:"import_asset", path:pa, id:cid}),
                      () => upload({op:"upload_sprite", id:cid}));
    const w = document.createElement("div");
    w.style.cssText = "display:flex;gap:4px;flex:1"; w.append(sp, b);
    sec.add(field("sprite", w));

    /* expresiones: nombre -> imagen; el show elige cuál */
    const ew = document.createElement("div");
    Object.entries(c.expr || {}).forEach(([ex, f]) => {
      const row = document.createElement("div"); row.className = "expr";
      const nm = document.createElement("span"); nm.className = "n"; nm.textContent = ex;
      const sel = select(f, ASSETS.includes(f) ? ASSETS : ASSETS.concat(f));
      sel.onchange = () => op({op:"set_sprite", id: cid, expr: ex, file: sel.value});
      const fb = fileBtn(`Imagen para "${ex}"`, "img", S.base || "",
                         pa => op({op:"import_asset", path: pa, id: cid, expr: ex}),
                         () => upload({op:"upload_sprite", id: cid, expr: ex}));
      const x = document.createElement("span"); x.className = "x"; x.textContent = "✕"; x.title = "quitar la expresión";
      x.onclick = () => op({op:"set_sprite", id: cid, expr: ex, file: ""});
      row.append(nm, sel, fb, x); ew.appendChild(row);
    });
    const addx = document.createElement("button"); addx.textContent = "+ expresión";
    addx.onclick = async () => {
      let n = await askOne("Nueva expresión", "nombre (p.ej. feliz)"); if (!n) return;
      n = n.replace(/\s+/g, "_");
      if (["left", "center", "right"].includes(n)) return toast("ese nombre es una posición, elegí otro", true);
      const pa = await browse(`Imagen para "${n}"`, "img", S.base || "",
                              () => upload({op:"upload_sprite", id: cid, expr: n}));
      if (pa) op({op:"import_asset", path: pa, id: cid, expr: n});
    };
    ew.appendChild(addx);
    sec.add(field("expresiones", ew));
  }

  const ren = document.createElement("button");
  ren.textContent = "renombrar id…";
  ren.title = "cambia el id y reapunta todos los pasos que lo usan";
  ren.onclick = async () => {
    const n = await askOne("Renombrar personaje", "nuevo id", cid);
    if (n && n !== cid) op({op:"rename_char", old: cid, new: n});
  };
  sec.add(field("id", ren));
  return sec;
}

/* parámetros de animación por tipo (los que usa el engine, ver vnstudio._animate) */
const APARAMS = {
  linear: ["x", "y", "time"], accel: ["x", "y", "time"], decel: ["x", "y", "time"],
  move: ["x", "y", "time", "curve"],
  wave: ["vib", "cycle"], waveonce: ["vib", "cycle"], jump: ["vib", "cycle"], jumponce: ["vib", "cycle"],
  fall: ["dist", "falltime"], vibrate: ["vib", "wait"],
};
const ALABEL = { x: "x destino", y: "y destino", time: "tiempo ms", curve: "curva", vib: "amplitud",
                 cycle: "ciclo ms", dist: "distancia", falltime: "tiempo ms", wait: "cada ms" };
const ADEF = { x: 0, y: 0, time: 500, curve: "linear", vib: 18, cycle: 340, dist: 120, falltime: 600, wait: 40 };
/* params completos para un tipo: conserva los que siguen aplicando, rellena el resto */
function animDefaults(kind, cur){
  const out = {};
  (APARAMS[kind] || []).forEach(k => { out[k] = (cur && cur[k] != null) ? cur[k] : ADEF[k]; });
  return out;
}

/* secciones plegables (recuerdan si quedaron abiertas) */
function sect(title, open){
  const d = document.createElement("details"), k = "vnssec:" + title;
  try { const v = localStorage.getItem(k); if (v !== null) open = v === "1"; } catch (e) {}
  d.open = open;
  d.addEventListener("toggle", () => { try { localStorage.setItem(k, d.open ? "1" : "0"); } catch (e) {} });
  const sm = document.createElement("summary"); sm.textContent = title;
  d.appendChild(sm);
  d.add = el => { d.appendChild(el); return d; };
  return d;
}
/* campo numérico: se escribe o se arrastra la etiqueta (Shift = fino) */
function num(label, v, opts, commit){
  const el = input(v), row = field(label, el), lab = row.querySelector("label");
  lab.className = "scrub"; lab.title = "arrastrá para cambiar (Shift = fino)";
  lab.addEventListener("pointerdown", e => {
    const x0 = e.clientX, v0 = el.value;
    lab.setPointerCapture(e.pointerId);
    const move = ev => {
      el.value = VNS.scrubValue(v0, ev.clientX - x0, Object.assign({fine: ev.shiftKey}, opts));
      commit(+el.value, true);
    };
    const up = () => { lab.removeEventListener("pointermove", move);
                       lab.removeEventListener("pointerup", up); commit(+el.value, false); };
    lab.addEventListener("pointermove", move); lab.addEventListener("pointerup", up);
    e.preventDefault();
  });
  el.onchange = () => { if (el.value !== "") commit(+el.value, false); };
  return row;
}
/* mientras se arrastra se ve en el escenario; al soltar se guarda en el `show` */
function liveLayer(id, key){
  return (v, dragging) => {
    const l = SG.layers.find(x => x.id === id);
    if (l) {
      l[key] = v;
      const el = document.querySelector(`#stage .layer[data-id="${id}"]`);
      if (el) Object.assign(el.style, VNS.layerStyle(l, SG));
      markSelection();
    }
    if (!dragging) op({op:"set_layer", id, props:{[key]: v}});
  };
}

function renderProps(){
  const box = $("#props"); box.innerHTML = "";
  const steps = S.model.scenes[S.scene] || [];
  if (!(S.step >= 0 && S.step < steps.length)) {
    box.innerHTML = '<div class="hint">(elegí un paso en el timeline)</div>'; return; }
  const s = steps[S.step], chars = Object.keys(S.model.characters);
  const paso = sect("Paso", true); box.appendChild(paso);
  /* cada campo se aplica solo al cambiar (Enter o salir del campo): sin "Aplicar" */
  const add = (k, label, el) => {
    el.onchange = () => op({op:"set_props", props:{[k]: parseProp(k, el)}});
    if (el.tagName === "INPUT") el.onkeydown = e => { if (e.key === "Enter") el.blur(); };
    paso.add(field(label, el));
  };

  if (s.op === "bg") {
    const p = s.spec||{};
    add("bg","fondo", input(p.kind==="grad" ? `grad:${p.a},${p.b}` : p.kind==="solid" ? p.color : (p.file||"")));
    paso.add(field("imagen", picker(p.file || "", ASSETS,
      v => op({op:"set_props", props:{bg: v || "#000000"}}), "bg", "image/*")));
    const fr = num("fade ms", s.fade, {def: 0, min: 0, max: 5000, step: 10},
                   (v, dragging) => { if (!dragging) op({op:"set_props", props:{fade: v}}); });
    fr.querySelector("input").dataset.p = "fade";
    paso.add(fr);
    paso.insertAdjacentHTML("beforeend", '<div class="hint">grad:#a,#b · #rrggbb · archivo.png · fade 0 = corte seco</div>');
  } else if (s.op === "show" || s.op === "hide") {
    box.appendChild(charSection(s.id, chars, v => op({op:"set_props", props:{id: v}}),
                                s.op === "show"));
    if (s.op === "show") {
      const posSel = select(s.pos || "", ["", "left", "center", "right"]);
      posSel.querySelector('option[value=""]').textContent = "(donde está)";
      add("pos","pos", posSel);
      const exs = Object.keys((S.model.characters[s.id] || {}).expr || {});
      if (exs.length) {                                // sólo si el personaje tiene expresiones
        const e = select(s.expr || "", [""].concat(exs));
        e.querySelector('option[value=""]').textContent = "(base)"; e.dataset.k = "expr";
        add("expr", "expresión", e);
      }
      const tr = sect("Transformar", true); box.appendChild(tr);
      tr.add(num("x", s.x, {def:0}, liveLayer(s.id, "x")));
      tr.add(num("y", s.y, {def:0}, liveLayer(s.id, "y")));
      tr.add(num("z", s.z, {def:10, min:1}, liveLayer(s.id, "z")));
      tr.add(num("zoom %", s.zoom, {def:100, min:10, max:400}, liveLayer(s.id, "zoom")));
      tr.add(num("opac %", s.opacity, {def:100, min:0, max:100}, liveLayer(s.id, "opacity")));
      const tint = input(s.tint || "");
      tint.placeholder = "#rrggbb";
      tint.onchange = () => op({op:"set_layer", id:s.id, props:{tint: tint.value.trim()}});
      tr.add(field("tinte", tint));
      const zf = document.createElement("div");
      zf.style.cssText = "display:flex;gap:4px;flex:1";
      [["▲ al frente", true], ["▼ al fondo", false]].forEach(([t, front]) => {
        const b = document.createElement("button"); b.textContent = t;
        b.onclick = () => op({op:"set_z", id: s.id, front}); zf.appendChild(b);
      });
      tr.add(field("orden", zf));

      tr.insertAdjacentHTML("beforeend",
        '<div class="hint">arrastrá el sprite o sus esquinas en el escenario</div>');
    }
  } else if (s.op === "say") {
    const t = document.createElement("textarea"); t.rows = 3; t.value = s.text || "";
    add("text", "texto", t);
    t.onkeydown = e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); t.blur(); } };
    box.appendChild(charSection(s.who, chars, v => op({op:"set_props", props:{who: v}}), true));
  } else if (s.op === "animate") {
    const kind = select(s.kind, Object.keys(APARAMS)); kind.dataset.k = "kind";
    kind.onchange = () => op({op:"set_props", props:{kind: kind.value, params: animDefaults(kind.value, s.params)}});
    paso.add(field("tipo", kind));
    const params = animDefaults(s.kind, s.params);   // campos según el tipo, no "k=v"
    (APARAMS[s.kind] || []).forEach(k => {
      if (k === "curve") {
        const c = select(params.curve, ["linear", "accel", "decel"]); c.dataset.p = "curve";
        c.onchange = () => { params.curve = c.value; op({op:"set_props", props:{params}}); };
        paso.add(field(ALABEL[k], c)); return;
      }
      const row = num(ALABEL[k], params[k], {def: ADEF[k] || 0},
                      (v, dragging) => { params[k] = v; if (!dragging) op({op:"set_props", props:{params}}); });
      row.querySelector("input").dataset.p = k;
      paso.add(row);
    });
    paso.insertAdjacentHTML("beforeend",
      '<div class="hint">doble click en el timeline (o ▶ Probar paso) para verla</div>');
    box.appendChild(charSection(s.id, chars.filter(c => c !== "narrator"),
                                v => op({op:"set_props", props:{id: v}}), true));
  } else if (s.op === "bgm" || s.op === "se") {
    paso.add(field("archivo", picker(s.file || "", AUDIO,
      v => op({op:"set_props", props:{file: v}}), "file", "audio/*")));
    if (s.op === "bgm") { const c = document.createElement("input"); c.type="checkbox"; c.checked=!!s.stop;
                          c.style.width="auto"; add("stop","detener", c); }
  } else if (s.op === "goto") {
    add("target","a", select(s.target, S.model.order));
  } else if (s.op === "choice") {
    /* una fila por opción: etiqueta + escena destino + ✕ */
    const opts = (s.options || []).map(o => Object.assign({}, o));
    const commit = () => op({op:"set_props", props:{options: opts}});
    const wrap = document.createElement("div");
    opts.forEach((o, i) => {
      const row = document.createElement("div"); row.className = "opt";
      const lbl = input(o.label); lbl.placeholder = "etiqueta";
      lbl.onchange = () => { opts[i].label = lbl.value; commit(); };
      lbl.onkeydown = e => { if (e.key === "Enter") lbl.blur(); };
      const tgt = select(o.target, S.model.order);
      tgt.onchange = () => { opts[i].target = tgt.value; commit(); };
      const x = document.createElement("span"); x.className = "x"; x.textContent = "✕"; x.title = "sacar la opción";
      x.onclick = () => { opts.splice(i, 1); commit(); };
      row.append(lbl, tgt, x); wrap.appendChild(row);
    });
    const addb = document.createElement("button"); addb.textContent = "+ opción";
    addb.onclick = () => { opts.push({label: "opción", target: S.model.order[0]}); commit(); };
    wrap.appendChild(addb);
    paso.add(wrap);
    if (!opts.length) paso.insertAdjacentHTML("beforeend", '<div class="hint">sin opciones el choice no lleva a ningún lado</div>');
  } else { paso.insertAdjacentHTML("beforeend", '<div class="hint">(sin propiedades)</div>'); return; }

}
/* valor de un campo del paso, con el tipo que espera el modelo */
function parseProp(k, el){
  let v = el.type === "checkbox" ? el.checked : el.value;
  if (k === "options") return v.split("\n").filter(x => x.includes("->"))
      .map(x => ({label: x.split("->")[0].trim(), target: x.split("->")[1].trim()}));
  if (k === "params") { const o = {}; v.split(/\s+/).filter(Boolean).forEach(kv => {
      const [a, bb] = kv.split("="); const n = Number(bb); o[a] = isNaN(n) ? bb : n; }); return o; }
  return v;
}

async function refresh(){
  try {
    SG = S.play ? S.play : await api.stage(S.scene, S.step);
    const as = await api.assets(); ASSETS = as.assets; AUDIO = as.audio;
  } catch (e) { toast("no se pudo dibujar el escenario: " + e, true); return; }
  renderLists(); renderStage(); renderProps();
  if ((SG.warnings || []).length) toast(SG.warnings.join("\n"), true);
}

/* ---------- diálogos propios (nada de prompt/confirm del browser) ---------- */
function ask(title, fields, msg){
  const dlg = $("#dlg"), body = $("#dlg-body");
  $("#dlg-title").textContent = title;
  body.innerHTML = msg ? `<div id="dlg-msg">${msg}</div>` : "";
  const els = {};
  fields.forEach(f => {
    const el = input(f.v == null ? "" : f.v);
    if (f.type) el.type = f.type;
    if (f.list) { const sl = select(f.v, f.list); els[f.k] = sl; body.appendChild(field(f.label, sl)); return; }
    els[f.k] = el; body.appendChild(field(f.label, el));
  });
  $("#dlg-ok").textContent = fields.length ? "Aceptar" : "Sí";
  dlg.showModal();
  const first = body.querySelector("input,select");
  (first || $("#dlg-ok")).focus();                  // sin campos: Enter = Sí, no Cancelar
  dlg.onkeydown = e => {                            // Enter acepta aunque el foco esté en un select
    if (e.key === "Enter" && e.target.tagName !== "TEXTAREA") { e.preventDefault(); dlg.close("ok"); } };
  return new Promise(res => {
    dlg.addEventListener("close", () => {
      if (dlg.returnValue !== "ok") return res(null);
      const out = {};
      for (const [k, el] of Object.entries(els)) out[k] = el.value.trim();
      res(out);
    }, {once:true});
  });
}
const askOne = async (title, label, v) => {
  const r = await ask(title, [{k:"v", label, v}]);
  return r && r.v ? r.v : null;
};
const stepCount = () => (S.model.scenes[S.scene] || []).length;
$("#b-new").onclick = async () => {
  if (await ask("Nuevo proyecto", [], "Se descarta lo que no hayas guardado.")) op({op:"new_project"}); };
$("#b-open").onclick = async () => {
  const p = await browse("Abrir proyecto (.vn)", "vn", S.path || "");
  if (p) op({op:"open_project", path:p}); };
$("#b-play").onclick = () => op(S.play ? {op:"play_stop"}
                                 : {op:"play", scene:S.scene, step: Math.max(0, S.step)});
$("#b-undo").onclick = () => op({op:"undo"});
$("#b-redo").onclick = () => op({op:"redo"});
$("#b-validate").onclick = async () => {
  await op({op:"validate"});
  if (!(S.problems || []).length) toast("✓ proyecto válido: sin problemas");
  else toast(`${S.problems.length} problema(s) — mirá el panel de propiedades`, true);
};
$("#b-save").onclick = async () => {
  if (S.path) return op({op:"save"});
  const sug = (S.model.title || "historia").toLowerCase().replace(/\s+/g, "-") + ".vn";
  const p = await browse("Guardar como (.vn)", "vn", VNS.joinPath(S.base || "", sug));
  if (p) op({op:"save", path:p});
};
$("#b-export").onclick = async () => {
  const r = await ask("Exportar", [{k:"kind", label:"formato", v:"html", list:["html", "vnp", "iso"]}],
                      "html = player web · vnp = blob para la PS2 · iso = imagen booteable (necesita el ELF)");
  if (!r) return;
  if (r.kind === "html") {
    const p = await browse("Exportar player HTML", "any", VNS.joinPath(S.base || "", "player.html"));
    if (p) op({op:"export", path:p});
  } else if (r.kind === "vnp") {
    const p = await browse("Exportar blob PS2 (.vnp)", "any", VNS.joinPath(S.base || "", "game.vnp"));
    if (p) op({op:"export_ps2", path:p});
  } else {
    const elf = await browse("ELF del player (ps2/ZNTVN.ELF)", "any", S.base || "");
    if (!elf) return;
    const p = await browse("Exportar ISO", "any", VNS.joinPath(S.base || "", "historia.iso"));
    if (p) op({op:"export_ps2", path:p, elf});
  }
};
/* vista de flujo: SVG desde sceneGraph, click en un nodo va a la escena */
function renderGraph(){
  const g = VNS.sceneGraph(S.model), svg = $("#graph-svg");
  const W = Math.max(...g.nodes.map(n => n.x)) + 120, H = Math.max(...g.nodes.map(n => n.y)) + 60;
  svg.setAttribute("width", W); svg.setAttribute("height", H);
  const pos = Object.fromEntries(g.nodes.map(n => [n.id, n]));
  let out = `<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
    <path d="M0,0 L10,5 L0,10 z" fill="#868ea0"/></marker></defs>`;
  g.edges.forEach(e => {
    const a = pos[e.from], b = pos[e.to];
    const x1 = a.x, y1 = a.y + 16, x2 = b.x, y2 = b.y - 16 - (b === a ? 0 : 0);
    const loop = a === b;
    const d = loop ? `M${x1 + 40},${y1 - 16} C${x1 + 90},${y1 - 40} ${x1 + 90},${y1 + 10} ${x1 + 40},${y1}`
                   : `M${x1},${y1} C${x1},${(y1 + y2) / 2} ${x2},${(y1 + y2) / 2} ${x2},${y2}`;
    out += `<path class="edge" d="${d}" marker-end="url(#arr)"/>`;
    if (e.label) out += `<text class="elabel" x="${(x1 + x2) / 2 + 4}" y="${(y1 + y2) / 2}">${e.label.slice(0, 18)}</text>`;
  });
  g.nodes.forEach(n => {
    out += `<g class="node${n.start ? " start" : ""}${n.dead ? " dead" : ""}" data-id="${n.id}" transform="translate(${n.x - 60},${n.y - 16})">
      <rect width="120" height="32"/><text x="60" y="21" text-anchor="middle">${n.id}</text></g>`;
  });
  svg.innerHTML = out;
  svg.querySelectorAll(".node").forEach(el => el.addEventListener("click", () => {
    $("#graph").close(""); op({op:"select", scene: el.dataset.id, step: 0}); }));
}
$("#b-graph").onclick = () => { renderGraph(); $("#graph").showModal(); };
$("#b-char").onclick = async () => {
  const r = await ask("Nuevo personaje", [
    {k:"id", label:"id"}, {k:"name", label:"nombre"},
    {k:"color", label:"color", v:"#7cc4ff", type:"color"}]);
  if (r && r.id) op({op:"add_char", id:r.id, name:r.name || r.id, color:r.color}); };
$("#b-scene-add").onclick = async () => {
  const n = await askOne("Nueva escena", "id"); if(n) op({op:"add_scene", name:n}); };
$("#b-scene-dup").onclick = () => op({op:"dup_scene"});
$("#b-scene-ren").onclick = async () => {
  const n = await askOne("Renombrar escena", "nuevo id", S.scene); if(n) op({op:"rename_scene", name:n}); };
$("#b-scene-del").onclick = async () => {
  if (await ask("Borrar escena", [], `¿Borrar la escena "${S.scene}" con sus ${stepCount()} pasos?`))
    op({op:"del_scene"});
};
$("#b-scene-up").onclick = () => op({op:"move_scene", delta:-1});
$("#b-scene-dn").onclick = () => op({op:"move_scene", delta:1});
$("#b-step-add").onclick = () => op({op:"add_step", kind: $("#newop").value});
$("#b-step-dup").onclick = () => op({op:"dup_step"});
$("#b-step-up").onclick = () => op({op:"move_step", delta:-1});
$("#b-step-dn").onclick = () => op({op:"move_step", delta:1});
$("#b-step-del").onclick = () => SELS.length > 1 ? op({op:"del_steps", indices: SELS}) : op({op:"del_step"});
/* diálogo rápido: la acción más común de una VN, sin pasar por el inspector */
function renderQuickWho(){
  const sel = $("#quick-who"), cur = sel.value;
  const ids = Object.keys(S.model.characters);
  sel.innerHTML = ids.map(id => `<option value="${id}">${S.model.characters[id].name || id}</option>`).join("");
  const st = (S.model.scenes[S.scene] || [])[S.step];
  sel.value = ids.includes(cur) ? cur : (st && st.op === "say" && st.who) || ids.find(c => c !== "narrator") || "narrator";
}
$("#quick").addEventListener("keydown", async e => {
  if (e.key === "Escape") return $("#quick").blur();
  if (e.key !== "Enter") return;
  const text = $("#quick").value.trim(); if (!text) return;
  e.preventDefault();
  $("#quick").value = "";
  await op({op:"add_step", kind:"say", props:{who: $("#quick-who").value, text}});
  $("#quick").focus();                              // seguir escribiendo la siguiente línea
});
$("#b-prev").onclick = () => op({op:"select", scene:S.scene, step: Math.max(-1, S.step - 1)});
$("#b-next").onclick = () => op({op:"select", scene:S.scene, step: Math.min(stepCount() - 1, S.step + 1)});
/* preview AUTORITATIVO: lo renderiza Python con el engine real y llega como APNG */
let animT = null;
const ANIM_MS = 1200;
function closeAnim(){
  clearTimeout(animT);
  $("#anim").hidden = true; $("#anim").removeAttribute("src");
  $("#animbar").hidden = true;
}
$("#b-probar").onclick = () => {
  if (S.step < 0) return toast("elegí un paso en el timeline para probarlo");
  const a = $("#anim");
  a.src = `/api/anim?scene=${encodeURIComponent(S.scene)}&step=${S.step}&ms=${ANIM_MS}&_=${Date.now()}`;
  a.hidden = false; $("#animbar").hidden = false;
  clearTimeout(animT);
  animT = setTimeout(closeAnim, ANIM_MS + 600);      // se va sola, no hay que adivinar
};
$("#b-anim-x").onclick = closeAnim;
$("#b-adv").onclick = () => { if (!finishTyping()) op({op:"play_advance"}); };
$("#b-cps").onclick = cycleCps;
$("#b-cps").textContent = "⌨ " + (CPS ? CPS + " cps" : "sin tipeo");
$("#b-exit").onclick = () => op({op:"play_stop"});
$("#b-help").onclick = () => $("#help").showModal();
function goFind(r){ $("#find").close(""); op({op:"select", scene:r.scene, step:r.step}); }
$("#find-q").addEventListener("input", () => {
  const ul = $("#find-list"); ul.innerHTML = "";
  VNS.searchSteps(S.model, $("#find-q").value).slice(0, 60).forEach(r => {
    const li = document.createElement("li");
    li.innerHTML = `<span class="n">${r.scene} · ${r.step + 1}</span>${r.text.slice(0, 90)}`;
    li.onclick = () => goFind(r); ul.appendChild(li);
  });
});
$("#find-q").addEventListener("keydown", e => {
  if (e.key === "Enter") { e.preventDefault(); const r = VNS.searchSteps(S.model, $("#find-q").value)[0]; if (r) goFind(r); }
});
$("#anim").onclick = closeAnim;

const CMDS = {
  play:     () => $("#b-play").click(),
  stop:     () => { if (!$("#anim").hidden) return closeAnim();
                    if (S.play) op({op:"play_stop"}); },
  prev:     () => $("#b-prev").click(),
  next:     () => $("#b-next").click(),
  del_step: () => { if (SELS.length > 1) op({op:"del_steps", indices: SELS}); else $("#b-step-del").click(); },
  copy:     () => {
    const steps = S.model.scenes[S.scene] || [];
    CLIP = SELS.filter(i => steps[i]).map(i => JSON.parse(JSON.stringify(steps[i])));
    if (CLIP.length) toast(`${CLIP.length} paso(s) copiado(s)`); },
  paste:    () => { if (CLIP.length) op({op:"paste_steps", steps: CLIP}); else toast("no hay pasos copiados"); },
  find:     () => { $("#find-q").value = ""; $("#find-list").innerHTML = ""; $("#find").showModal(); $("#find-q").focus(); },
  guides:   cycleGuides,
  undo:     () => op({op:"undo"}),
  redo:     () => op({op:"redo"}),
  save:     () => $("#b-save").click(),
  help:     () => { $("#help").showModal(); },
};
$("#help-body").innerHTML = VNS.KEYMAP.map(
  e => `<tr><td class="k">${e.keys}</td><td>${e.desc}</td></tr>`).join("");

addEventListener("keydown", e => {
  const t = e.target.tagName;
  if (t === "INPUT" || t === "TEXTAREA" || t === "SELECT" || $("#dlg").open || $("#brw").open || $("#find").open || $("#graph").open) return;
  if ($("#help").open) return;
  /* en Play, espacio/enter avanzan el diálogo */
  if (S.play && (e.key === " " || e.key === "Enter") && !(SG.choices||[]).length && !SG.done) {
    e.preventDefault(); if (!finishTyping()) op({op:"play_advance"}); return; }
  const cmd = VNS.resolveKey(e);
  if (!cmd || !CMDS[cmd]) return;
  e.preventDefault(); CMDS[cmd]();
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
  if (S.play) {                            // en Play el click completa el texto, después avanza
    if (finishTyping()) return;
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
  markSelection();
  showGuides(gx, gy);
});

const endDrag = async () => {
  if (!drag) return;
  const l = drag.l; drag = null; showGuides(null, null);
  await op({op:"set_layer_pos", id: l.id, x: Math.round(l.x), y: Math.round(l.y)});
};
$("#stage").addEventListener("pointerup", endDrag);
$("#stage").addEventListener("pointercancel", endDrag);

addEventListener("beforeunload", e => { if (S && S.dirty) { e.preventDefault(); e.returnValue = ""; } });

(async () => {
  S = await api.model();
  if (S.api !== API) {
    toast(`El server que está corriendo es de otra versión (server api=${S.api == null ? "viejo" : S.api},` +
          ` UI api=${API}). Cerralo con Ctrl+C y volvé a correr: python3 -m znt web`, true);
    $("#probs").textContent = "Server desactualizado: reinicialo (Ctrl+C y python3 -m znt web).";
  }
  if (S.step < 0 && (S.model.scenes[S.scene] || []).length)
    S = await api.op({op:"select", scene:S.scene, step:0});
  $("#newop").innerHTML = S.step_ops.map(o => `<option>${o}</option>`).join("");
  $("#newop").value = "say";
  await refresh();
})();
