const assert = require("assert");
const A = require(require("path").join(__dirname, "../../znt/web/static/logic.js"));

/* --- splitters: nunca aplastan un panel ni al vecino --- */
assert.strictEqual(A.clampPane(300, 1200, 180, 400), 300, "valor cómodo pasa igual");
assert.strictEqual(A.clampPane(50, 1200, 180, 400), 180, "mínimo propio");
assert.strictEqual(A.clampPane(900, 1200, 180, 400), 800, "deja el mínimo del vecino");
assert.strictEqual(A.clampPane(500, 500, 180, 400), 180, "ventana chica: gana el mínimo propio");

/* --- viewport: el stage entra entero y centrado (letterbox) --- */
let r = A.fitRect(1000, 400, 640, 448);          // contenedor ancho -> sobra a los costados
assert.strictEqual(r.h, 400, "alto limitante");
assert.strictEqual(Math.round(r.w), Math.round(400 * 640 / 448), "mantiene aspecto");
assert.strictEqual(Math.round(r.left), Math.round((1000 - r.w) / 2), "centrado en x");
assert.strictEqual(r.top, 0, "sin barras arriba");

r = A.fitRect(320, 1000, 640, 448);              // contenedor alto -> sobra arriba y abajo
assert.strictEqual(r.w, 320, "ancho limitante");
assert.strictEqual(Math.round(r.h), Math.round(320 * 448 / 640), "mantiene aspecto");
assert.strictEqual(Math.round(r.top), Math.round((1000 - r.h) / 2), "centrado en y");

r = A.fitRect(1280, 896, 640, 448);
assert.strictEqual(r.scale, 2, "escala = cuánto agranda el stage");
assert.deepStrictEqual(A.fitRect(0, 0, 640, 448), { w: 0, h: 0, left: 0, top: 0, scale: 0 },
                       "contenedor sin medir todavía");
console.log("SHELL GREEN");
