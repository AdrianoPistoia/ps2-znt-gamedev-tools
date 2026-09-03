const assert = require("assert");
const A = require(require("path").join(__dirname, "../../znt/web/static/logic.js"));

const prev = { model: {x: 1}, scene: "s", step: 2 };

// respuesta normal: se adopta
let r = A.mergeState(prev, { model: {x: 2}, scene: "s", step: 3 });
assert.deepStrictEqual(r.state.model, {x: 2});
assert.strictEqual(r.error, null);

// respuesta con error: se avisa y se CONSERVA el estado anterior
r = A.mergeState(prev, { model: {x: 9}, scene: "s", step: 0, error: "op desconocida: foo" });
assert.strictEqual(r.error, "op desconocida: foo");
assert.deepStrictEqual(r.state.model, {x: 9}, "el server igual manda estado válido");

// respuesta rota (400/500, sin model): no se pisa nada
r = A.mergeState(prev, { error: "Boom: qué se yo" });
assert.strictEqual(r.state, prev, "la UI no se queda sin modelo");
assert.strictEqual(r.error, "Boom: qué se yo");
r = A.mergeState(prev, null);
assert.strictEqual(r.state, prev);
assert.ok(r.error, "el fetch fallido también se avisa");
console.log("STATE GREEN");
