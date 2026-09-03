const assert = require("assert");
const A = require(require("path").join(__dirname, "../../znt/web/static/logic.js"));

/* --- capas: arriba lo que está al frente (z mayor), como en Figma/Blender --- */
const layers = [
  { id: "b", name: "Leo", z: 12, url: null },
  { id: "a", name: "Ana", z: 20, url: "/api/asset?f=ana.png" },
  { id: "c", name: "Cy",  z: 12, url: null },
];
const rows = A.outlineRows(layers);
assert.deepStrictEqual(rows.map(r => r.id), ["a", "b", "c"], "z desc, empate por id");
assert.strictEqual(rows[0].sprite, true, "sabe si tiene imagen o placeholder");
assert.strictEqual(rows[1].sprite, false);
assert.deepStrictEqual(A.outlineRows([]), []);

/* --- doble click en una capa: llevar al paso que la muestra --- */
const steps = [
  { op: "bg" }, { op: "show", id: "a" }, { op: "say", who: "a" },
  { op: "show", id: "b" }, { op: "show", id: "a" }, { op: "end" },
];
assert.strictEqual(A.showStepIndex(steps, "a", 5), 4, "el último show en o antes del paso");
assert.strictEqual(A.showStepIndex(steps, "a", 3), 1, "no mira más allá del paso actual");
assert.strictEqual(A.showStepIndex(steps, "b", 5), 3);
assert.strictEqual(A.showStepIndex(steps, "z", 5), -1, "no está");
assert.strictEqual(A.showStepIndex(steps, "a", -1), 4, "sin paso elegido: mira toda la escena");
console.log("OUTLINER GREEN");
