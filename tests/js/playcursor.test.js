const assert = require("assert");
const A = require(require("path").join(__dirname, "../../znt/web/static/logic.js"));

/* The timeline follows Play: while playing, scene and step are the runtime's
   (which may have jumped scenes via a choice/goto). */
const edit = { scene: "s", step: 3, play: null };
assert.deepStrictEqual(A.playCursor(edit), { scene: "s", step: 3, playing: false });
const playing = { scene: "s", step: 3, play: { scene: "t", step: 0 } };
assert.deepStrictEqual(A.playCursor(playing), { scene: "t", step: 0, playing: true });
assert.deepStrictEqual(A.playCursor({ scene: "s", step: -1, play: null }),
                       { scene: "s", step: -1, playing: false });
console.log("PLAYCURSOR GREEN");
