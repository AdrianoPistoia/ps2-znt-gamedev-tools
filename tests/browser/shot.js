#!/usr/bin/env node
/* Captura de VN Studio por CDP, sin tocar el código de la app.
 *   node tests/browser/shot.js proyecto.vn salida.png ["js a correr antes"] */
"use strict";
const { spawn } = require("child_process");
const fs = require("fs"), os = require("os"), path = require("path");
const REPO = path.join(__dirname, "..", "..");
const [vnPath, out, pre] = process.argv.slice(2);
const waitLine = (p, st, re) => new Promise((res, rej) => { let b = "";
  p[st].on("data", d => { b += d; const m = b.match(re); if (m) res(m); });
  setTimeout(() => rej(new Error("timeout: " + b)), 15000); });
(async () => {
  const srv = spawn("python3", ["-m", "znt", "web", vnPath, "--port", "0", "--no-browser"],
                    { cwd: REPO, env: { ...process.env, PYTHONPATH: REPO, PYTHONUNBUFFERED: "1" } });
  const [, url] = await waitLine(srv, "stdout", /en (http:\/\/127\.0\.0\.1:\d+\/)/);
  const prof = fs.mkdtempSync(path.join(os.tmpdir(), "vnshot-"));
  const chrome = spawn("chromium", ["--headless=new", "--disable-gpu", "--no-first-run", "--hide-scrollbars",
    "--remote-debugging-port=0", "--remote-allow-origins=*", "--window-size=1400,860", "--user-data-dir=" + prof, "about:blank"]);
  const [, dbg] = await waitLine(chrome, "stderr", /DevTools listening on ws:\/\/127\.0\.0\.1:(\d+)\//);
  const tgt = await (await fetch(`http://127.0.0.1:${dbg}/json/new?${url}`, { method: "PUT" })).json();
  const ws = new WebSocket(tgt.webSocketDebuggerUrl);
  await new Promise(r => ws.onopen = r);
  let id = 0; const pend = {};
  ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pend[m.id]) { pend[m.id](m); delete pend[m.id]; } };
  const send = (method, params = {}) => new Promise(res => { pend[++id] = res; ws.send(JSON.stringify({ id, method, params })); });
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  await sleep(1500);
  if (pre) await send("Runtime.evaluate", { expression: pre, awaitPromise: true });
  await sleep(700);
  const r = await send("Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(out, Buffer.from(r.result.data, "base64"));
  ws.close(); chrome.kill("SIGKILL"); srv.kill("SIGKILL");
  console.log("escrito", out);
})().catch(e => { console.error(e.message); process.exit(1); });
