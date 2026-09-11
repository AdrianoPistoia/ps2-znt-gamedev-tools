const assert = require("assert");
const A = require(require("path").join(__dirname, "../../znt/web/static/logic.js"));

/* --- scrubbable numeric fields (Blender/AE style) --- */
assert.strictEqual(A.scrubValue(100, 0, {}), 100, "no drag, no change");
assert.strictEqual(A.scrubValue(100, 10, {}), 110, "1 px = 1 unit");
assert.strictEqual(A.scrubValue(100, 3, {step: 5}), 115, "step of 5");
assert.strictEqual(A.scrubValue(100, 10, {fine: true}), 103, "fine: a quarter");
assert.strictEqual(A.scrubValue(10, -100, {min: 0}), 0, "never below the minimum");
assert.strictEqual(A.scrubValue(390, 100, {max: 400}), 400, "nor above the maximum");
assert.strictEqual(A.scrubValue(null, 5, {def: 100}), 105, "empty starts from the default");
assert.ok(Number.isInteger(A.scrubValue(100, 7, {fine: true})), "always an integer");
console.log("INSPECTOR GREEN");
