const assert = require("assert");
const A = require(require("path").join(__dirname, "../../znt/web/static/logic.js"));

/* --- layers: frontmost (highest z) on top, like Figma/Blender --- */
const layers = [
  { id: "b", name: "Leo", z: 12, url: null },
  { id: "a", name: "Ana", z: 20, url: "/api/asset?f=ana.png" },
  { id: "c", name: "Cy",  z: 12, url: null },
];
const rows = A.outlineRows(layers);
assert.deepStrictEqual(rows.map(r => r.id), ["a", "b", "c"], "z desc, ties by id");
assert.strictEqual(rows[0].sprite, true, "knows whether it has an image or a placeholder");
assert.strictEqual(rows[1].sprite, false);
assert.deepStrictEqual(A.outlineRows([]), []);

/* --- double click on a layer: jump to the step that shows it --- */
const steps = [
  { op: "bg" }, { op: "show", id: "a" }, { op: "say", who: "a" },
  { op: "show", id: "b" }, { op: "show", id: "a" }, { op: "end" },
];
assert.strictEqual(A.showStepIndex(steps, "a", 5), 4, "the last show at or before the step");
assert.strictEqual(A.showStepIndex(steps, "a", 3), 1, "does not look past the current step");
assert.strictEqual(A.showStepIndex(steps, "b", 5), 3);
assert.strictEqual(A.showStepIndex(steps, "z", 5), -1, "not there");
assert.strictEqual(A.showStepIndex(steps, "a", -1), 4, "no step selected: looks at the whole scene");
console.log("OUTLINER GREEN");
