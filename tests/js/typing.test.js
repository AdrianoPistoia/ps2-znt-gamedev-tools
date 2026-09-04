const assert = require("assert");
const A = require(require("path").join(__dirname, "../../znt/web/static/logic.js"));

/* Efecto de tipeo: cuántos caracteres se muestran a los t ms, a cps chars/seg. */
assert.strictEqual(A.typedChars("hola mundo", 0, 40), 0);
assert.strictEqual(A.typedChars("hola mundo", 100, 40), 4, "40 cps -> 4 en 100 ms");
assert.strictEqual(A.typedChars("hola mundo", 5000, 40), 10, "nunca pasa el largo");
assert.strictEqual(A.typedChars("hola", 100, 0), 4, "cps 0 = sin efecto: todo de una");
assert.strictEqual(A.typedChars("", 100, 40), 0);
console.log("TYPING GREEN");
