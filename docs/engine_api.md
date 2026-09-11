# Engine API towards the Squirrel scripts

Catalogue of what the *Zero no Tsukaima: KtHC* engine exposes to the Squirrel code
of the scenes. It is the input for **layer 1** (off-console runtime): everything
marked *native* has to be implemented on the host; everything *script-side* runs
as-is in the interpreter.

**How it was obtained** (`python -m znt scan scripts/ --elf SLPS_257.09`): over the
1920 scenes, *definitions* (class/function/local/slot) are separated from *calls*
(global `name(` vs `.method(`). An identifier called as a global function and
**never defined in the corpus** is a candidate native; it is confirmed by
cross-referencing it with the ELF strings, where SqPlus registers every binding by
name. Result: **36 candidate global natives, 35 confirmed in the ELF** (`[E]`).

> Regex heuristic, not a Squirrel parser. The signatures are real *usage
> examples*, not declarations: they give arity and types by inspection, not a contract.

---

## 1. Global natives (implement on the host)

Grouped by subsystem. In parentheses, a real usage from the corpus.

### Audio
- `MusicPlay(canal, name, volumen)` [E] — plays BGM/SE on a channel (0 = music, 1 = SE).
- `MusicStop(canal, tiempo)` [E] — stops the channel, with optional fade in ms.
- `MusicFade(canal, volumen)` [E] — fade to the given volume.
- `MusicPlayingNow(canal)` [E] — is anything playing on the channel? (0/id).
- `MusicCurrent(...)` [E] — current track of the channel.

### Dialogue / voice
- `Talk(0, voice)` [E] — starts playback of a voice line.
- `TalkLength(0)` [E] — length of the voice in progress (for text timing).
- `TalkStop(0)` [E] — cuts the voice.
- `Talkingnow(...)` [E] — is a voice playing?
- `isVoiceOn(nameVoice)` [E] — is this character's voice enabled in the options?
- `AddHistory(talkName, nameVoice, voiceId, text)` [E] — pushes the line to the backlog.
- `getCharSpeed()` [E] — configured typing speed.
- `getAutoWait()` [E] — auto-mode wait.
- `isAllSkip()` [E] — is global skip active?

### Progress / saving
- `getReaded(scene)` [E] / `setReaded(scene, line)` [E] — already-read line mark per scene (for skipping read text).
- `SetClearFlag(route)` [E] — marks a route as finished.
- `SetMovieNo(num)` [E] — records the last movie watched.

### Choice / navigation maps (game menus)
- `SelectAdd(text)` [E] / `SelectClear()` [E] — builds the option list of a `select`.
- `MoveAdd(room, pose)` [E] / `MoveClear()` [E] — destinations of the movement map.
- `DateAdd(chr)` [E] / `DateClear()` [E] — candidates of the dating system.
- `BattleAdd(name)` [E] / `BattleClear()` [E] / `BattleEnemy(pos, name, pose)` [E] — battle setup.

### System / input / loading
- `_vibrate(n)` [E] — controller vibration (n intensity/duration).
- `swapStart(name, time)` [E] / `swapStop()` [E] — transition ("swap") between screens.
- `loadStop()` [E] — stops a load in progress.
- `isDriveImage()` [E] — is it reading from the disc? (for load gating).
- `getThread(scene)` [E] — gets the thread/coroutine of a scene (flow control between scenes).

### Callback (reverse direction: the engine calls the script)
- `onSEFadeComplsted(...)` — **the only one not confirmed in the ELF**. Misspelled
  name ("Complsted"); it is a handler the engine invokes when an SE fade ends. Not
  a native to implement but a hook the script defines and the engine calls.

---

## 2. Native classes and their methods

Two classes are instantiated from the script but defined by the engine. Their
methods also appear as strings in the ELF.

### `Layer(esForeground)` — graphics layer
Instance: `Layer(fore)`, `Layer(true)`. It is the drawing primitive; everything
visual (backgrounds, sprites, UI) is a Layer. The Squirrel library (§3) wraps it.

Observed methods (with usage example):
- `loadImage(imageId)` — loads a texture (SCENEDAT/NORMAL index) into the layer.
- `loadChangeImage(image, tipo, frameTime)` — loads with an animated transition.
- `copyImage(otherLayer)` — copies the content of another layer.
- `show(bool)` — visibility.
- `setPos(x, y)` — position.
- `setOpacity(a)` / `getOpacity()` — alpha 0..100.
- `setColor(r, g, b, a)` — tint (values ~0..100, alpha 0..128).
- `setZoom(z)` — scale.
- `setRotate(ang)` — rotation.
- `setAffineOrigin(ax, ay)` — origin of the affine transforms.
- `setLevel(n)` — Z order (0 = back, higher = front).
- `setActionOffset(dx, dy)` — temporary offset (for vibration/shake).
- `stopAction()` — cuts the action in progress.
- `getWidth()` / `getHeight()` — dimensions of the loaded image.
- `fadeIn(frames)` / `fadeOut(frames)` — fades on the layer.
- `sync(fore)` — syncs the fore/back double buffer.

### `MessageWindow(x, y, modo)` — dialogue box
Instance: `MessageWindow(48, 336, 1)`, `MessageWindow(xpos, ypos, 8)`.

Observed methods:
- `write(texto)` — writes/animates the text (accepts concatenation with game data).
- `ShowNamePlate(name)` — shows the plate with the speaker's name.
- `showCursor(bool)` — "continue" cursor.
- `fore()` / `back(bool)` — bring to front / send back.
- `clear()` — clears the box.

> Other `.method()` calls (`.len`, `.append`, `.slice`, `.tointeger`,
> `.tofloat`, `.remove`, `.getstatus`, `.call`, `.wakeup`) are **Squirrel builtin
> delegates** (arrays, strings, integers, threads), not the engine's: the VM
> provides them, they do not have to be implemented as game API.

---

## 3. Script-side library (runs as-is in the interpreter)

None of this has to be reimplemented: they are the game's own `.nut`. Layer 1 only
has to **execute them**. They define 40 classes and include the whole animation
framework built on top of the native `Layer`:

- **Layer wrappers**: `AdvLayer`, `BasicLayer`, `ActionLayer`, `ScreenLayer`.
- **Animation modules** (`LayerModule` and family): `LayerMoveModule`,
  `LayerNormalMoveModule`, `LayerAccelMoveModule`, `LayerDecelMoveModule`,
  `LayerRotateModule`, `LayerNormalRotateModule`, `LayerZoomModule`,
  `LayerNormalZoomModule`, `LayerFadeModeModule`, `LayerFadeToModeModule`,
  `LayerFallActionModule`, `LayerJumpActionModule`, `LayerJumpOnceActionModule`,
  `LayerVibrateActionModule`, `LayerWaveActionModule`, `LayerWaveOnceActionModule`,
  `LayerModeModule`.
- **Script-side audio**: `AdvBGM`, `AdvSE`, `AdvSoundTrack` (wrap `Music*`).
- **States/other**: `Item`, and scene enums (`BATTLE`, `MOVE`, `DATE`, `SELECT`,
  `MOVIE`, `WAIT`, `CHANGE`, `DONE`, `COFFEE`, `Like`, `Tundele`, `SYSSAVE`).

**Scene commands** defined in the library (which is why they do NOT show up as natives):
`reset`, `init`, `initVariable`, `select`, `selectInit`, `restrict`, `fadeIn`,
`fadeOut`, `voice`. They are the "language" every scene uses — 1505 start with
`if (`, 395 with `reset();`, 12 with `selectInit();`.

---

## 4. Squirrel builtins to provide (the VM gives them)

If layer 1 uses a real Squirrel runtime (recommended: do not rewrite the VM),
this comes for free: `print`, `format`, `array`, `type`, `math` functions
(`sin`, `cos`, `sqrt`, `rand`, `min`, `max`, `abs`, `floor`, `PI`…), and the
array/string/table/thread delegates (`len`, `append`, `slice`, `find`, `tointeger`,
`getstatus`, `wakeup`, `call`…). The corpus uses coroutines (`getThread`, `.wakeup`,
`.getstatus`), so the runtime has to support `newthread`/`suspend`.

---

## 5. What it means for layer 1

| Piece | Where it comes from | Work in layer 1 |
|---|---|---|
| Squirrel VM + builtins + coroutines | existing runtime (bind, do not rewrite) | integrate |
| Native classes `Layer`, `MessageWindow` | **implement on the host** | TIM2 drawing + text with the font (layer 2 already reads both) |
| 36 global natives (audio, voice, flags, select…) | **implement on the host** | audio with stubs first; flags/select/history with in-memory state |
| Animation library + scene commands | the game's `.nut` (layer 2 extracts them) | run as-is |

The minimal path to "a scene in a window": VM + `Layer` (loadImage/show/
setPos/setLevel) + `MessageWindow` (write/ShowNamePlate) + `reset`/`select`, with the
rest of the natives as stubs that do not break the flow.

*Regenerate this catalogue:* `python -m znt scan <scripts/> --elf <ELF> --json api.json`.
