# VN Studio (web) — feature map and QA

Status as of 2026-09-04, branch `web-studio`. The editor runs on the real engine
(`znt.vnstudio.VNRuntime`); the Python server is the source of truth and the
browser composes with CSS. This document is the inventory + what the QA found +
what is missing for the vision.

## 1. Feature map (what exists)

### Project
| Feature | Where | How |
|---|---|---|
| New / Open / Save / Save as / Export HTML | topbar | own dialogs + 📁 file browser |
| Validate (broken gotos, missing characters/expressions, scenes with no exit, assets) | topbar | problems panel in the inspector |
| **⌥ flow**: scene graph | topbar | SVG, click goes to the scene |
| Export **html / vnp / iso** | topbar | format dialog + browser |
| Undo / Redo | topbar, Ctrl+Z / Ctrl+Y | history on the server |
| Server: `--restart`, `--stop`, `--port`, API version warning | CLI | pidfile + /proc sweep |

### Scenes and steps
| Feature | Where |
|---|---|
| Scenes: add, duplicate, rename, move up/down | outliner |
| Steps: add (10 types), duplicate, delete, move, drag to reorder, **multi-selection, Ctrl+C/V, Ctrl+F** | timeline |
| **Groups** (Ctrl+G): several steps = one click in Play; band on the timeline and list in the outliner; `group x … endgroup` in the .vn | timeline / outliner |
| Timeline with tracks per type, ruler, playhead, scrub, Ctrl+wheel zoom | timeline |
| Inspector per step type with collapsible sections | inspector |
| Numeric fields with scrub (drag the label, Shift fine) | inspector |

### Characters and layers
| Feature | Where |
|---|---|
| Create character (id, name, colour) | topbar ＋ Character |
| Single Character section: choose, name, colour, sprite (📁/⇧ upload), **expressions**, rename id | inspector |
| The step's layers (front first), synced selection, double click → its `show` | outliner |
| Drag sprite with snap and guides (Shift free); corner handles = zoom | viewport |
| Z order ▲/▼, opacity, tint, x/y/z/zoom | inspector |

### Playback
| Feature | Where |
|---|---|
| Play **step by step** from the chosen step (click/Space/⏭ = next step; a group = one click); choices; typing ⌨; bgm/se | viewport |
| The timeline follows the runtime (scene and step), click on a clip = play from there | timeline |
| UI switched off in Play except game + timeline | everywhere |
| ▶ Try step: transition rendered by the engine (APNG), closes on its own | viewport |
| Guides (centre/thirds/safe zone), eye to hide dialogue/options | viewport |

### Robustness
- Server errors, fetch errors and unreadable assets → toast + problems panel.
- 1/2/4/8/16-bit PNG, palette and grayscale; interlaced warns.
- Unknown op, nonexistent path, saving without a path → explicit error.

## 2. QA tools

- `tests/run_all.sh` — everything: core demo, Python tests, JS tests (node), C
  reader, real DOM (chromium `--dump-dom`) and ISO mastering.
- `tests/browser/qa.js` — **real QA**: drives chromium through the Chrome DevTools
  Protocol (clicks, keyboard, drag) against the real server and collects the JS
  exceptions. `node tests/browser/qa.js [flow…]`, `QA_DEBUG=1` dumps the app
  state on failure. Every flow starts clean.

## 3. QA findings (real browser) and what was done

| # | Finding | Impact | Status |
|---|---|---|---|
| 1 | Enter in the dialogs ran **Cancel** (it was the first submit button of the `<form method=dialog>`) | creating a scene/character "did nothing" | fixed |
| 2 | The step fields (text, pos, type, options…) **did not apply** until pressing "Apply"; the rest of the inspector did apply on its own | lost edits, inconsistency | fixed: everything applies on change, no button |
| 3 | **Validate** with no problems said nothing | looked broken | fixed: "✓ project valid" / "N problems" |
| 4 | In a **confirmation** with no fields, Enter landed on Cancel (first focus) | delete did not delete | fixed: focus on Yes |
| 5 | An id rule with `display:flex` beat `[hidden]` | the preview bar stayed visible always | fixed |
| 6 | The choice's **black veil** was also drawn while editing | "everything goes dark and I don't know why" | fixed: soft preview + sign |
| 7 | **Old server** silently ignored new ops; busy port = traceback | "doesn't work on my side" | fixed: API version + `--restart` |
| 8 | **Save without a path** was a no-op; the project lived only in memory | lost work | fixed: save as + autosave + ● |
| 9 | The **choice** was edited in a "label -> scene" textarea | typo-prone | fixed: rows with a scene dropdown |
| 10 | The **animation params** were `k=v` text | you had to know the names | fixed: fields per type, with scrub |
| 11 | Adding a dialogue required: pick type, ＋, go to the inspector, type | slow for the most common thing | fixed: **quick dialogue** bar (Enter adds and continues) |
| 12 | Deleting a scene/character did not exist | dirty projects | fixed (with rules: never the last one; a character in use is refused and it says where) |

Harness false positives that were fixed in the harness (not in the app):
step count of the test project, synthetic Enter without `text`, flows that
depended on order (now every flow starts clean), the new scene brings an `end`
by design.

## 4. Vision backlog — done (2026-09-04, TDD + real QA per item)

| # | Feature | Where it ended up |
|---|---|---|
| 1 | **Expressions per character** — `sprite ana happy happy.png`, `show ana happy [pos]`; pos optional (keeps position) | format + validate, runtime, server, inspector (Character section / selector in show), outliner, HTML player, PS2 blob **v4** + C reader |
| 2 | **Background transition** `bg X fade=ms` (real crossfade) and **typing effect** in Play (⌨ cps; click completes, then advances) | runtime (tween), APNG preview, HTML player (#bg2), inspector |
| 3 | **Audio in the browser**: looping bgm and one-shot se (se_seq) during Play; ▶ to listen in the selectors | runtime, Play state, UI |
| 4 | **Multi-selection** (Shift/Ctrl+click), **Ctrl+C/V** between scenes, multiple Del | logic.js clickSelect, server paste_steps/del_steps |
| 5 | **Ctrl+F** search in dialogues and options, live results | logic.js searchSteps, dialog |
| 6 | **Flow view** ⌥: scene graph (BFS from start, red = no exit), click goes to the scene | logic.js sceneGraph, SVG |
| 7 | **Export** html / **vnp** / **iso** from the UI (blob of the in-memory project; ISO asks for the ELF and genisoimage) | server export_ps2, format dialog + browser |

Extra findings that came out in this round: Enter in a dialog with the focus on
a `<select>` did not accept (now Enter accepts from any field); the typing
effect made the first click not advance (by design: it completes the text;
the QA models it and the `tipeo` flow verifies it).

Left for later (blocking nothing): light theme / UI scaling, editor i18n,
dragging files onto the stage, shortcuts per step type, expressions and fade
in the PS2 player (the blob already carries the image per expression; the fade
and typing of the ELF are `ps2/main.c` work).

## 5. How to run the QA

```sh
./tests/run_all.sh                       # everything (includes qa.js if chromium is there)
node tests/browser/qa.js                 # just the user flows
QA_DEBUG=1 node tests/browser/qa.js play # one flow, with a state dump on failure
```
