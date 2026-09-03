const assert = require("assert");
const A = require(require("path").join(__dirname, "../../znt/web/static/logic.js"));

/* --- handles: arrastrar una esquina cambia el zoom, no el tamaño natural --- */
const l = { w: 200, h: 300, zoom: 100 };
assert.strictEqual(A.resizeZoom(l, 1, 0), 100, "sin movimiento no cambia");
assert.strictEqual(A.resizeZoom(l, 1, 50), 150, "tirar 50px a la derecha sobre 200 de ancho");
assert.strictEqual(A.resizeZoom(l, -1, -50), 150, "el handle izquierdo es simétrico");
assert.strictEqual(A.resizeZoom(l, 1, -50), 50, "achicar");
assert.strictEqual(A.resizeZoom(l, 1, -400), 10, "tope mínimo");
assert.strictEqual(A.resizeZoom(l, 1, 9999), 400, "tope máximo");
assert.strictEqual(A.resizeZoom({ w: 200, h: 300, zoom: 200 }, 1, 0), 200, "parte del zoom actual");

/* --- guías: ciclo off -> centro -> tercios -> safe --- */
assert.deepStrictEqual(A.guides("off"), { xs: [], ys: [], rect: null });
assert.deepStrictEqual(A.guides("center"), { xs: [0.5], ys: [0.5], rect: null });
const t = A.guides("thirds");
assert.deepStrictEqual(t.xs.map(v => +v.toFixed(3)), [0.333, 0.667]);
assert.deepStrictEqual(t.ys.map(v => +v.toFixed(3)), [0.333, 0.667]);
assert.deepStrictEqual(A.guides("safe").rect, { x: 0.05, y: 0.05, w: 0.9, h: 0.9 });
assert.strictEqual(A.nextGuide("off"), "center");
assert.strictEqual(A.nextGuide("safe"), "off", "cierra el ciclo");
console.log("VIEWPORT GREEN");
