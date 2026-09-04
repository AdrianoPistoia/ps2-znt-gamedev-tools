const assert = require("assert");
const A = require(require("path").join(__dirname, "../../znt/web/static/logic.js"));

const M = { start: "a", order: ["a", "b", "c", "huerfana"], scenes: {
  a: [{ op: "say", who: "x", text: "." }, { op: "choice", options: [{ label: "ir", target: "b" }, { label: "no", target: "c" }] }],
  b: [{ op: "goto", target: "c" }],
  c: [{ op: "end" }],
  huerfana: [{ op: "say", who: "x", text: "sin salida" }],
} };
const g = A.sceneGraph(M);
const byId = Object.fromEntries(g.nodes.map(n => [n.id, n]));
assert.deepStrictEqual(g.nodes.map(n => n.id), ["a", "b", "c", "huerfana"], "todas las escenas");
assert.strictEqual(byId.a.depth, 0, "la de inicio arriba");
assert.strictEqual(byId.b.depth, 1); assert.strictEqual(byId.c.depth, 1, "c: camino más corto (a la lleva directo)");
assert.ok(byId.huerfana.depth > byId.c.depth, "lo inalcanzable va al final");
assert.strictEqual(byId.a.start, true); assert.strictEqual(byId.b.start, false);
assert.strictEqual(byId.huerfana.dead, true, "sin end/goto/choice");
assert.strictEqual(byId.c.dead, false, "end no es dead-end");
assert.deepStrictEqual(g.edges.map(e => [e.from, e.to, e.label]),
  [["a", "b", "ir"], ["a", "c", "no"], ["b", "c", ""]], "aristas en orden, con etiqueta del choice");
assert.ok(g.nodes.every(n => Number.isFinite(n.x) && Number.isFinite(n.y)), "posiciones para dibujar");
assert.ok(byId.b.x !== byId.c.x || byId.b.y !== byId.c.y, "no se pisan");
assert.deepStrictEqual(A.sceneGraph({ start: "s", order: ["s"], scenes: { s: [] } }).edges, []);
console.log("GRAPH GREEN");
