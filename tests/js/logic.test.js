const assert = require("assert");
const A = require(require("path").join(__dirname,"../../znt/web/static/logic.js"));
const near = (a, b, m) => assert.ok(Math.abs(a - b) < 1e-6, `${m}: ${a} != ${b}`);
const st = { w: 640, h: 448 };

// centred layer, natural size, resting on the floor
let s = A.layerStyle({ x: 0, y: 0, z: 10, zoom: 100, opacity: 100, w: 200, h: 300 }, st);
near(parseFloat(s.left), (320 - 100) / 640 * 100, "left centred");
near(parseFloat(s.top), (448 - 300) / 448 * 100, "top floor");
near(parseFloat(s.width), 200 / 640 * 100, "width");
near(parseFloat(s.height), 300 / 448 * 100, "height");
assert.strictEqual(s.zIndex, 10, "zIndex = level");
near(parseFloat(s.opacity), 1, "opacity");

// 200% zoom scales and keeps the centre and the baseline
s = A.layerStyle({ x: 0, y: 0, z: 1, zoom: 200, opacity: 50, w: 200, h: 300 }, st);
near(parseFloat(s.width), 400 / 640 * 100, "width zoom");
near(parseFloat(s.left), (320 - 200) / 640 * 100, "left zoom (centred)");
near(parseFloat(s.top), (448 - 600) / 448 * 100, "top zoom (baseline)");
near(parseFloat(s.opacity), 0.5, "opacity 50");

// x/y offset
s = A.layerStyle({ x: 180, y: -20, z: 1, zoom: 100, opacity: 100, w: 200, h: 300 }, st);
near(parseFloat(s.left), (320 + 180 - 100) / 640 * 100, "left with x");
near(parseFloat(s.top), (448 - 300 - 20) / 448 * 100, "top with y");

// backgrounds
assert.ok(A.bgStyle({ kind: "grad", a: "#101828", b: "#304060" }).includes("linear-gradient"));
assert.strictEqual(A.bgStyle({ kind: "solid", color: "#123456" }), "#123456");
assert.ok(A.bgStyle({ kind: "img", url: "/api/asset?f=a.png" }).includes("url("));
console.log("LOGIC GREEN");
