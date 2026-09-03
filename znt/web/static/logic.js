/* Lógica pura del cliente de VN Studio (sin DOM) — testeable con node.
 * El servidor Python manda el LAYOUT de las capas; acá sólo lo traducimos a CSS.
 * Todo en porcentajes: el stage escala solo con su contenedor, sin JS de resize. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.VNS = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  /* Capa -> CSS. Anclada abajo y centrada en x (mismo criterio que VNRuntime). */
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

  /* Presets de posición (mismos que vnstudio.POS). */
  const POS = { left: -180, center: 0, right: 180 };

  /* Punto del puntero -> coords del stage (el stage puede estar escalado por CSS). */
  function stageXY(clientX, clientY, rect, st) {
    return { x: (clientX - rect.left) / rect.width * st.w,
             y: (clientY - rect.top) / rect.height * st.h };
  }

  /* Imán: engancha al objetivo más cercano dentro del umbral. */
  function snap(raw, targets, thr) {
    let best = null, bd = thr + 1;
    for (const t of targets) { const d = Math.abs(raw - t); if (d < bd) { best = t; bd = d; } }
    return (best !== null && bd <= thr) ? { v: best, hit: true } : { v: raw, hit: false };
  }

  /* Objetivos de snap: centro, presets y el eje/base de las otras capas. */
  function snapTargets(layers, selfId) {
    const others = layers.filter(l => l.id !== selfId);
    return { xs: [0, POS.left, POS.right].concat(others.map(l => l.x)),
             ys: [0].concat(others.map(l => l.y)) };
  }

  /* Soltar en (fx,fy) del stage -> x/y de la capa (respeta zoom y anclaje abajo). */
  function dragTo(l, st, grabDX, grabDY, fx, fy) {
    const zoom = (l.zoom == null ? 100 : l.zoom) / 100;
    const w = l.w * zoom, h = l.h * zoom;
    return { x: (fx - grabDX) - st.w / 2 + w / 2,
             y: (fy - grabDY) - st.h + h };
  }

  /* --- timeline: los pasos como clips, en pistas por tipo --- */

  const LANES = [
    { key: "fondo",      ops: ["bg"],                  color: "#3d6a8f" },
    { key: "personajes", ops: ["show", "hide", "animate"], color: "#7a5aa8" },
    { key: "diálogo",    ops: ["say"],                 color: "#2f7a5f" },
    { key: "audio",      ops: ["bgm", "se"],           color: "#8f6a30" },
    { key: "flujo",      ops: ["choice", "goto", "end"], color: "#8f4050" },
  ];
  const laneOf = op => {
    const i = LANES.findIndex(l => l.ops.indexOf(op) >= 0);
    return i < 0 ? LANES.length - 1 : i;                // lo desconocido: flujo
  };

  /* Rectángulo del clip i (view: ancho de clip, alto de pista y separación). */
  function clipRect(step, i, view) {
    const lane = laneOf(step.op);
    return { x: i * view.cw, y: lane * view.lh,
             w: view.cw - view.gap, h: view.lh - view.gap, lane };
  }

  /* Al soltar en x, ¿en qué posición cae? */
  function dropIndex(x, view, n) {
    return Math.max(0, Math.min(n - 1, Math.round(x / view.cw)));
  }

  /* --- shell --- */

  /* Ancho de un panel al arrastrar el splitter: respeta su mínimo y el del vecino. */
  function clampPane(px, total, min, minOther) {
    return Math.max(min, Math.min(px, total - minOther));
  }

  /* Encajar el stage (aw x ah) dentro del contenedor, centrado y con letterbox. */
  function fitRect(cw, ch, aw, ah) {
    if (cw <= 0 || ch <= 0) return { w: 0, h: 0, left: 0, top: 0, scale: 0 };
    const scale = Math.min(cw / aw, ch / ah), w = aw * scale, h = ah * scale;
    return { w, h, left: (cw - w) / 2, top: (ch - h) / 2, scale };
  }

  return { layerStyle, bgStyle, stageXY, snap, snapTargets, dragTo, POS,
           clampPane, fitRect, LANES, laneOf, clipRect, dropIndex };
});
