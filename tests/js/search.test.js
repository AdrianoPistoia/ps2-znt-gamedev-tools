const assert = require("assert");
const A = require(require("path").join(__dirname, "../../znt/web/static/logic.js"));

/* --- multi-selection in the timeline --- */
let r = A.clickSelect([2], 2, 5, {});
assert.deepStrictEqual(r, { sel: [5], anchor: 5 }, "plain click: only that one");
r = A.clickSelect([2], 2, 5, { shift: true });
assert.deepStrictEqual(r, { sel: [2, 3, 4, 5], anchor: 2 }, "shift: range from the anchor");
r = A.clickSelect([5], 5, 2, { shift: true });
assert.deepStrictEqual(r.sel, [2, 3, 4, 5], "backwards range too");
r = A.clickSelect([1, 3], 3, 5, { ctrl: true });
assert.deepStrictEqual(r, { sel: [1, 3, 5], anchor: 5 }, "ctrl: adds");
r = A.clickSelect([1, 3, 5], 5, 3, { ctrl: true });
assert.deepStrictEqual(r.sel, [1, 5], "ctrl on a selected one: removes it");
r = A.clickSelect([], -1, 4, { shift: true });
assert.deepStrictEqual(r.sel, [4], "shift without anchor = plain click");

/* --- search in dialogue and choices --- */
const M = { order: ["s", "t"], scenes: {
  s: [{ op: "bg" }, { op: "say", who: "a", text: "Let's go to the Tower" },
      { op: "choice", options: [{ label: "Go to the tower", target: "t" }, { label: "No", target: "s" }] }],
  t: [{ op: "say", who: "b", text: "the tower, at last" }, { op: "end" }] } };
let res = A.searchSteps(M, "tower");
assert.deepStrictEqual(res.map(x => [x.scene, x.step]), [["s", 1], ["s", 2], ["t", 0]], "case-insensitive, in order");
assert.ok(res[1].text.includes("Go to the tower"), "choice options count");
assert.deepStrictEqual(A.searchSteps(M, ""), []);
assert.deepStrictEqual(A.searchSteps(M, "zzz"), []);
console.log("SEARCH GREEN");
