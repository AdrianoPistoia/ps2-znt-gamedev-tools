const assert = require("assert");
const A = require(require("path").join(__dirname, "../../znt/web/static/logic.js"));

/* --- pistas por tipo, como un editor de video --- */
assert.deepStrictEqual(A.LANES.map(l => l.key),
                       ["fondo", "personajes", "diálogo", "audio", "flujo"]);
assert.strictEqual(A.laneOf("bg"), 0);
["show", "hide", "animate"].forEach(o => assert.strictEqual(A.laneOf(o), 1, o));
assert.strictEqual(A.laneOf("say"), 2);
["bgm", "se"].forEach(o => assert.strictEqual(A.laneOf(o), 3, o));
["choice", "goto", "end"].forEach(o => assert.strictEqual(A.laneOf(o), 4, o));
assert.strictEqual(A.laneOf("loquesea"), 4, "lo desconocido cae en flujo");

/* --- geometría de los clips: x por índice, y por pista --- */
const view = { cw: 100, lh: 22, gap: 2 };
let r = A.clipRect({ op: "say" }, 2, view);
assert.deepStrictEqual(r, { x: 200, y: 44, w: 98, h: 20, lane: 2 });
assert.strictEqual(A.clipRect({ op: "bg" }, 0, view).y, 0, "primera pista arriba");

/* --- soltar: el índice destino sale de la x --- */
assert.strictEqual(A.dropIndex(240, view, 5), 2);
assert.strictEqual(A.dropIndex(260, view, 5), 3, "más allá de la mitad cae en el siguiente");
assert.strictEqual(A.dropIndex(-90, view, 5), 0, "no se sale por la izquierda");
assert.strictEqual(A.dropIndex(9999, view, 5), 4, "ni por la derecha");
console.log("TIMELINE GREEN");
