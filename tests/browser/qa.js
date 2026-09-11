#!/usr/bin/env node
/* Real QA: drives chromium over CDP (clicks, keyboard, drag) against the
 * real server, and collects the page's JS exceptions.
 *   node tests/browser/qa.js            -> runs every flow
 *   node tests/browser/qa.js play drag  -> only those
 * No deps: native WebSocket and fetch from Node ≥ 22. */
"use strict";
const { spawn } = require("child_process");
const fs = require("fs"), os = require("os"), path = require("path"), assert = require("assert");
const REPO = path.join(__dirname, "..", "..");
const ONLY = process.argv.slice(2);

/* ---------- test project ---------- */
const DIR = fs.mkdtempSync(path.join(os.tmpdir(), "vnqa-"));
const VN = path.join(DIR, "demo.vn");
const VN_TEXT = `title: QA
character ana "Ana" #7cc4ff
character leo "Leo" #f0a92e
sprite ana ana.png
scene intro
  bg grad:#101828,#2a3a5f
  show ana left
  show leo right zoom=120
  ana: Did you bring the map?
  leo: It is in the tower.
  animate ana wave amp=8 speed=2
  choice
  - Go to the tower -> tower
  - Stay -> intro
scene tower
  bg #1a1020
  bgm theme.wav
  show leo center
  leo: We made it.
  se hit.wav
  leo: The end.
  end
`;
fs.writeFileSync(VN, VN_TEXT);
for (const f of ["theme.wav", "hit.wav"])                  // minimal WAV (header only)
  fs.writeFileSync(path.join(DIR, f), Buffer.from("RIFF\x24\x00\x00\x00WAVEfmt ", "latin1"));
{ // opaque 40x60 PNG, no deps
  const zlib = require("zlib");
  const w = 40, h = 60, raw = Buffer.alloc((w * 3 + 1) * h);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++)
    raw.set([120, 180, 240], y * (w * 3 + 1) + 1 + x * 3);
  const crc = b => { let c = ~0; for (const v of b) { c ^= v; for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (0xEDB88320 & -(c & 1)); } return ~c >>> 0; };
  const chunk = (t, d) => { const len = Buffer.alloc(4); len.writeUInt32BE(d.length);
    const td = Buffer.concat([Buffer.from(t), d]); const c = Buffer.alloc(4); c.writeUInt32BE(crc(td));
    return Buffer.concat([len, td, c]); };
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr.set([8, 2, 0, 0, 0], 8);
  fs.writeFileSync(path.join(DIR, "ana.png"), Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]),
    chunk("IHDR", ihdr), chunk("IDAT", zlib.deflateSync(raw)), chunk("IEND", Buffer.alloc(0))]));
}

/* ---------- processes ---------- */
const waitLine = (proc, stream, re, what) => new Promise((res, rej) => {
  let buf = ""; const t = setTimeout(() => rej(new Error("timeout waiting for " + what + "\n" + buf)), 15000);
  proc[stream].on("data", d => { buf += d; const m = buf.match(re); if (m) { clearTimeout(t); res(m); } });
  proc.on("exit", c => rej(new Error(what + " exited (" + c + ")\n" + buf)));
});
const kill = p => { try { p.kill("SIGKILL"); } catch (e) {} };

async function main() {
  const srv = spawn("python3", ["-m", "znt", "web", VN, "--port", "0", "--no-browser"],
                    { cwd: REPO, env: { ...process.env, PYTHONPATH: REPO, PYTHONUNBUFFERED: "1" } });
  const [, url] = await waitLine(srv, "stdout", /at (http:\/\/127\.0\.0\.1:\d+\/)/, "the server");
  const chrome = spawn("chromium", ["--headless=new", "--disable-gpu", "--no-first-run",
    "--remote-debugging-port=0", "--remote-allow-origins=*", "--window-size=1400,900",
    "--user-data-dir=" + path.join(DIR, "profile"), "about:blank"]);
  const [, dbg] = await waitLine(chrome, "stderr", /DevTools listening on ws:\/\/127\.0\.0\.1:(\d+)\//, "chromium");
  const tgt = await (await fetch(`http://127.0.0.1:${dbg}/json/new?${url}`, { method: "PUT" })).json();

  /* ---------- CDP client ---------- */
  const ws = new WebSocket(tgt.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let seq = 0; const pend = {}; const jserr = [];
  ws.onmessage = e => {
    const m = JSON.parse(e.data);
    if (m.id && pend[m.id]) { pend[m.id](m); delete pend[m.id]; return; }
    if (m.method === "Runtime.exceptionThrown") {
      const d = m.params.exceptionDetails; jserr.push((d.exception && d.exception.description) || d.text);
    } else if (m.method === "Runtime.consoleAPICalled" && m.params.type === "error") {
      jserr.push("console.error: " + m.params.args.map(a => a.value || a.description).join(" "));
    }
  };
  const send = (method, params = {}) => new Promise((res, rej) => {
    const id = ++seq;
    pend[id] = m => m.error ? rej(new Error(method + ": " + JSON.stringify(m.error))) : res(m.result);
    ws.send(JSON.stringify({ id, method, params }));
  });
  await send("Runtime.enable"); await send("Page.enable");

  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const js = async expr => {
    const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error("js failed: " + ((r.exceptionDetails.exception || {}).description || r.exceptionDetails.text) + "\n  in: " + expr.slice(0, 120));
    return r.result.value;
  };
  /* wait for the app to finish what it was doing */
  const settle = async () => {
    for (let i = 0; i < 100; i++) { await sleep(40); if (!(await js("window.__vns && window.__vns.busy"))) break; }
    await js("new Promise(r => requestAnimationFrame(() => setTimeout(r, 30)))");
  };
  /* a clip outside the visible part of the timeline is scrolled into view before measuring
     (as a person would); the stage is left alone (overflow hidden) */
  const rect = async sel => js(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e) return null;
    if (e.closest("#tlbody")) e.scrollIntoView({ block: "nearest", inline: "nearest" });
    const r = e.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height }; })()`);
  const mouse = (type, x, y, extra = {}) => send("Input.dispatchMouseEvent", { type, x, y, button: "left", clickCount: 1, ...extra });
  const clickAt = async (x, y) => { await mouse("mouseMoved", x, y); await mouse("mousePressed", x, y); await mouse("mouseReleased", x, y); await settle(); };
  const click = async sel => { const r = await rect(sel); assert(r, "missing " + sel); await clickAt(r.x, r.y); };
  const clickText = async (sel, text) => {          // button by its text
    const ok = await js(`(() => { const b = [...document.querySelectorAll(${JSON.stringify(sel)})].find(x => x.textContent.trim().startsWith(${JSON.stringify(text)})); if (!b) return false; b.scrollIntoView(); b.click(); return true; })()`);
    assert(ok, `no ${sel} with text "${text}"`); await settle();
  };
  const drag = async (x1, y1, x2, y2, n = 10) => {
    await mouse("mouseMoved", x1, y1); await mouse("mousePressed", x1, y1);
    for (let i = 1; i <= n; i++) await mouse("mouseMoved", x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n, { buttons: 1 });
    await mouse("mouseReleased", x2, y2); await settle();
  };
  const KEYS = { Escape: 27, Enter: 13, Delete: 46, Tab: 9, ArrowLeft: 37, ArrowRight: 39, " ": 32 };
  const key = async (k, mods = 0) => {
    const code = KEYS[k] || k.toUpperCase().charCodeAt(0);
    const printable = k.length === 1 && !(mods & 2);
    const txt = k === "Enter" ? "\r" : printable ? k : undefined;   // Enter carries text: that is what triggers the submit
    const base = { key: k, code: k.length === 1 ? "Key" + k.toUpperCase() : k, windowsVirtualKeyCode: code, modifiers: mods };
    await send("Input.dispatchKeyEvent", { type: txt !== undefined ? "keyDown" : "rawKeyDown", ...base, text: txt });
    await send("Input.dispatchKeyEvent", { type: "keyUp", ...base }); await settle();
  };
  const CTRL = 2, SHIFT = 8;
  const type = async text => { await send("Input.insertText", { text }); };
  const model = () => js("fetch('/api/model').then(r => r.json())");
  const count = sel => js(`document.querySelectorAll(${JSON.stringify(sel)}).length`);
  const text = sel => js(`(document.querySelector(${JSON.stringify(sel)}) || {}).textContent || ""`);
  const isOpen = sel => js(`!!(document.querySelector(${JSON.stringify(sel)}) || {}).open`);
  const clipOf = async op => {                       // index of the first clip of that kind
    const i = await js(`(() => { const c = [...document.querySelectorAll(".clip")].find(c => c.textContent.startsWith(${JSON.stringify(op)})); return c ? +c.dataset.i : -1; })()`);
    assert(i >= 0, "no clip " + op); return i;
  };
  const dump = () => js(`JSON.stringify({step: S.step, scene: S.scene, play: !!S.play, sel: typeof SEL !== "undefined" ? SEL : null,
    sels: typeof SELS !== "undefined" ? SELS : null, clips: document.querySelectorAll(".clip").length,
    dlg: document.querySelector("#dlg").open, brw: document.querySelector("#brw").open, help: document.querySelector("#help").open,
    toast: document.querySelector("#toast").hidden ? "" : document.querySelector("#toast").textContent,
    active: document.activeElement && (document.activeElement.id || document.activeElement.tagName),
    probs: document.querySelector("#probs").textContent.slice(0, 120)})`);
  const selectValue = async (sel, v) => { await js(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); e.value = ${JSON.stringify(v)}; e.dispatchEvent(new Event("change", {bubbles:true})); })()`); await settle(); };
  const fillInput = async (sel, v) => { await click(sel); await js(`document.querySelector(${JSON.stringify(sel)}).select()`); await type(v); };

  await new Promise(r => setTimeout(r, 800)); await settle();

  /* ---------- flows ---------- */
  const flows = {};
  const flow = (name, fn) => { flows[name] = fn; };

  flow("load", async () => {
    assert.strictEqual(await count(".clip"), 7, "7 steps as clips");
    assert.ok((await js("S.step")) >= 0, "starts with a step selected");
    assert.ok((await text("#props")).length > 20, "the inspector shows something");
    await click('.clip[data-i="0"]');
    assert.strictEqual(await count("#layers li"), 0, "no layers at the bg step");
    assert.ok((await text("#m-zoom")).endsWith("%"), "shows the viewport scale");
  });

  flow("select", async () => {
    await click('.clip[data-i="3"]');
    assert.strictEqual(await js("S.step"), 3);
    assert.strictEqual(await text("#m-op"), "say");
    assert.ok((await text("#text")).includes("map"), "the step's line is on the stage");
    assert.strictEqual(await count("#layers li"), 2, "two layers on stage");
    await key("ArrowRight"); assert.strictEqual(await js("S.step"), 4, "→ moves one step forward");
    await key("ArrowLeft");  assert.strictEqual(await js("S.step"), 3, "← moves back");
  });

  flow("add-say-and-edit", async () => {
    await click('.clip[data-i="3"]');
    await selectValue("#newop", "say");
    await click("#b-step-add");
    assert.strictEqual(await count(".clip"), 8, "a clip was added");
    assert.strictEqual(await js("S.step"), 4, "the new one is selected, right after the previous");
    assert.strictEqual(await count("#props textarea"), 1, "the text is edited in a textarea");
    await fillInput("#props textarea", "New QA line");
    await key("Tab");                                  // blur -> change
    await sleep(200); await settle();
    const m = await model();
    const st = m.model.scenes.intro[4];
    assert.strictEqual(st.op, "say");
    assert.strictEqual(st.text, "New QA line", `the text applied on leaving the field (got: ${JSON.stringify(st.text)})`);
    assert.ok((await text("#text")).includes("New QA line"), "and it shows on the stage");
  });

  flow("undo-redo", async () => {
    const n = await count(".clip");
    await click("#b-step-add");
    assert.strictEqual(await count(".clip"), n + 1);
    await key("z", CTRL);
    assert.strictEqual(await count(".clip"), n, "Ctrl+Z undoes the added step");
    await key("y", CTRL);
    assert.strictEqual(await count(".clip"), n + 1, "Ctrl+Y redoes it");
    await key("z", CTRL);
  });

  flow("play", async () => {
    await click('.clip[data-i="1"]');                  // show ana
    await click("#b-play");
    assert.ok(await js("document.body.classList.contains('playing')"), "Play mode");
    assert.strictEqual(await count(".clip.playing"), 1, "one clip marked");
    assert.strictEqual(await js("S.play.step"), 1, "starts AT the selected step (step by step)");
    assert.strictEqual(await count("#stage .layer"), 1, "only what is there up to that step shows");
    const r = await rect("#stage"); await clickAt(r.x, r.y - 80);
    assert.strictEqual(await js("S.play.step"), 2, "click on screen = one step");
    await key(" ");
    assert.strictEqual(await js("S.play.step"), 3, "Space too");
    assert.ok((await text("#text")).includes("map"), "and now the line shows");
    for (let i = 0; i < 8 && !(await js("S.play.choices.length")); i++) await key(" ");
    assert.strictEqual(await js("S.play.choices.length"), 2, "reaches the choice");
    await clickText("#choices button", "Go to the tower");
    assert.strictEqual(await js("S.play.scene"), "tower", "choosing jumps scene");
    assert.strictEqual(await text("#scenes li.sel span"), "tower", "the scene list follows Play");
    await key("Escape");
    assert.ok(!(await js("document.body.classList.contains('playing')")), "Esc exits");
    assert.strictEqual(await js("S.step"), 1, "returns to the editing selection");
  });

  flow("drag-sprite", async () => {
    await click('.clip[data-i="1"]');
    const before = (await model()).model.scenes.intro[1];
    const r = await rect('.layer[data-id="ana"]'); assert(r, "ana's sprite on the stage");
    await drag(r.x, r.y, r.x + 90, r.y);
    const after = (await model()).model.scenes.intro[1];
    assert.ok((after.x || 0) > (before.x || -180) + 30, `x should grow: ${before.x} -> ${after.x}`);
    assert.strictEqual(await js("SEL"), "ana", "it stays selected");
    assert.ok(!(await js("document.querySelector('#frame').hidden")), "selection frame visible");
  });

  flow("handles-zoom", async () => {
    await click('.clip[data-i="1"]');
    await click('.layer[data-id="ana"]');
    const h = await rect('#frame .hnd[data-h="1"]'); assert(h, "right handle");
    await drag(h.x, h.y, h.x + 40, h.y);
    const z = (await model()).model.scenes.intro[1].zoom;
    assert.ok(z > 100, `zoom should go up: ${z}`);
  });

  flow("file-browser", async () => {
    await click('.clip[data-i="1"]');
    await clickText("#props button", "📁");
    assert.ok(await isOpen("#brw"), "the file browser opens");
    assert.ok((await count("#brw-list li")) > 0, "lists something");
    assert.ok((await text("#brw-crumbs")).includes("/"), "breadcrumbs");
    await clickText("#brw menu button", "Cancel");
    assert.ok(!(await isOpen("#brw")), "it closes");
  });

  flow("new-character-dialog", async () => {
    await click("#b-char");
    assert.ok(await isOpen("#dlg"));
    await type("cy");
    await key("Tab"); await type("Cy");
    await key("Enter");                               // Enter must ACCEPT
    await settle();
    assert.ok(!(await isOpen("#dlg")), "Enter closes the dialog");
    const m = await model();
    assert.ok(m.model.characters.cy, "Enter accepts and creates the character (does not cancel)");
    assert.strictEqual(m.model.characters.cy.name, "Cy");
  });

  flow("choice-preview", async () => {
    await click(`.clip[data-i="${await clipOf("choice")}"]`);
    assert.strictEqual(await text("#m-op"), "choice");
    assert.ok(!(await js("document.querySelector('#choices').hidden")), "choices visible");
    assert.ok((await text("#choices .tag")).includes("preview"), "preview tag");
    const bg = await js("getComputedStyle(document.querySelector('#choices')).backgroundColor");
    assert.ok(!/0\.6\)/.test(bg), "no game scrim while editing: " + bg);
  });

  flow("timeline-reorder", async () => {
    const before = (await model()).model.scenes.intro.map(s => s.op);
    const a = await rect('.clip[data-i="1"]');
    await drag(a.x, a.y, a.x + 3 * 118, a.y);
    const after = (await model()).model.scenes.intro.map(s => s.op);
    assert.notDeepStrictEqual(after, before, "the order changed");
    assert.strictEqual(after[4], before[1] === "show" ? "show" : after[4], "the clip landed where it was dropped");
    await key("z", CTRL);
    assert.deepStrictEqual((await model()).model.scenes.intro.map(s => s.op), before, "undo brings it back");
  });

  flow("delete-step", async () => {
    const n = await count(".clip");
    await click(`.clip[data-i="${n - 2}"]`);
    await key("Delete");
    assert.strictEqual(await count(".clip"), n - 1, "Del deletes the step");
    await key("z", CTRL);
    assert.strictEqual(await count(".clip"), n);
  });

  flow("scenes", async () => {
    await click("#b-scene-add");
    await type("final"); await key("Enter"); await settle();
    assert.ok((await text("#scenes")).includes("final"), "new scene in the list");
    assert.strictEqual(await js("S.scene"), "final", "it becomes selected");
    for (let i = 0; i < 5 && (await count(".clip")); i++) {       // leave it with no exit
      await click(`.clip[data-i="${(await count(".clip")) - 1}"]`); await key("Delete");
    }
    assert.strictEqual(await count(".clip"), 0, "every step can be deleted");
    await click("#b-step-add");
    assert.strictEqual(await count(".clip"), 1, "the first step can be added to an empty scene");
    await key("z", CTRL);
    await click("#b-scene-ren");
    await js("document.querySelector('#dlg input').select()"); await type("final2"); await key("Enter"); await settle();
    assert.strictEqual(await js("S.scene"), "final2", "rename via dialog");
    await clickText("#scenes li", "intro");
    assert.strictEqual(await js("S.scene"), "intro");
  });

  flow("save-and-validate", async () => {
    await click("#b-scene-add"); await type("final2"); await key("Enter"); await settle();   // scene with no exit
    while (await count(".clip")) { await click(`.clip[data-i="${(await count(".clip")) - 1}"]`); await key("Delete"); }
    const before = fs.statSync(VN).mtimeMs;
    await sleep(20);
    await key("s", CTRL);
    assert.ok(fs.statSync(VN).mtimeMs > before, "Ctrl+S wrote the .vn");
    await click("#b-validate");
    await settle();
    const probs = await text("#probs");
    assert.ok(probs.includes("final2") && probs.includes("no exit"), "validate reports the scene with no exit: " + probs);
    await clickText("#scenes li", "final2");
    await selectValue("#newop", "end"); await click("#b-step-add");        // fix it: end
    await click("#b-validate"); await settle();
    assert.strictEqual(await text("#probs"), "", "no problems: the panel is empty");
    assert.ok((await text("#toast")).includes("valid") || (await text("#toast")).includes("no problems"),
              "and it says explicitly that everything is fine (not silence)");
  });

  flow("guides-overlay-help", async () => {
    await key("g");
    assert.ok(await js("document.querySelector('#b-guides').classList.contains('on')"), "G turns guides on");
    assert.ok((await count("#guides .g")) > 0, "lines are drawn");
    await key("g"); await key("g"); await key("g");
    assert.ok(!(await js("document.querySelector('#b-guides').classList.contains('on')")), "the cycle returns to off");
    await click("#b-overlay");
    await click('.clip[data-i="3"]');
    assert.ok(await js("document.querySelector('#dbox').hidden"), "eye off: no dialogue box");
    await click("#b-overlay");
    assert.ok(!(await js("document.querySelector('#dbox').hidden")), "eye on: it comes back");
    await key("?", SHIFT);
    assert.ok(await isOpen("#help"), "? opens the help");
    await key("Escape");
    assert.ok(!(await isOpen("#help")), "Esc closes it");
  });

  flow("try-step", async () => {
    await click(`.clip[data-i="${await clipOf("animate")}"]`);
    await click("#b-probar");
    assert.ok(!(await js("document.querySelector('#animbar').hidden")), "preview bar visible");
    await key("Escape");
    assert.ok(await js("document.querySelector('#anim').hidden"), "Esc closes the preview");
  });

  const reset = async () => {
    await js(`(async () => {
      for (const d of document.querySelectorAll("dialog[open]")) d.close("");
      if (typeof closeAnim === "function") closeAnim();
      if (S.play) await op({op:"play_stop"});
      CPS = 0;                                   // no typing: flows advance in one click
    })()`);
    fs.writeFileSync(VN, VN_TEXT);               // the project goes back to the original: every flow really starts clean
    for (const f of fs.readdirSync(DIR)) if (f.includes("autosave")) fs.unlinkSync(path.join(DIR, f));
    await js(`op({op:"open_project", path:${JSON.stringify(VN)}}).then(() => op({op:"select", scene:"intro", step:1}))`);
    await settle();
  };

  flow("unsaved-changes", async () => {
    await key("s", CTRL);
    assert.ok(!(await js("document.querySelector('#m-path').classList.contains('dirty')")), "saved = clean");
    await click("#b-step-add"); 
    assert.ok(await js("document.querySelector('#m-path').classList.contains('dirty')"), "editing marks ●");
    assert.ok((await js("document.title")).startsWith("●"), "and the tab title too");
    assert.ok(fs.existsSync(VN.replace(/\.vn$/, ".autosave.vn")), "there is an autosave");
    await key("s", CTRL);
    assert.ok(!(await js("document.querySelector('#m-path').classList.contains('dirty')")), "Ctrl+S cleans");
    assert.ok(!fs.existsSync(VN.replace(/\.vn$/, ".autosave.vn")), "and removes the autosave");
    await key("z", CTRL);
  });

  flow("delete-scene", async () => {
    await click("#b-scene-add"); await type("junk"); await key("Enter"); await settle();
    assert.strictEqual(await js("S.scene"), "junk");
    await click("#b-scene-del");
    assert.ok(await isOpen("#dlg"), "asks for confirmation");
    await key("Enter"); await settle();
    assert.ok(!(await text("#scenes")).includes("junk"), "the scene is gone");
    assert.ok(await js("S.model.order.includes(S.scene)"), "another one is selected");
  });

  flow("character-roster", async () => {
    assert.ok((await text("#chars")).includes("Ana"), "the roster lists the characters");
    await click("#b-char"); await type("tmp"); await key("Enter"); await settle();
    assert.ok((await text("#chars")).includes("tmp"), "the new one appears");
    const ok = await js(`(() => { const li = [...document.querySelectorAll("#chars li")].find(l => l.textContent.includes("tmp")); li.querySelector(".x").click(); return !!li; })()`);
    assert.ok(ok); await settle();
    await key("Enter"); await settle();
    assert.ok(!(await text("#chars")).includes("tmp"), "deleted");
    await js(`(() => { const li = [...document.querySelectorAll("#chars li")].find(l => l.textContent.includes("Ana")); li.querySelector(".x").click(); })()`);
    await settle(); await key("Enter"); await settle();
    assert.ok((await text("#chars")).includes("Ana"), "Ana is in use: not deleted");
    assert.ok((await text("#toast")).includes("step"), "and it says why: " + await text("#toast"));
  });

  flow("choice-editor", async () => {
    await click(`.clip[data-i="${await clipOf("choice")}"]`);
    assert.strictEqual(await count("#props .opt"), 2, "one row per option");
    assert.strictEqual(await count("#props .opt select"), 2, "the target is a scene dropdown");
    await selectValue("#props .opt:nth-of-type(2) select", "tower");
    let opts = (await model()).model.scenes.intro.find(s => s.op === "choice").options;
    assert.strictEqual(opts[1].target, "tower", "changing the target applies");
    await fillInput("#props .opt:nth-of-type(1) input", "Climb"); await key("Enter");
    opts = (await model()).model.scenes.intro.find(s => s.op === "choice").options;
    assert.strictEqual(opts[0].label, "Climb", "changing the label applies");
    await clickText("#props button", "+ option");
    assert.strictEqual(await count("#props .opt"), 3, "a row is added");
    await js(`document.querySelector("#props .opt:nth-of-type(3) .x").click()`); await settle();
    assert.strictEqual(await count("#props .opt"), 2, "and removed");
  });

  flow("animate-fields", async () => {
    await click(`.clip[data-i="${await clipOf("animate")}"]`);
    assert.ok(await count('#props input[data-p="vib"]'), "wave: amplitude");
    assert.ok(await count('#props input[data-p="cycle"]'), "wave: cycle");
    assert.strictEqual(await count('#props input[data-p="dist"]'), 0, "wave has no distance");
    await selectValue('#props select[data-k="kind"]', "fall");
    assert.ok(await count('#props input[data-p="dist"]'), "fall: distance");
    assert.ok(await count('#props input[data-p="falltime"]'), "fall: time");
    await fillInput('#props input[data-p="dist"]', "200"); await key("Enter");
    const st = (await model()).model.scenes.intro.find(s => s.op === "animate");
    assert.strictEqual(st.kind, "fall"); assert.strictEqual(st.params.dist, 200, "a number, not text");
    await selectValue('#props select[data-k="kind"]', "move");
    assert.ok(await count('#props select[data-p="curve"]'), "move: curve as a dropdown");
  });

  flow("quick-dialogue", async () => {
    await click('.clip[data-i="1"]');
    const n = await count(".clip");
    await click("#quick"); await type("Hello QA"); await key("Enter");
    assert.strictEqual(await count(".clip"), n + 1, "Enter adds a say");
    let sc = (await model()).model.scenes.intro;
    assert.strictEqual(sc[2].op, "say"); assert.strictEqual(sc[2].text, "Hello QA", "after the selected step");
    assert.strictEqual(await js("document.activeElement.id"), "quick", "focus stays to keep typing");
    assert.strictEqual(await js("document.querySelector('#quick').value"), "", "and the field is cleared");
    await selectValue("#quick-who", "leo");
    await type("And another"); await key("Enter");
    sc = (await model()).model.scenes.intro;
    assert.strictEqual(sc[3].text, "And another", "the next one follows");
    assert.strictEqual(sc[3].who, "leo", "with the chosen speaker");
    await key("z", CTRL); await key("z", CTRL);
  });

  flow("expressions", async () => {
    await click(`.clip[data-i="${await clipOf("show ana")}"]`);
    assert.strictEqual(await count("#props .expr"), 0, "ana starts with no expressions");
    assert.strictEqual(await count('#props select[data-k="expr"]'), 0, "no expressions, no selector in the step");
    await clickText("#props button", "+ expression");
    assert.ok(await isOpen("#dlg"), "asks for the name");
    await type("happy"); await key("Enter"); await settle();
    assert.ok(await isOpen("#brw"), "and then the image");
    await clickText("#brw-list li", "ana.png");
    await clickText("#brw menu button", "Choose");
    assert.strictEqual(await count("#props .expr"), 1, "the expression row appears");
    let c = (await model()).model.characters.ana;
    assert.strictEqual(c.expr.happy, "ana.png", "it is defined");
    assert.strictEqual(await count('#props select[data-k="expr"]'), 1, "now the step can pick an expression");
    await selectValue('#props select[data-k="expr"]', "happy");
    let st = (await model()).model.scenes.intro.find(s => s.op === "show" && s.id === "ana");
    assert.strictEqual(st.expr, "happy", "the show uses the expression");
    assert.ok((await text("#layers")).includes("happy"), "the outliner shows the expression");
    await selectValue('#props select[data-k="expr"]', "");
    st = (await model()).model.scenes.intro.find(s => s.op === "show" && s.id === "ana");
    assert.ok(!("expr" in st), "(base) removes the expression from the step");
    await js(`document.querySelector("#props .expr .x").click()`); await settle();
    c = (await model()).model.characters.ana;
    assert.ok(!c.expr, "✕ removes the expression from the character");
  });

  flow("typing", async () => {
    await js(`localStorage.setItem("vnscps", "3"); CPS = 3;`);   // slow, to see it
    await click('.clip[data-i="3"]');                            // a line
    await click("#b-play");
    const full = await js("S.play.say.text");
    const shown = await text("#text");
    assert.ok(shown.length < full.length, `while typing it shows partially: "${shown}"`);
    const r = await rect("#stage"); await clickAt(r.x, r.y - 80);
    assert.strictEqual(await text("#text"), full, "the first click completes the text");
    const step = await js("S.play.step");
    assert.strictEqual(await js("S.play.step"), step, "and does not advance");
    await clickAt(r.x, r.y - 80);
    assert.ok((await js("S.play.step")) > step, "the next click advances");
    await js(`localStorage.removeItem("vnscps"); CPS = 0;`);
  });

  flow("bg-fade", async () => {
    await click('.clip[data-i="0"]');                 // bg
    assert.ok(await count('#props input[data-p="fade"]'), "the background has a fade field");
    await fillInput('#props input[data-p="fade"]', "300"); await key("Enter");
    const st = (await model()).model.scenes.intro[0];
    assert.strictEqual(st.fade, 300, "it is stored in the step");
    await key("z", CTRL);
  });

  flow("audio", async () => {
    await clickText("#scenes li", "tower");
    await click('.clip[data-i="1"]');                                  // the bgm
    await click("#b-play");
    assert.ok((await js("document.querySelector('#bgm').getAttribute('src') || ''")).includes("theme.wav"),
              "in Play the scene's bgm plays");
    assert.ok(await js("!document.querySelector('#bgm').paused || document.querySelector('#bgm').error !== null"),
              "it is playing (or the test file is not valid audio)");
    const r = await rect("#stage");
    for (let i = 0; i < 6 && !(await js("document.querySelector('#sfx').getAttribute('src') || ''")).includes("hit"); i++)
      await clickAt(r.x, r.y - 80);                                    // step by step up to the se
    assert.ok((await js("document.querySelector('#sfx').getAttribute('src') || ''")).includes("hit.wav"),
              "the se fired");
    await key("Escape");
    assert.ok(await js("document.querySelector('#bgm').paused"), "leaving Play silences it");
    /* while editing: ▶ button to listen to the chosen file */
    await click('.clip[data-i="1"]');                            // bgm
    await clickText("#props button", "▶");
    assert.ok((await js("document.querySelector('#sfx').getAttribute('src') || ''")).includes("theme.wav"),
              "▶ plays the step's file");
    await clickText("#scenes li", "intro");
  });

  flow("multi-select-copy-paste", async () => {
    const n = await count(".clip");
    await click('.clip[data-i="1"]');
    const r3 = await rect('.clip[data-i="3"]');
    await mouse("mouseMoved", r3.x, r3.y);
    await mouse("mousePressed", r3.x, r3.y, { modifiers: SHIFT }); await mouse("mouseReleased", r3.x, r3.y, { modifiers: SHIFT });
    await settle();
    assert.strictEqual(await count(".clip.sel"), 3, "Shift+click selects the range 1..3");
    assert.strictEqual(await js("S.step"), 3, "the cursor lands on the last one");
    await key("c", CTRL);
    await click(`.clip[data-i="${n - 1}"]`);                    // at the end
    await key("v", CTRL);
    assert.strictEqual(await count(".clip"), n + 3, "Ctrl+V pastes the 3 after the cursor");
    const sc = (await model()).model.scenes.intro;
    assert.strictEqual(sc[n].op, sc[1].op, "in the same order");
    await click(`.clip[data-i="${n}"]`);
    const rl = await rect(`.clip[data-i="${n + 2}"]`);
    await mouse("mouseMoved", rl.x, rl.y);
    await mouse("mousePressed", rl.x, rl.y, { modifiers: SHIFT }); await mouse("mouseReleased", rl.x, rl.y, { modifiers: SHIFT });
    await settle();
    await key("Delete");
    assert.strictEqual(await count(".clip"), n, "Del deletes the multi-selection");
    await clickText("#scenes li", "tower");                     // clipboard across scenes
    const m = await count(".clip");
    await click('.clip[data-i="0"]'); await key("v", CTRL);
    assert.strictEqual(await count(".clip"), m + 3, "pastes into another scene");
    await key("z", CTRL); await clickText("#scenes li", "intro");
  });

  flow("find", async () => {
    await key("f", CTRL);
    assert.ok(await isOpen("#find"), "Ctrl+F opens find");
    await type("We made it"); await settle();
    assert.ok((await count("#find-list li")) >= 1, "lists results as you type");
    await click("#find-list li");
    assert.ok(!(await isOpen("#find")), "choosing closes");
    assert.strictEqual(await js("S.scene"), "tower", "and goes to the scene");
    assert.ok((await text("#text")).includes("We made it"), "to the step");
    await clickText("#scenes li", "intro");
  });

  flow("scene-graph", async () => {
    await click("#b-graph");
    assert.ok(await isOpen("#graph"), "the flow view opens");
    assert.ok((await count("#graph svg .node")) >= 2, "one node per scene");
    assert.ok((await count("#graph svg .edge")) >= 1, "the choice/goto edges");
    const ok = await js(`(() => { const n = [...document.querySelectorAll("#graph svg .node")].find(n => n.textContent.includes("tower")); n.dispatchEvent(new MouseEvent("click", {bubbles:true})); return !!n; })()`);
    assert.ok(ok); await settle();
    assert.ok(!(await isOpen("#graph")), "clicking a node closes");
    assert.strictEqual(await js("S.scene"), "tower", "and goes to that scene");
    await clickText("#scenes li", "intro");
  });

  flow("export-ps2", async () => {
    await click("#b-export");
    assert.ok(await isOpen("#dlg"), "Export asks for the format");
    await selectValue("#dlg select", "vnp");
    await key("Enter"); await settle();
    assert.ok(await isOpen("#brw"), "and then where");
    await js(`document.querySelector("#brw-path").value = ${JSON.stringify(path.join(DIR, "out.vnp"))}`);
    await clickText("#brw menu button", "Choose");
    assert.ok(fs.existsSync(path.join(DIR, "out.vnp")), "wrote the PS2 blob");
    assert.ok((await text("#toast")).includes("out.vnp"), "and says so");
  });

  flow("play-mode", async () => {
    assert.strictEqual(await text("#b-playmode"), "step by step", "starts in the editor's mode");
    await click('.clip[data-i="0"]'); await click("#b-play");
    assert.strictEqual(await js("S.play.stepwise"), true);
    assert.strictEqual(await js("S.play.say"), null, "step by step: step 0 is the background, no line");
    await key("Escape");
    await click("#b-playmode");
    assert.strictEqual(await text("#b-playmode"), "as the player", "the button names the mode");
    await click('.clip[data-i="0"]'); await click("#b-play");
    assert.strictEqual(await js("S.play.stepwise"), false);
    assert.ok(await js("!!S.play.say"), "as the player: runs up to the first line");
    await key("Escape"); await click("#b-playmode");        // leave it as it was
  });

  flow("groups", async () => {
    await click('.clip[data-i="0"]');
    const r2 = await rect('.clip[data-i="2"]');
    await mouse("mouseMoved", r2.x, r2.y);
    await mouse("mousePressed", r2.x, r2.y, { modifiers: SHIFT }); await mouse("mouseReleased", r2.x, r2.y, { modifiers: SHIFT });
    await settle();
    await key("g", CTRL);
    assert.ok(await isOpen("#dlg"), "Ctrl+G asks for the name");
    await js(`document.querySelector("#dlg input").select()`); await type("opening"); await key("Enter"); await settle();
    assert.strictEqual(await count(".gband"), 1, "group band in the timeline");
    assert.ok((await text("#groups")).includes("opening"), "and in the outliner");
    let sc = (await model()).model.scenes.intro;
    assert.deepStrictEqual(sc.slice(0, 3).map(s => s.group), ["opening", "opening", "opening"]);
    await click('.clip[data-i="0"]'); await click("#b-play");
    assert.strictEqual(await js("S.play.step"), 2, "Play: the whole group is one click");
    assert.strictEqual(await count("#stage .layer"), 2, "both characters are already there");
    await key("Escape");
    await click('.clip[data-i="1"]'); await key("g", CTRL);          // inside a group = ungroup
    assert.ok(await isOpen("#dlg")); await key("Enter"); await settle();
    sc = (await model()).model.scenes.intro;
    assert.ok(!sc[1].group && sc[0].group === "opening", "removed only that step");
    await key("z", CTRL); await key("z", CTRL);
  });

  /* ---------- run ---------- */
  const names = Object.keys(flows).filter(n => !ONLY.length || ONLY.includes(n));
  let fails = 0;
  for (const n of names) {
    const errBefore = jserr.length;
    try { await reset(); await flows[n](); process.stdout.write(`  ✓ ${n}\n`); }
    catch (e) { fails++; process.stdout.write(`  ✗ ${n}: ${e.message.split("\n")[0]}\n`);
      if (process.env.QA_DEBUG) process.stdout.write(`    state: ${await dump().catch(() => "?")}\n`); }
    if (jserr.length > errBefore) { fails++; process.stdout.write(`    ⚠ JS: ${jserr.slice(errBefore).join(" | ").slice(0, 300)}\n`); }
  }
  ws.close(); kill(chrome); kill(srv);
  console.log(fails ? `QA: ${fails} problem(s)` : "QA GREEN");
  process.exit(fails ? 1 : 0);
}
main().catch(e => { console.error("harness:", e.message); process.exit(2); });
