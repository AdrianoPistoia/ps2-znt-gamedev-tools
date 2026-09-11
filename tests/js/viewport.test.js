const assert = require("assert");
const A = require(require("path").join(__dirname, "../../znt/web/static/logic.js"));

/* --- handles: dragging a corner changes the zoom, not the natural size --- */
const l = { w: 200, h: 300, zoom: 100 };
assert.strictEqual(A.resizeZoom(l, 1, 0), 100, "no movement, no change");
assert.strictEqual(A.resizeZoom(l, 1, 50), 150, "pull 50px to the right over 200 of width");
assert.strictEqual(A.resizeZoom(l, -1, -50), 150, "the left handle is symmetric");
assert.strictEqual(A.resizeZoom(l, 1, -50), 50, "shrink");
assert.strictEqual(A.resizeZoom(l, 1, -400), 10, "lower cap");
assert.strictEqual(A.resizeZoom(l, 1, 9999), 400, "upper cap");
assert.strictEqual(A.resizeZoom({ w: 200, h: 300, zoom: 200 }, 1, 0), 200, "starts from the current zoom");

/* --- guides: cycle off -> centre -> thirds -> safe --- */
assert.deepStrictEqual(A.guides("off"), { xs: [], ys: [], rect: null });
assert.deepStrictEqual(A.guides("center"), { xs: [0.5], ys: [0.5], rect: null });
const t = A.guides("thirds");
assert.deepStrictEqual(t.xs.map(v => +v.toFixed(3)), [0.333, 0.667]);
assert.deepStrictEqual(t.ys.map(v => +v.toFixed(3)), [0.333, 0.667]);
assert.deepStrictEqual(A.guides("safe").rect, { x: 0.05, y: 0.05, w: 0.9, h: 0.9 });
assert.strictEqual(A.nextGuide("off"), "center");
assert.strictEqual(A.nextGuide("safe"), "off", "closes the cycle");
console.log("VIEWPORT GREEN");
