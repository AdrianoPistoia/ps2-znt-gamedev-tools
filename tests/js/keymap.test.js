const assert = require("assert");
const A = require(require("path").join(__dirname, "../../znt/web/static/logic.js"));

const k = (key, mod) => A.resolveKey(Object.assign({key}, mod || {}));
assert.strictEqual(k("z", {ctrlKey:true}), "undo");
assert.strictEqual(k("y", {ctrlKey:true}), "redo");
assert.strictEqual(k("Z", {ctrlKey:true, shiftKey:true}), "redo", "the other usual redo");
assert.strictEqual(k("s", {ctrlKey:true}), "save");
assert.strictEqual(k("ArrowLeft"), "prev");
assert.strictEqual(k("ArrowRight"), "next");
assert.strictEqual(k(" "), "play");
assert.strictEqual(k("Escape"), "stop");
assert.strictEqual(k("g"), "guides");
assert.strictEqual(k("G"), "guides", "case does not matter");
assert.strictEqual(k("Delete"), "del_step");
assert.strictEqual(k("?"), "help");
assert.strictEqual(k("q"), null, "unmapped keys do nothing");
assert.strictEqual(k("z"), null, "without ctrl it is not undo");

// the help overlay is built from this alone: every command needs a description
const seen = new Set();
for (const e of A.KEYMAP) {
  assert.ok(e.keys && e.desc, `incomplete entry: ${JSON.stringify(e)}`);
  assert.ok("cmd" in e, "explicit cmd (null = informational only, like Shift)");
  assert.ok(!seen.has(e.keys), `duplicate shortcut: ${e.keys}`);
  seen.add(e.keys);
}
console.log("KEYMAP GREEN");
