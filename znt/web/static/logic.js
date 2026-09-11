/* Pure client-side logic for VN Studio (no DOM) — testable with node.
 * The Python server sends the layer LAYOUT; here we only translate it to CSS.
 * Everything in percentages: the stage scales with its container, no resize JS. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.VNS = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  /* Layer -> CSS. Anchored at the bottom and centered in x (same rule as VNRuntime). */
  function layerStyle(l, st) {
    const zoom = (l.zoom == null ? 100 : l.zoom) / 100;
    const w = l.w * zoom, h = l.h * zoom;
    return {
      left:   ((st.w / 2 + l.x - w / 2) / st.w * 100) + "%",
      top:    ((st.h - h + l.y) / st.h * 100) + "%",
      width:  (w / st.w * 100) + "%",
      height: (h / st.h * 100) + "%",
      zIndex: l.z,
      opacity: (l.opacity == null ? 100 : l.opacity) / 100,
    };
  }

  function bgStyle(bg) {
    if (!bg) return "#000";
    if (bg.kind === "grad") return `linear-gradient(160deg, ${bg.a}, ${bg.b})`;
    if (bg.kind === "img") return `center/cover url("${bg.url}")`;
    return bg.color || "#000";
  }

  /* Position presets (same as vnstudio.POS). */
  const POS = { left: -180, center: 0, right: 180 };

  /* Pointer point -> stage coords (the stage may be scaled by CSS). */
  function stageXY(clientX, clientY, rect, st) {
    return { x: (clientX - rect.left) / rect.width * st.w,
             y: (clientY - rect.top) / rect.height * st.h };
  }

  /* Magnet: snaps to the nearest target within the threshold. */
  function snap(raw, targets, thr) {
    let best = null, bd = thr + 1;
    for (const t of targets) { const d = Math.abs(raw - t); if (d < bd) { best = t; bd = d; } }
    return (best !== null && bd <= thr) ? { v: best, hit: true } : { v: raw, hit: false };
  }

  /* Snap targets: center, presets and the other layers' axis/baseline. */
  function snapTargets(layers, selfId) {
    const others = layers.filter(l => l.id !== selfId);
    return { xs: [0, POS.left, POS.right].concat(others.map(l => l.x)),
             ys: [0].concat(others.map(l => l.y)) };
  }

  /* Drop at stage (fx,fy) -> layer x/y (respects zoom and bottom anchoring). */
  function dragTo(l, st, grabDX, grabDY, fx, fy) {
    const zoom = (l.zoom == null ? 100 : l.zoom) / 100;
    const w = l.w * zoom, h = l.h * zoom;
    return { x: (fx - grabDX) - st.w / 2 + w / 2,
             y: (fy - grabDY) - st.h + h };
  }

  /* --- stage: what gets drawn on top --- */

  /* In Play it looks like the game. While editing, choices are previewed without
     covering the stage (the game's scrim made it look like "it darkened by itself")
     and the viewport eye turns the overlays off to work on the sprites. */
  function stageOverlay(st) {
    const has = (st.choices || []).length > 0;
    if (st.play)
      return { dialog: !!st.say, choices: has, scrim: has ? 0.6 : 0,
               interactive: true, label: "" };
    if (!st.showDialog)
      return { dialog: false, choices: false, scrim: 0, interactive: false, label: "" };
    return { dialog: !!st.say, choices: has, scrim: has ? 0.22 : 0,
             interactive: false,
             label: has ? "choices (preview) — ▶ Play to try them" : "" };
  }

  /* --- file browser --- */

  /* Path -> clickable segments. */
  function crumbs(path) {
    if (!path) return [];
    const parts = path.split("/").filter(Boolean);
    const out = [{ name: "/", path: "/" }];
    let acc = "";
    for (const p of parts) { acc += "/" + p; out.push({ name: p, path: acc }); }
    return out;
  }
  const joinPath = (dir, name) => (dir.endsWith("/") ? dir : dir + "/") + name;

  /* --- Play --- */

  /* Typing effect: characters visible at t ms (cps 0 = all at once). */
  function typedChars(text, t, cps) {
    if (!cps) return text.length;
    return Math.min(text.length, Math.floor(t * cps / 1000));
  }

  /* Scene/step the timeline shows: the runtime's while playing. */
  function playCursor(S) {
    if (S.play) return { scene: S.play.scene, step: S.play.step, playing: true };
    return { scene: S.scene, step: S.step, playing: false };
  }

  /* --- state --- */

  /* Server response -> new state + error to show. A broken response
     (400/500 or failed fetch) must not leave the UI without a model. */
  function mergeState(prev, res) {
    if (!res) return { state: prev, error: "no response from the server" };
    if (!res.model) return { state: prev, error: res.error || "unexpected response" };
    return { state: res, error: res.error || null };
  }

  /* --- shortcuts --- */

  /* One place: both the dispatch and the help overlay come from here. */
  const KEYMAP = [
    { keys: "Space",      cmd: "play",     desc: "Play / next step" },
    { keys: "Esc",        cmd: "stop",     desc: "Exit Play mode" },
    { keys: "←  →",       cmd: "prev",     desc: "Previous / next step" },
    { keys: "Del",        cmd: "del_step", desc: "Delete the step" },
    { keys: "G",          cmd: "guides",   desc: "Guides: center / thirds / safe area" },
    { keys: "Ctrl+Z",     cmd: "undo",     desc: "Undo" },
    { keys: "Ctrl+Y",     cmd: "redo",     desc: "Redo" },
    { keys: "Ctrl+S",     cmd: "save",     desc: "Save the .vn" },
    { keys: "Ctrl+C / Ctrl+V", cmd: "copy", desc: "Copy / paste steps (across scenes too)" },
    { keys: "Ctrl+F",     cmd: "find",     desc: "Search lines and choices" },
    { keys: "Ctrl+G",     cmd: "group",    desc: "Group the selected steps (one click in Play) / ungroup" },
    { keys: "Shift / Ctrl + click", cmd: null, desc: "Multi-select in the timeline" },
    { keys: "?",          cmd: "help",     desc: "This help" },
    { keys: "Shift",      cmd: null,       desc: "Drag without snapping / fine scrub" },
    { keys: "Ctrl+wheel", cmd: null,       desc: "Timeline zoom" },
  ];

  /* Key -> command (null if unmapped). */
  function resolveKey(e) {
    const k = e.key, low = k.length === 1 ? k.toLowerCase() : k;
    if (e.ctrlKey || e.metaKey) {
      if (low === "z") return e.shiftKey ? "redo" : "undo";
      if (low === "y") return "redo";
      if (low === "s") return "save";
      if (low === "c") return "copy";
      if (low === "v") return "paste";
      if (low === "f") return "find";
      if (low === "g") return "group";
      return null;
    }
    if (k === " ") return "play";
    if (k === "Escape") return "stop";
    if (k === "ArrowLeft") return "prev";
    if (k === "ArrowRight") return "next";
    if (k === "Delete" || k === "Backspace") return "del_step";
    if (low === "g") return "guides";
    if (k === "?") return "help";
    return null;
  }

  /* --- inspector --- */

  /* Draggable numeric field: dx in pixels -> value. */
  function scrubValue(v, dx, o) {
    o = o || {};
    const base = (v == null || v === "" || isNaN(v)) ? (o.def == null ? 0 : o.def) : +v;
    let n = Math.round(base + dx * (o.step == null ? 1 : o.step) * (o.fine ? 0.25 : 1));
    if (o.min != null) n = Math.max(o.min, n);
    if (o.max != null) n = Math.min(o.max, n);
    return n;
  }

  /* --- viewport --- */

  /* Drag a corner handle (dir: 1 right, -1 left). The layer is centered on
     its x, so the width grows on the opposite side too: 2*dx. */
  function resizeZoom(l, dir, dx) {
    const z = (l.zoom == null ? 100 : l.zoom);
    return Math.max(10, Math.min(400, Math.round((l.w * z / 100 + 2 * dir * dx) / l.w * 100)));
  }

  /* Viewport guides, as fractions of the stage. */
  const GUIDES = ["off", "center", "thirds", "safe"];
  function guides(kind) {
    if (kind === "center") return { xs: [0.5], ys: [0.5], rect: null };
    if (kind === "thirds") return { xs: [1/3, 2/3], ys: [1/3, 2/3], rect: null };
    if (kind === "safe")   return { xs: [], ys: [], rect: { x: .05, y: .05, w: .9, h: .9 } };
    return { xs: [], ys: [], rect: null };
  }
  const nextGuide = k => GUIDES[(GUIDES.indexOf(k) + 1) % GUIDES.length];

  /* --- scene graph --- */

  /* Nodes by depth from `start` (BFS over goto/choice); unreachable ones
     go last. Returns positions ready to draw. */
  function sceneGraph(model) {
    const edges = [];
    for (const sc of model.order) {
      for (const s of model.scenes[sc] || []) {
        if (s.op === "goto" && s.target) edges.push({ from: sc, to: s.target, label: "", kind: "goto" });
        if (s.op === "choice") (s.options || []).forEach(o => edges.push({ from: sc, to: o.target, label: o.label || "", kind: "choice" }));
      }
    }
    const depth = {}, start = model.start || model.order[0];
    if (model.scenes[start]) depth[start] = 0;
    const q = [start];
    while (q.length) {
      const cur = q.shift();
      for (const e of edges) if (e.from === cur && model.scenes[e.to] && depth[e.to] === undefined) {
        depth[e.to] = depth[cur] + 1; q.push(e.to);
      }
    }
    const maxD = Math.max(-1, ...Object.values(depth));
    const rows = {};
    const nodes = model.order.map(id => {
      const steps = model.scenes[id] || [];
      const d = depth[id] === undefined ? maxD + 1 : depth[id];
      const k = (rows[d] = (rows[d] || 0) + 1) - 1;
      return { id, depth: d, x: 80 + k * 170, y: 40 + d * 90, start: id === start,
               dead: !steps.some(s => s.op === "end" || s.op === "goto" || s.op === "choice") };
    });
    return { nodes, edges: edges.filter(e => model.scenes[e.to]) };
  }

  /* --- step groups (runs with the same `group`) --- */
  function groupRuns(steps) {
    const out = []; let cur = null;
    steps.forEach((s, i) => {
      const g = s.group || null;
      if (g && cur && cur.name === g) cur.b = i;
      else { if (cur) out.push(cur); cur = g ? { name: g, a: i, b: i } : null; }
    });
    if (cur) out.push(cur);
    return out;
  }

  /* --- multi-select and search --- */

  /* Click on clip i with the current selection: plain, Shift = range from the
     anchor, Ctrl = add/remove. Returns the new (sorted) selection and the anchor. */
  function clickSelect(sel, anchor, i, mods) {
    if (mods.shift && anchor >= 0) {
      const a = Math.min(anchor, i), b = Math.max(anchor, i), out = [];
      for (let k = a; k <= b; k++) out.push(k);
      return { sel: out, anchor };
    }
    if (mods.ctrl) {
      const out = sel.includes(i) ? sel.filter(k => k !== i) : sel.concat(i);
      return { sel: out.sort((x, y) => x - y), anchor: i };
    }
    return { sel: [i], anchor: i };
  }

  /* Searches lines and choice labels, case-insensitive. */
  function searchSteps(model, q) {
    q = (q || "").trim().toLowerCase();
    if (!q) return [];
    const out = [];
    for (const sc of model.order) {
      (model.scenes[sc] || []).forEach((s, i) => {
        const t = s.op === "say" ? (s.text || "")
              : s.op === "choice" ? (s.options || []).map(o => o.label).join(" / ") : "";
        if (t.toLowerCase().includes(q)) out.push({ scene: sc, step: i, text: t });
      });
    }
    return out;
  }

  /* --- outliner --- */

  /* Stage layers, frontmost first. */
  function outlineRows(layers) {
    return layers.slice()
      .sort((a, b) => (b.z - a.z) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0))
      .map(l => ({ id: l.id, name: l.name || l.id, z: l.z, color: l.color,
                   sprite: !!l.url, expr: l.expr || null }));
  }

  /* Index of the `show` that placed that layer (the last one at or before `upto`). */
  function showStepIndex(steps, id, upto) {
    const end = upto >= 0 ? Math.min(upto, steps.length - 1) : steps.length - 1;
    for (let i = end; i >= 0; i--)
      if (steps[i].op === "show" && steps[i].id === id) return i;
    return -1;
  }

  /* --- timeline: steps as clips, in lanes by type --- */

  const LANES = [
    { key: "background", ops: ["bg"],                  color: "#3d6a8f" },
    { key: "characters", ops: ["show", "hide", "animate"], color: "#7a5aa8" },
    { key: "dialogue",   ops: ["say"],                 color: "#2f7a5f" },
    { key: "audio",      ops: ["bgm", "se"],           color: "#8f6a30" },
    { key: "flow",       ops: ["choice", "goto", "end"], color: "#8f4050" },
  ];
  const laneOf = op => {
    const i = LANES.findIndex(l => l.ops.indexOf(op) >= 0);
    return i < 0 ? LANES.length - 1 : i;                // unknown ops: flow
  };

  /* Rectangle of clip i (view: clip width, lane height and gap). */
  function clipRect(step, i, view) {
    const lane = laneOf(step.op);
    return { x: i * view.cw, y: lane * view.lh,
             w: view.cw - view.gap, h: view.lh - view.gap, lane };
  }

  /* Dropping at x: which position does it land on? */
  function dropIndex(x, view, n) {
    return Math.max(0, Math.min(n - 1, Math.round(x / view.cw)));
  }

  /* --- shell --- */

  /* Pane width while dragging the splitter: respects its minimum and the neighbor's. */
  function clampPane(px, total, min, minOther) {
    return Math.max(min, Math.min(px, total - minOther));
  }

  /* Fit the stage (aw x ah) inside the container, centered and letterboxed. */
  function fitRect(cw, ch, aw, ah) {
    if (cw <= 0 || ch <= 0) return { w: 0, h: 0, left: 0, top: 0, scale: 0 };
    const scale = Math.min(cw / aw, ch / ah), w = aw * scale, h = ah * scale;
    return { w, h, left: (cw - w) / 2, top: (ch - h) / 2, scale };
  }

  return { layerStyle, bgStyle, stageXY, snap, snapTargets, dragTo, POS,
           clampPane, fitRect, groupRuns, sceneGraph, clickSelect, searchSteps, typedChars, playCursor, stageOverlay, crumbs, joinPath, mergeState, KEYMAP, resolveKey, scrubValue, resizeZoom, guides, nextGuide, GUIDES, outlineRows, showStepIndex, LANES, laneOf, clipRect, dropIndex };
});
