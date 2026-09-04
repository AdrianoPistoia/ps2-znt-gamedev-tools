#!/usr/bin/env node
/* QA de verdad: maneja chromium por CDP (clicks, teclado, arrastre) contra el
 * server real, y junta las excepciones JS de la página.
 *   node tests/browser/qa.js            -> corre todos los flujos
 *   node tests/browser/qa.js play drag  -> sólo esos
 * Sin deps: WebSocket y fetch nativos de Node ≥ 22. */
"use strict";
const { spawn } = require("child_process");
const fs = require("fs"), os = require("os"), path = require("path"), assert = require("assert");
const REPO = path.join(__dirname, "..", "..");
const ONLY = process.argv.slice(2);

/* ---------- proyecto de prueba ---------- */
const DIR = fs.mkdtempSync(path.join(os.tmpdir(), "vnqa-"));
const VN = path.join(DIR, "demo.vn");
fs.writeFileSync(VN, `title: QA
character ana "Ana" #7cc4ff
character leo "Leo" #f0a92e
sprite ana ana.png
scene inicio
  bg grad:#101828,#2a3a5f
  show ana left
  show leo right zoom=120
  ana: ¿Trajiste el mapa?
  leo: Está en la torre.
  animate ana wave amp=8 speed=2
  choice
  - Ir a la torre -> torre
  - Quedarse -> inicio
scene torre
  bg #1a1020
  show leo center
  leo: Llegamos.
  end
`);
{ // PNG 40x60 opaco, sin deps
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

/* ---------- procesos ---------- */
const waitLine = (proc, stream, re, what) => new Promise((res, rej) => {
  let buf = ""; const t = setTimeout(() => rej(new Error("timeout esperando " + what + "\n" + buf)), 15000);
  proc[stream].on("data", d => { buf += d; const m = buf.match(re); if (m) { clearTimeout(t); res(m); } });
  proc.on("exit", c => rej(new Error(what + " terminó (" + c + ")\n" + buf)));
});
const kill = p => { try { p.kill("SIGKILL"); } catch (e) {} };

async function main() {
  const srv = spawn("python3", ["-m", "znt", "web", VN, "--port", "0", "--no-browser"],
                    { cwd: REPO, env: { ...process.env, PYTHONPATH: REPO, PYTHONUNBUFFERED: "1" } });
  const [, url] = await waitLine(srv, "stdout", /en (http:\/\/127\.0\.0\.1:\d+\/)/, "el server");
  const chrome = spawn("chromium", ["--headless=new", "--disable-gpu", "--no-first-run",
    "--remote-debugging-port=0", "--remote-allow-origins=*", "--window-size=1400,900",
    "--user-data-dir=" + path.join(DIR, "profile"), "about:blank"]);
  const [, dbg] = await waitLine(chrome, "stderr", /DevTools listening on ws:\/\/127\.0\.0\.1:(\d+)\//, "chromium");
  const tgt = await (await fetch(`http://127.0.0.1:${dbg}/json/new?${url}`, { method: "PUT" })).json();

  /* ---------- cliente CDP ---------- */
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
    if (r.exceptionDetails) throw new Error("js falló: " + ((r.exceptionDetails.exception || {}).description || r.exceptionDetails.text) + "\n  en: " + expr.slice(0, 120));
    return r.result.value;
  };
  /* esperar a que la app termine lo que estaba haciendo */
  const settle = async () => {
    for (let i = 0; i < 100; i++) { await sleep(40); if (!(await js("window.__vns && window.__vns.busy"))) break; }
    await js("new Promise(r => requestAnimationFrame(() => setTimeout(r, 30)))");
  };
  const rect = async sel => js(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e) return null;
    const r = e.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height }; })()`);
  const mouse = (type, x, y, extra = {}) => send("Input.dispatchMouseEvent", { type, x, y, button: "left", clickCount: 1, ...extra });
  const clickAt = async (x, y) => { await mouse("mouseMoved", x, y); await mouse("mousePressed", x, y); await mouse("mouseReleased", x, y); await settle(); };
  const click = async sel => { const r = await rect(sel); assert(r, "no existe " + sel); await clickAt(r.x, r.y); };
  const clickText = async (sel, text) => {          // botón por su texto
    const ok = await js(`(() => { const b = [...document.querySelectorAll(${JSON.stringify(sel)})].find(x => x.textContent.trim().startsWith(${JSON.stringify(text)})); if (!b) return false; b.scrollIntoView(); b.click(); return true; })()`);
    assert(ok, `no hay ${sel} con texto "${text}"`); await settle();
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
    const txt = k === "Enter" ? "\r" : printable ? k : undefined;   // Enter lleva texto: así dispara el submit
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
  const clipOf = async op => {                       // índice del primer clip de ese tipo
    const i = await js(`(() => { const c = [...document.querySelectorAll(".clip")].find(c => c.textContent.startsWith(${JSON.stringify(op)})); return c ? +c.dataset.i : -1; })()`);
    assert(i >= 0, "no hay clip " + op); return i;
  };
  const dump = () => js(`JSON.stringify({step: S.step, scene: S.scene, play: !!S.play, sel: typeof SEL !== "undefined" ? SEL : null,
    dlg: document.querySelector("#dlg").open, brw: document.querySelector("#brw").open, help: document.querySelector("#help").open,
    toast: document.querySelector("#toast").hidden ? "" : document.querySelector("#toast").textContent,
    active: document.activeElement && (document.activeElement.id || document.activeElement.tagName),
    probs: document.querySelector("#probs").textContent.slice(0, 120)})`);
  const selectValue = async (sel, v) => { await js(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); e.value = ${JSON.stringify(v)}; e.dispatchEvent(new Event("change", {bubbles:true})); })()`); await settle(); };
  const fillInput = async (sel, v) => { await click(sel); await js(`document.querySelector(${JSON.stringify(sel)}).select()`); await type(v); };

  await new Promise(r => setTimeout(r, 800)); await settle();

  /* ---------- flujos ---------- */
  const flows = {};
  const flow = (name, fn) => { flows[name] = fn; };

  flow("carga", async () => {
    assert.strictEqual(await count(".clip"), 7, "7 pasos como clips");
    assert.ok((await js("S.step")) >= 0, "arranca con un paso elegido");
    assert.ok((await text("#props")).length > 20, "el inspector muestra algo");
    await click('.clip[data-i="0"]');
    assert.strictEqual(await count("#layers li"), 0, "en el paso bg no hay capas");
    assert.ok((await text("#m-zoom")).endsWith("%"), "muestra la escala del viewport");
  });

  flow("seleccionar", async () => {
    await click('.clip[data-i="3"]');
    assert.strictEqual(await js("S.step"), 3);
    assert.strictEqual(await text("#m-op"), "say");
    assert.ok((await text("#text")).includes("mapa"), "el diálogo del paso está en el escenario");
    assert.strictEqual(await count("#layers li"), 2, "dos capas en escena");
    await key("ArrowRight"); assert.strictEqual(await js("S.step"), 4, "→ avanza un paso");
    await key("ArrowLeft");  assert.strictEqual(await js("S.step"), 3, "← retrocede");
  });

  flow("agregar-say-y-editar", async () => {
    await click('.clip[data-i="3"]');
    await selectValue("#newop", "say");
    await click("#b-step-add");
    assert.strictEqual(await count(".clip"), 8, "se agregó un clip");
    assert.strictEqual(await js("S.step"), 4, "queda seleccionado el nuevo, después del anterior");
    assert.strictEqual(await count("#props textarea"), 1, "el texto se edita en un textarea");
    await fillInput("#props textarea", "Línea nueva de QA");
    await key("Tab");                                  // blur -> change
    await sleep(200); await settle();
    const m = await model();
    const st = m.model.scenes.inicio[4];
    assert.strictEqual(st.op, "say");
    assert.strictEqual(st.text, "Línea nueva de QA", `el texto se aplicó al salir del campo (quedó: ${JSON.stringify(st.text)})`);
    assert.ok((await text("#text")).includes("Línea nueva"), "y se ve en el escenario");
  });

  flow("undo-redo", async () => {
    const n = await count(".clip");
    await click("#b-step-add");
    assert.strictEqual(await count(".clip"), n + 1);
    await key("z", CTRL);
    assert.strictEqual(await count(".clip"), n, "Ctrl+Z deshace el paso agregado");
    await key("y", CTRL);
    assert.strictEqual(await count(".clip"), n + 1, "Ctrl+Y lo rehace");
    await key("z", CTRL);
  });

  flow("play", async () => {
    await click('.clip[data-i="1"]');                  // show ana
    await click("#b-play");
    assert.ok(await js("document.body.classList.contains('playing')"), "modo Play");
    assert.strictEqual(await count(".clip.playing"), 1, "un clip marcado");
    assert.strictEqual(await js("S.play.step"), 3, "arrancó en el 1 y se frenó en el primer diálogo (3)");
    const r = await rect("#stage"); await clickAt(r.x, r.y - 80);
    assert.strictEqual(await js("S.play.step"), 4, "click en pantalla avanza un diálogo");
    await key(" ");
    assert.ok(await js("S.play.step >= 5"), "Espacio también avanza");
    for (let i = 0; i < 6 && !(await js("S.play.choices.length")); i++) await key(" ");
    assert.strictEqual(await js("S.play.choices.length"), 2, "llega al choice");
    await clickText("#choices button", "Ir a la torre");
    assert.strictEqual(await js("S.play.scene"), "torre", "elegir salta de escena");
    assert.strictEqual(await text("#scenes li.sel span"), "torre", "la lista de escenas sigue al Play");
    await key("Escape");
    assert.ok(!(await js("document.body.classList.contains('playing')")), "Esc sale");
    assert.strictEqual(await js("S.step"), 1, "vuelve a la selección de edición");
  });

  flow("drag-sprite", async () => {
    await click('.clip[data-i="1"]');
    const before = (await model()).model.scenes.inicio[1];
    const r = await rect('.layer[data-id="ana"]'); assert(r, "sprite de ana en el escenario");
    await drag(r.x, r.y, r.x + 90, r.y);
    const after = (await model()).model.scenes.inicio[1];
    assert.ok((after.x || 0) > (before.x || -180) + 30, `x tendría que crecer: ${before.x} -> ${after.x}`);
    assert.strictEqual(await js("SEL"), "ana", "quedó seleccionada");
    assert.ok(!(await js("document.querySelector('#frame').hidden")), "marco de selección visible");
  });

  flow("handles-zoom", async () => {
    await click('.clip[data-i="1"]');
    await click('.layer[data-id="ana"]');
    const h = await rect('#frame .hnd[data-h="1"]'); assert(h, "handle derecho");
    await drag(h.x, h.y, h.x + 40, h.y);
    const z = (await model()).model.scenes.inicio[1].zoom;
    assert.ok(z > 100, `el zoom tendría que subir: ${z}`);
  });

  flow("explorador", async () => {
    await click('.clip[data-i="1"]');
    await clickText("#props button", "📁");
    assert.ok(await isOpen("#brw"), "se abre el explorador");
    assert.ok((await count("#brw-list li")) > 0, "lista algo");
    assert.ok((await text("#brw-crumbs")).includes("/"), "migas");
    await clickText("#brw menu button", "Cancelar");
    assert.ok(!(await isOpen("#brw")), "se cierra");
  });

  flow("nuevo-personaje-dialogo", async () => {
    await click("#b-char");
    assert.ok(await isOpen("#dlg"));
    await type("cy");
    await key("Tab"); await type("Cy");
    await key("Enter");                               // Enter tiene que ACEPTAR
    await settle();
    assert.ok(!(await isOpen("#dlg")), "Enter cierra el diálogo");
    const m = await model();
    assert.ok(m.model.characters.cy, "Enter acepta y crea el personaje (no cancela)");
    assert.strictEqual(m.model.characters.cy.name, "Cy");
  });

  flow("choice-preview", async () => {
    await click(`.clip[data-i="${await clipOf("choice")}"]`);
    assert.strictEqual(await text("#m-op"), "choice");
    assert.ok(!(await js("document.querySelector('#choices').hidden")), "opciones visibles");
    assert.ok((await text("#choices .tag")).includes("previsualizaci"), "cartel de previsualización");
    const bg = await js("getComputedStyle(document.querySelector('#choices')).backgroundColor");
    assert.ok(!/0\.6\)/.test(bg), "sin el velo del juego en edición: " + bg);
  });

  flow("timeline-reordenar", async () => {
    const before = (await model()).model.scenes.inicio.map(s => s.op);
    const a = await rect('.clip[data-i="1"]');
    await drag(a.x, a.y, a.x + 3 * 118, a.y);
    const after = (await model()).model.scenes.inicio.map(s => s.op);
    assert.notDeepStrictEqual(after, before, "el orden cambió");
    assert.strictEqual(after[4], before[1] === "show" ? "show" : after[4], "el clip cayó donde se soltó");
    await key("z", CTRL);
    assert.deepStrictEqual((await model()).model.scenes.inicio.map(s => s.op), before, "undo lo devuelve");
  });

  flow("borrar-paso", async () => {
    const n = await count(".clip");
    await click(`.clip[data-i="${n - 2}"]`);
    await key("Delete");
    assert.strictEqual(await count(".clip"), n - 1, "Supr borra el paso");
    await key("z", CTRL);
    assert.strictEqual(await count(".clip"), n);
  });

  flow("escenas", async () => {
    await click("#b-scene-add");
    await type("final"); await key("Enter"); await settle();
    assert.ok((await text("#scenes")).includes("final"), "escena nueva en la lista");
    assert.strictEqual(await js("S.scene"), "final", "queda seleccionada");
    for (let i = 0; i < 5 && (await count(".clip")); i++) {       // la dejo sin salida
      await click(`.clip[data-i="${(await count(".clip")) - 1}"]`); await key("Delete");
    }
    assert.strictEqual(await count(".clip"), 0, "se pueden borrar todos los pasos");
    await click("#b-step-add");
    assert.strictEqual(await count(".clip"), 1, "se puede agregar el primer paso a una escena vacía");
    await key("z", CTRL);
    await click("#b-scene-ren");
    await js("document.querySelector('#dlg input').select()"); await type("final2"); await key("Enter"); await settle();
    assert.strictEqual(await js("S.scene"), "final2", "renombrar por diálogo");
    await clickText("#scenes li", "inicio");
    assert.strictEqual(await js("S.scene"), "inicio");
  });

  flow("guardar-y-validar", async () => {
    const before = fs.statSync(VN).mtimeMs;
    await sleep(20);
    await key("s", CTRL);
    assert.ok(fs.statSync(VN).mtimeMs > before, "Ctrl+S escribió el .vn");
    await click("#b-validate");
    await settle();
    const probs = await text("#probs");
    assert.ok(probs.includes("final2") && probs.includes("sin salida"), "validar reporta la escena sin salida: " + probs);
    await clickText("#scenes li", "final2");
    await selectValue("#newop", "end"); await click("#b-step-add");        // la arreglo: end
    await click("#b-validate"); await settle();
    assert.strictEqual(await text("#probs"), "", "sin problemas: el panel queda vacío");
    assert.ok((await text("#toast")).includes("válido") || (await text("#toast")).includes("sin problemas"),
              "y se dice explícitamente que está todo bien (no silencio)");
  });

  flow("guias-overlay-ayuda", async () => {
    await key("g");
    assert.ok(await js("document.querySelector('#b-guides').classList.contains('on')"), "G prende guías");
    assert.ok((await count("#guides .g")) > 0, "se dibujan líneas");
    await key("g"); await key("g"); await key("g");
    assert.ok(!(await js("document.querySelector('#b-guides').classList.contains('on')")), "el ciclo vuelve a off");
    await click("#b-overlay");
    await click('.clip[data-i="3"]');
    assert.ok(await js("document.querySelector('#dbox').hidden"), "ojo apagado: sin cuadro de diálogo");
    await click("#b-overlay");
    assert.ok(!(await js("document.querySelector('#dbox').hidden")), "ojo prendido: vuelve");
    await key("?", SHIFT);
    assert.ok(await isOpen("#help"), "? abre la ayuda");
    await key("Escape");
    assert.ok(!(await isOpen("#help")), "Esc la cierra");
  });

  flow("probar-paso", async () => {
    await click(`.clip[data-i="${await clipOf("animate")}"]`);
    await click("#b-probar");
    assert.ok(!(await js("document.querySelector('#animbar').hidden")), "barra de preview visible");
    await key("Escape");
    assert.ok(await js("document.querySelector('#anim').hidden"), "Esc cierra el preview");
  });

  const reset = async () => {
    await js(`(async () => {
      for (const d of document.querySelectorAll("dialog[open]")) d.close("");
      if (typeof closeAnim === "function") closeAnim();
      if (S.play) await op({op:"play_stop"});
      if (S.scene !== "inicio" || S.step !== 1) await op({op:"select", scene:"inicio", step:1});
    })()`);
    await settle();
  };

  flow("cambios-sin-guardar", async () => {
    await key("s", CTRL);
    assert.ok(!(await js("document.querySelector('#m-path').classList.contains('dirty')")), "guardado = limpio");
    await click("#b-step-add"); 
    assert.ok(await js("document.querySelector('#m-path').classList.contains('dirty')"), "editar marca ●");
    assert.ok((await js("document.title")).startsWith("●"), "y el título de la pestaña también");
    assert.ok(fs.existsSync(VN.replace(/\.vn$/, ".autosave.vn")), "hay autosave");
    await key("s", CTRL);
    assert.ok(!(await js("document.querySelector('#m-path').classList.contains('dirty')")), "Ctrl+S limpia");
    assert.ok(!fs.existsSync(VN.replace(/\.vn$/, ".autosave.vn")), "y borra el autosave");
    await key("z", CTRL);
  });

  flow("borrar-escena", async () => {
    await click("#b-scene-add"); await type("basura"); await key("Enter"); await settle();
    assert.strictEqual(await js("S.scene"), "basura");
    await click("#b-scene-del");
    assert.ok(await isOpen("#dlg"), "pide confirmación");
    await key("Enter"); await settle();
    assert.ok(!(await text("#scenes")).includes("basura"), "la escena se fue");
    assert.ok(await js("S.model.order.includes(S.scene)"), "quedó otra seleccionada");
  });

  flow("roster-personajes", async () => {
    assert.ok((await text("#chars")).includes("Ana"), "el roster lista a los personajes");
    await click("#b-char"); await type("tmp"); await key("Enter"); await settle();
    assert.ok((await text("#chars")).includes("tmp"), "el nuevo aparece");
    const ok = await js(`(() => { const li = [...document.querySelectorAll("#chars li")].find(l => l.textContent.includes("tmp")); li.querySelector(".x").click(); return !!li; })()`);
    assert.ok(ok); await settle();
    await key("Enter"); await settle();
    assert.ok(!(await text("#chars")).includes("tmp"), "borrado");
    await js(`(() => { const li = [...document.querySelectorAll("#chars li")].find(l => l.textContent.includes("Ana")); li.querySelector(".x").click(); })()`);
    await settle(); await key("Enter"); await settle();
    assert.ok((await text("#chars")).includes("Ana"), "Ana está en uso: no se borra");
    assert.ok((await text("#toast")).includes("paso"), "y se dice por qué: " + await text("#toast"));
  });

  flow("choice-editor", async () => {
    await click(`.clip[data-i="${await clipOf("choice")}"]`);
    assert.strictEqual(await count("#props .opt"), 2, "una fila por opción");
    assert.strictEqual(await count("#props .opt select"), 2, "el destino es un desplegable de escenas");
    await selectValue("#props .opt:nth-of-type(2) select", "torre");
    let opts = (await model()).model.scenes.inicio.find(s => s.op === "choice").options;
    assert.strictEqual(opts[1].target, "torre", "cambiar el destino aplica");
    await fillInput("#props .opt:nth-of-type(1) input", "Subir"); await key("Enter");
    opts = (await model()).model.scenes.inicio.find(s => s.op === "choice").options;
    assert.strictEqual(opts[0].label, "Subir", "cambiar la etiqueta aplica");
    await clickText("#props button", "+ opción");
    assert.strictEqual(await count("#props .opt"), 3, "se agrega una fila");
    await js(`document.querySelector("#props .opt:nth-of-type(3) .x").click()`); await settle();
    assert.strictEqual(await count("#props .opt"), 2, "y se saca");
  });

  flow("animate-campos", async () => {
    await click(`.clip[data-i="${await clipOf("animate")}"]`);
    assert.ok(await count('#props input[data-p="vib"]'), "wave: amplitud");
    assert.ok(await count('#props input[data-p="cycle"]'), "wave: ciclo");
    assert.strictEqual(await count('#props input[data-p="dist"]'), 0, "wave no tiene distancia");
    await selectValue('#props select[data-k="kind"]', "fall");
    assert.ok(await count('#props input[data-p="dist"]'), "fall: distancia");
    assert.ok(await count('#props input[data-p="falltime"]'), "fall: tiempo");
    await fillInput('#props input[data-p="dist"]', "200"); await key("Enter");
    const st = (await model()).model.scenes.inicio.find(s => s.op === "animate");
    assert.strictEqual(st.kind, "fall"); assert.strictEqual(st.params.dist, 200, "número, no texto");
    await selectValue('#props select[data-k="kind"]', "move");
    assert.ok(await count('#props select[data-p="curve"]'), "move: curva como desplegable");
  });

  flow("dialogo-rapido", async () => {
    await click('.clip[data-i="1"]');
    const n = await count(".clip");
    await click("#quick"); await type("Hola QA"); await key("Enter");
    assert.strictEqual(await count(".clip"), n + 1, "Enter agrega un say");
    let sc = (await model()).model.scenes.inicio;
    assert.strictEqual(sc[2].op, "say"); assert.strictEqual(sc[2].text, "Hola QA", "después del paso elegido");
    assert.strictEqual(await js("document.activeElement.id"), "quick", "el foco se queda para seguir escribiendo");
    assert.strictEqual(await js("document.querySelector('#quick').value"), "", "y el campo se vacía");
    await selectValue("#quick-who", "leo");
    await type("Y otra"); await key("Enter");
    sc = (await model()).model.scenes.inicio;
    assert.strictEqual(sc[3].text, "Y otra", "la siguiente va a continuación");
    assert.strictEqual(sc[3].who, "leo", "con el hablante elegido");
    await key("z", CTRL); await key("z", CTRL);
  });

  /* ---------- correr ---------- */
  const names = Object.keys(flows).filter(n => !ONLY.length || ONLY.includes(n));
  let fails = 0;
  for (const n of names) {
    const errBefore = jserr.length;
    try { await reset(); await flows[n](); process.stdout.write(`  ✓ ${n}\n`); }
    catch (e) { fails++; process.stdout.write(`  ✗ ${n}: ${e.message.split("\n")[0]}\n`);
      if (process.env.QA_DEBUG) process.stdout.write(`    estado: ${await dump().catch(() => "?")}\n`); }
    if (jserr.length > errBefore) { fails++; process.stdout.write(`    ⚠ JS: ${jserr.slice(errBefore).join(" | ").slice(0, 300)}\n`); }
  }
  ws.close(); kill(chrome); kill(srv);
  console.log(fails ? `QA: ${fails} problema(s)` : "QA GREEN");
  process.exit(fails ? 1 : 0);
}
main().catch(e => { console.error("harness:", e.message); process.exit(2); });
