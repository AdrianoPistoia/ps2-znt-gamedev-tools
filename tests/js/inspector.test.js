const assert = require("assert");
const A = require(require("path").join(__dirname, "../../znt/web/static/logic.js"));

/* --- campos numéricos que se arrastran (estilo Blender/AE) --- */
assert.strictEqual(A.scrubValue(100, 0, {}), 100, "sin arrastre no cambia");
assert.strictEqual(A.scrubValue(100, 10, {}), 110, "1 px = 1 unidad");
assert.strictEqual(A.scrubValue(100, 3, {step: 5}), 115, "paso de 5");
assert.strictEqual(A.scrubValue(100, 10, {fine: true}), 103, "fino: un cuarto");
assert.strictEqual(A.scrubValue(10, -100, {min: 0}), 0, "no baja del mínimo");
assert.strictEqual(A.scrubValue(390, 100, {max: 400}), 400, "ni sube del máximo");
assert.strictEqual(A.scrubValue(null, 5, {def: 100}), 105, "vacío arranca del default");
assert.ok(Number.isInteger(A.scrubValue(100, 7, {fine: true})), "siempre entero");
console.log("INSPECTOR GREEN");
