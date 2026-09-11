const assert = require("assert");
const A = require(require("path").join(__dirname, "../../znt/web/static/logic.js"));

/* Typing effect: how many characters are shown at t ms, at cps chars/sec. */
assert.strictEqual(A.typedChars("hello world", 0, 40), 0);
assert.strictEqual(A.typedChars("hello world", 100, 40), 4, "40 cps -> 4 at 100 ms");
assert.strictEqual(A.typedChars("hello world", 5000, 40), 11, "never past the length");
assert.strictEqual(A.typedChars("hello", 100, 0), 5, "cps 0 = no effect: everything at once");
assert.strictEqual(A.typedChars("", 100, 40), 0);
console.log("TYPING GREEN");
