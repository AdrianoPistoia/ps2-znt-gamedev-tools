const assert = require("assert");
const A = require(require("path").join(__dirname, "../../znt/web/static/logic.js"));

const k = (key, mod) => A.resolveKey(Object.assign({key}, mod || {}));
assert.strictEqual(k("z", {ctrlKey:true}), "undo");
assert.strictEqual(k("y", {ctrlKey:true}), "redo");
assert.strictEqual(k("Z", {ctrlKey:true, shiftKey:true}), "redo", "el otro rehacer de siempre");
assert.strictEqual(k("s", {ctrlKey:true}), "save");
assert.strictEqual(k("ArrowLeft"), "prev");
assert.strictEqual(k("ArrowRight"), "next");
assert.strictEqual(k(" "), "play");
assert.strictEqual(k("Escape"), "stop");
assert.strictEqual(k("g"), "guides");
assert.strictEqual(k("G"), "guides", "no importa la mayúscula");
assert.strictEqual(k("Delete"), "del_step");
assert.strictEqual(k("?"), "help");
assert.strictEqual(k("q"), null, "lo no mapeado no hace nada");
assert.strictEqual(k("z"), null, "sin ctrl no es deshacer");

// el overlay de ayuda se arma solo con esto: todo comando necesita descripción
const seen = new Set();
for (const e of A.KEYMAP) {
  assert.ok(e.keys && e.desc, `entrada incompleta: ${JSON.stringify(e)}`);
  assert.ok("cmd" in e, "cmd explícito (null = sólo informativo, como Shift)");
  assert.ok(!seen.has(e.keys), `atajo duplicado: ${e.keys}`);
  seen.add(e.keys);
}
console.log("KEYMAP GREEN");
