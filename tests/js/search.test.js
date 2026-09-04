const assert = require("assert");
const A = require(require("path").join(__dirname, "../../znt/web/static/logic.js"));

/* --- selección múltiple en el timeline --- */
let r = A.clickSelect([2], 2, 5, {});
assert.deepStrictEqual(r, { sel: [5], anchor: 5 }, "click simple: sólo ese");
r = A.clickSelect([2], 2, 5, { shift: true });
assert.deepStrictEqual(r, { sel: [2, 3, 4, 5], anchor: 2 }, "shift: rango desde el ancla");
r = A.clickSelect([5], 5, 2, { shift: true });
assert.deepStrictEqual(r.sel, [2, 3, 4, 5], "rango hacia atrás también");
r = A.clickSelect([1, 3], 3, 5, { ctrl: true });
assert.deepStrictEqual(r, { sel: [1, 3, 5], anchor: 5 }, "ctrl: suma");
r = A.clickSelect([1, 3, 5], 5, 3, { ctrl: true });
assert.deepStrictEqual(r.sel, [1, 5], "ctrl sobre uno elegido: lo saca");
r = A.clickSelect([], -1, 4, { shift: true });
assert.deepStrictEqual(r.sel, [4], "shift sin ancla = click simple");

/* --- búsqueda en diálogos y opciones --- */
const M = { order: ["s", "t"], scenes: {
  s: [{ op: "bg" }, { op: "say", who: "a", text: "Vamos a la Torre" },
      { op: "choice", options: [{ label: "Ir a la torre", target: "t" }, { label: "No", target: "s" }] }],
  t: [{ op: "say", who: "b", text: "torre, al fin" }, { op: "end" }] } };
let res = A.searchSteps(M, "torre");
assert.deepStrictEqual(res.map(x => [x.scene, x.step]), [["s", 1], ["s", 2], ["t", 0]], "sin distinguir mayúsculas, en orden");
assert.ok(res[1].text.includes("Ir a la torre"), "las opciones del choice cuentan");
assert.deepStrictEqual(A.searchSteps(M, ""), []);
assert.deepStrictEqual(A.searchSteps(M, "zzz"), []);
console.log("SEARCH GREEN");
