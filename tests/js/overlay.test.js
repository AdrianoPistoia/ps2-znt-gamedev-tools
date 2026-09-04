const assert = require("assert");
const A = require(require("path").join(__dirname, "../../znt/web/static/logic.js"));

/* Qué se dibuja encima del escenario y por qué. En edición NO se puede oscurecer
   todo sin decir qué está pasando. */
let o = A.stageOverlay({ play: false, choices: [], say: {}, showDialog: true });
assert.strictEqual(o.dialog, true, "el cuadro de diálogo se ve");
assert.strictEqual(o.choices, false);
assert.strictEqual(o.scrim, 0, "sin velo");

o = A.stageOverlay({ play: false, choices: [{}], say: null, showDialog: true });
assert.strictEqual(o.choices, true, "las opciones se previsualizan");
assert.ok(o.scrim > 0 && o.scrim <= 0.25, `en edición el velo es suave: ${o.scrim}`);
assert.strictEqual(o.interactive, false, "editando no se elige una opción");
assert.ok(/previsualizaci/i.test(o.label), o.label);

o = A.stageOverlay({ play: true, choices: [{}], say: null, showDialog: true });
assert.strictEqual(o.scrim, 0.6, "en Play sí, como en el juego");
assert.strictEqual(o.interactive, true);
assert.strictEqual(o.label, "", "en Play no hay carteles de editor");

o = A.stageOverlay({ play: false, choices: [{}], say: {}, showDialog: false });
assert.deepStrictEqual([o.dialog, o.choices, o.scrim], [false, false, 0],
                       "con el ojo apagado no se tapa nada");
o = A.stageOverlay({ play: true, choices: [], say: {}, showDialog: false });
assert.strictEqual(o.dialog, true, "pero en Play el diálogo va igual");
console.log("OVERLAY GREEN");
