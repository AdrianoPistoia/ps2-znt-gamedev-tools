const assert = require("assert");
const A = require(require("path").join(__dirname, "../../znt/web/static/logic.js"));

/* --- splitters: never crush a pane or its neighbour --- */
assert.strictEqual(A.clampPane(300, 1200, 180, 400), 300, "a comfortable value passes through");
assert.strictEqual(A.clampPane(50, 1200, 180, 400), 180, "own minimum");
assert.strictEqual(A.clampPane(900, 1200, 180, 400), 800, "leaves the neighbour's minimum");
assert.strictEqual(A.clampPane(500, 500, 180, 400), 180, "small window: own minimum wins");

/* --- viewport: the stage fits whole and centred (letterbox) --- */
let r = A.fitRect(1000, 400, 640, 448);          // wide container -> spare room on the sides
assert.strictEqual(r.h, 400, "height is the limit");
assert.strictEqual(Math.round(r.w), Math.round(400 * 640 / 448), "keeps aspect");
assert.strictEqual(Math.round(r.left), Math.round((1000 - r.w) / 2), "centred in x");
assert.strictEqual(r.top, 0, "no bars on top");

r = A.fitRect(320, 1000, 640, 448);              // tall container -> spare room above and below
assert.strictEqual(r.w, 320, "width is the limit");
assert.strictEqual(Math.round(r.h), Math.round(320 * 448 / 640), "keeps aspect");
assert.strictEqual(Math.round(r.top), Math.round((1000 - r.h) / 2), "centred in y");

r = A.fitRect(1280, 896, 640, 448);
assert.strictEqual(r.scale, 2, "scale = how much the stage is enlarged");
assert.deepStrictEqual(A.fitRect(0, 0, 640, 448), { w: 0, h: 0, left: 0, top: 0, scale: 0 },
                       "container not measured yet");
console.log("SHELL GREEN");
