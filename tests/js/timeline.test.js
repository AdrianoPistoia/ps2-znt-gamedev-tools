const assert = require("assert");
const A = require(require("path").join(__dirname, "../../znt/web/static/logic.js"));

/* --- one lane per kind, like a video editor --- */
assert.deepStrictEqual(A.LANES.map(l => l.key),
                       ["background", "characters", "dialogue", "audio", "flow"]);
assert.strictEqual(A.laneOf("bg"), 0);
["show", "hide", "animate"].forEach(o => assert.strictEqual(A.laneOf(o), 1, o));
assert.strictEqual(A.laneOf("say"), 2);
["bgm", "se"].forEach(o => assert.strictEqual(A.laneOf(o), 3, o));
["choice", "goto", "end"].forEach(o => assert.strictEqual(A.laneOf(o), 4, o));
assert.strictEqual(A.laneOf("whatever"), 4, "unknown ops fall into flow");

/* --- clip geometry: x by index, y by lane --- */
const view = { cw: 100, lh: 22, gap: 2 };
let r = A.clipRect({ op: "say" }, 2, view);
assert.deepStrictEqual(r, { x: 200, y: 44, w: 98, h: 20, lane: 2 });
assert.strictEqual(A.clipRect({ op: "bg" }, 0, view).y, 0, "first lane on top");

/* --- drop: the target index comes from x --- */
assert.strictEqual(A.dropIndex(240, view, 5), 2);
assert.strictEqual(A.dropIndex(260, view, 5), 3, "past the midpoint lands on the next one");
assert.strictEqual(A.dropIndex(-90, view, 5), 0, "does not run off the left");
assert.strictEqual(A.dropIndex(9999, view, 5), 4, "nor off the right");
console.log("TIMELINE GREEN");
