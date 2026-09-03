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

  return { layerStyle, bgStyle };
});
