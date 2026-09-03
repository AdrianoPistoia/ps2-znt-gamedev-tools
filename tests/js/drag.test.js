const assert = require("assert");
const A = require(require("path").join(__dirname,"../../znt/web/static/logic.js"));
const near = (a,b,m)=>assert.ok(Math.abs(a-b)<1e-6,`${m}: ${a} != ${b}`);
const st = {w:640,h:448};

// pantalla -> coords del stage (el stage puede estar escalado por CSS)
const rect = {left:100, top:50, width:1280, height:896};   // 2x
let p = A.stageXY(100+640, 50+448, rect, st);
near(p.x, 320, "stageXY x"); near(p.y, 224, "stageXY y");

// snap: engancha dentro del umbral, alinea con otros, libre fuera
assert.deepStrictEqual(A.snap(175, [0,-180,180], 12), {v:180, hit:true});
assert.deepStrictEqual(A.snap(160, [0,-180,180], 12), {v:160, hit:false});
assert.deepStrictEqual(A.snap(6,   [0], 12),          {v:0,   hit:true});
assert.deepStrictEqual(A.snap(70,  [0,64], 12),       {v:64,  hit:true});

// arrastre: de un punto del stage al x/y de la capa (respeta zoom y anclaje)
const l = {x:0,y:0,zoom:100,w:200,h:300};
// agarrada justo en su esquina sup-izq => grab (0,0); soltar en el centro-piso
const left0 = st.w/2 + l.x - l.w/2, top0 = st.h - l.h + l.y;   // 220, 148
let d = A.dragTo(l, st, 0, 0, left0 + 50, top0 - 20);
near(d.x, 50, "dragTo x"); near(d.y, -20, "dragTo y");
// con zoom 200% el ancho es 400 => el centrado cambia, pero el resultado es coherente
const l2 = {x:0,y:0,zoom:200,w:200,h:300};
const left2 = st.w/2 + l2.x - 400/2, top2 = st.h - 600 + l2.y;
d = A.dragTo(l2, st, 0, 0, left2 + 10, top2 + 5);
near(d.x, 10, "dragTo x zoom"); near(d.y, 5, "dragTo y zoom");

// objetivos de snap a partir de las otras capas
const t = A.snapTargets([{id:"a",x:64,y:0},{id:"b",x:-90,y:12}], "b");
assert.deepStrictEqual(t.xs, [0,-180,180,64], "targets x");
assert.deepStrictEqual(t.ys, [0,0], "targets y");
console.log("DRAG GREEN");
