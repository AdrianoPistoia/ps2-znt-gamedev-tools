const assert = require("assert");
const A = require(require("path").join(__dirname, "../../znt/web/static/logic.js"));

const prev = { model: {x: 1}, scene: "s", step: 2 };

// normal response: adopted
let r = A.mergeState(prev, { model: {x: 2}, scene: "s", step: 3 });
assert.deepStrictEqual(r.state.model, {x: 2});
assert.strictEqual(r.error, null);

// response with error: reported, and the previous state is KEPT
r = A.mergeState(prev, { model: {x: 9}, scene: "s", step: 0, error: "unknown op: foo" });
assert.strictEqual(r.error, "unknown op: foo");
assert.deepStrictEqual(r.state.model, {x: 9}, "the server still sends a valid state");

// broken response (400/500, no model): nothing gets overwritten
r = A.mergeState(prev, { error: "Boom: who knows" });
assert.strictEqual(r.state, prev, "the UI is never left without a model");
assert.strictEqual(r.error, "Boom: who knows");
r = A.mergeState(prev, null);
assert.strictEqual(r.state, prev);
assert.ok(r.error, "a failed fetch is reported too");
console.log("STATE GREEN");
