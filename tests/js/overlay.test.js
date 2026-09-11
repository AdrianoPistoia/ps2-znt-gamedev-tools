const assert = require("assert");
const A = require(require("path").join(__dirname, "../../znt/web/static/logic.js"));

/* What gets drawn over the stage and why. While editing, NOTHING may dim the
   whole thing without saying what is going on. */
let o = A.stageOverlay({ play: false, choices: [], say: {}, showDialog: true });
assert.strictEqual(o.dialog, true, "the dialogue box is visible");
assert.strictEqual(o.choices, false);
assert.strictEqual(o.scrim, 0, "no scrim");

o = A.stageOverlay({ play: false, choices: [{}], say: null, showDialog: true });
assert.strictEqual(o.choices, true, "choices are previewed");
assert.ok(o.scrim > 0 && o.scrim <= 0.25, `while editing the scrim is soft: ${o.scrim}`);
assert.strictEqual(o.interactive, false, "no picking an option while editing");
assert.ok(/preview/i.test(o.label), o.label);

o = A.stageOverlay({ play: true, choices: [{}], say: null, showDialog: true });
assert.strictEqual(o.scrim, 0.6, "in Play it does, like in the game");
assert.strictEqual(o.interactive, true);
assert.strictEqual(o.label, "", "no editor notices in Play");

o = A.stageOverlay({ play: false, choices: [{}], say: {}, showDialog: false });
assert.deepStrictEqual([o.dialog, o.choices, o.scrim], [false, false, 0],
                       "with the eye off nothing is covered");
o = A.stageOverlay({ play: true, choices: [], say: {}, showDialog: false });
assert.strictEqual(o.dialog, true, "but in Play the dialogue shows anyway");
console.log("OVERLAY GREEN");
