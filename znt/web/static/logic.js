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

  return { layerStyle, bgStyle, stageXY, snap, snapTargets, dragTo, POS };
});
