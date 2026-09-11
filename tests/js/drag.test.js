const assert = require("assert");
const A = require(require("path").join(__dirname,"../../znt/web/static/logic.js"));
const near = (a,b,m)=>assert.ok(Math.abs(a-b)<1e-6,`${m}: ${a} != ${b}`);
const st = {w:640,h:448};

// screen -> stage coords (the stage may be scaled by CSS)
const rect = {left:100, top:50, width:1280, height:896};   // 2x
let p = A.stageXY(100+640, 50+448, rect, st);
near(p.x, 320, "stageXY x"); near(p.y, 224, "stageXY y");

// snap: latches within the threshold, aligns with others, free outside it
assert.deepStrictEqual(A.snap(175, [0,-180,180], 12), {v:180, hit:true});
assert.deepStrictEqual(A.snap(160, [0,-180,180], 12), {v:160, hit:false});
assert.deepStrictEqual(A.snap(6,   [0], 12),          {v:0,   hit:true});
assert.deepStrictEqual(A.snap(70,  [0,64], 12),       {v:64,  hit:true});

// drag: from a stage point to the layer's x/y (honours zoom and anchor)
const l = {x:0,y:0,zoom:100,w:200,h:300};
// grabbed right at its top-left corner => grab (0,0); drop at centre-floor
const left0 = st.w/2 + l.x - l.w/2, top0 = st.h - l.h + l.y;   // 220, 148
let d = A.dragTo(l, st, 0, 0, left0 + 50, top0 - 20);
near(d.x, 50, "dragTo x"); near(d.y, -20, "dragTo y");
// at 200% zoom the width is 400 => the centring changes, but the result is consistent
const l2 = {x:0,y:0,zoom:200,w:200,h:300};
const left2 = st.w/2 + l2.x - 400/2, top2 = st.h - 600 + l2.y;
d = A.dragTo(l2, st, 0, 0, left2 + 10, top2 + 5);
near(d.x, 10, "dragTo x zoom"); near(d.y, 5, "dragTo y zoom");

// snap targets derived from the other layers
const t = A.snapTargets([{id:"a",x:64,y:0},{id:"b",x:-90,y:12}], "b");
assert.deepStrictEqual(t.xs, [0,-180,180,64], "targets x");
assert.deepStrictEqual(t.ys, [0,0], "targets y");
console.log("DRAG GREEN");
