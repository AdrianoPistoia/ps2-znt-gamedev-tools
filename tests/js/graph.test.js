const assert = require("assert");
const A = require(require("path").join(__dirname, "../../znt/web/static/logic.js"));

const M = { start: "a", order: ["a", "b", "c", "orphan"], scenes: {
  a: [{ op: "say", who: "x", text: "." }, { op: "choice", options: [{ label: "go", target: "b" }, { label: "no", target: "c" }] }],
  b: [{ op: "goto", target: "c" }],
  c: [{ op: "end" }],
  orphan: [{ op: "say", who: "x", text: "no way out" }],
} };
const g = A.sceneGraph(M);
const byId = Object.fromEntries(g.nodes.map(n => [n.id, n]));
assert.deepStrictEqual(g.nodes.map(n => n.id), ["a", "b", "c", "orphan"], "every scene");
assert.strictEqual(byId.a.depth, 0, "the start scene at the top");
assert.strictEqual(byId.b.depth, 1); assert.strictEqual(byId.c.depth, 1, "c: shortest path (a leads to it directly)");
assert.ok(byId.orphan.depth > byId.c.depth, "unreachable goes last");
assert.strictEqual(byId.a.start, true); assert.strictEqual(byId.b.start, false);
assert.strictEqual(byId.orphan.dead, true, "no end/goto/choice");
assert.strictEqual(byId.c.dead, false, "end is not a dead end");
assert.deepStrictEqual(g.edges.map(e => [e.from, e.to, e.label]),
  [["a", "b", "go"], ["a", "c", "no"], ["b", "c", ""]], "edges in order, labelled from the choice");
assert.ok(g.nodes.every(n => Number.isFinite(n.x) && Number.isFinite(n.y)), "positions to draw with");
assert.ok(byId.b.x !== byId.c.x || byId.b.y !== byId.c.y, "no overlap");
assert.deepStrictEqual(A.sceneGraph({ start: "s", order: ["s"], scenes: { s: [] } }).edges, []);
console.log("GRAPH GREEN");
