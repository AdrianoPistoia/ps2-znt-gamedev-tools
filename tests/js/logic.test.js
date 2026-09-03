const assert = require("assert");
const A = require(require("path").join(__dirname,"../../znt/web/static/logic.js"));
const near = (a, b, m) => assert.ok(Math.abs(a - b) < 1e-6, `${m}: ${a} != ${b}`);
const st = { w: 640, h: 448 };

// capa centrada, tamaño natural, apoyada en el piso
let s = A.layerStyle({ x: 0, y: 0, z: 10, zoom: 100, opacity: 100, w: 200, h: 300 }, st);
near(parseFloat(s.left), (320 - 100) / 640 * 100, "left centrado");
near(parseFloat(s.top), (448 - 300) / 448 * 100, "top piso");
near(parseFloat(s.width), 200 / 640 * 100, "width");
near(parseFloat(s.height), 300 / 448 * 100, "height");
assert.strictEqual(s.zIndex, 10, "zIndex = level");
near(parseFloat(s.opacity), 1, "opacity");

// zoom 200% escala y mantiene el centro y la base
s = A.layerStyle({ x: 0, y: 0, z: 1, zoom: 200, opacity: 50, w: 200, h: 300 }, st);
near(parseFloat(s.width), 400 / 640 * 100, "width zoom");
near(parseFloat(s.left), (320 - 200) / 640 * 100, "left zoom (centrado)");
near(parseFloat(s.top), (448 - 600) / 448 * 100, "top zoom (base)");
near(parseFloat(s.opacity), 0.5, "opacity 50");

// offset x/y
s = A.layerStyle({ x: 180, y: -20, z: 1, zoom: 100, opacity: 100, w: 200, h: 300 }, st);
near(parseFloat(s.left), (320 + 180 - 100) / 640 * 100, "left con x");
near(parseFloat(s.top), (448 - 300 - 20) / 448 * 100, "top con y");

// fondos
assert.ok(A.bgStyle({ kind: "grad", a: "#101828", b: "#304060" }).includes("linear-gradient"));
assert.strictEqual(A.bgStyle({ kind: "solid", color: "#123456" }), "#123456");
assert.ok(A.bgStyle({ kind: "img", url: "/api/asset?f=a.png" }).includes("url("));
console.log("LOGIC GREEN");
