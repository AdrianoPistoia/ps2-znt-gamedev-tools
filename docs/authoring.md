# Authoring a new VN (layer 3)

You write your story in a plain-text `.vn` file and `znt vn build` compiles it into a
**single-file HTML player** (scene JSON + a tiny JS engine + embedded assets) that
plays in any browser: click or space to advance, buttons to choose. It runs on the
layer-1 scene model (background + sprites + dialogue box), with no dependencies.

```sh
python3 -m znt vn build story.vn player.html
python3 -m znt vn demo-build player.html          # generates a playable example
```

## `.vn` format

One directive per line. `#` is a comment.

### Header
```
title: My Story
character saito "Saito" color=#7cc4ff
character louise "Louise" color=#ff9ec2
sprite saito saito.png            # optional: character art (placeholder otherwise)
```
`narrator` exists by default (empty name, for narration).

### Scenes and steps
```
scene intro                       # opens a scene; steps follow until the next 'scene'
  bg grad:#101830,#2a4a80         # background: vertical gradient (top,bottom)
  bg #223                         #   or solid color
  bg room.png                     #   or image (embedded in the HTML / goes into the PS2 blob)
  bg night.png fade=600           #   fade=ms: crossfade from the previous background
  show louise left                # show sprite: left | center | right (x=-180 / 0 / 180)
  show louise happy right         # with expression (see 'sprite'); without a position it keeps the one it had
  show louise x=40 y=0 z=5 zoom=120 opacity=80 tint=#ff8080   # layer: x/y in px from center/floor,
                                  #   higher z = in front, zoom and opacity in %, tint color
  hide louise
  animate louise move x=200 y=-40 curve=accel time=400   # tween to that x/y (curve: linear|accel|decel)
  animate louise wave vib=16 cycle=340                    # actions: wave | waveonce | jump | jumponce
  animate louise fall dist=120 time=600                   #   | fall (dist, time) | vibrate (vib, wait)
  louise: Awake again?            # dialogue: <character>: text
  * A silence filled the room.    # narration (same as  narrator: ...)
  bgm theme.wav                   # looping music (PCM WAV for PS2; the HTML takes whatever the browser plays)
  bgm stop
  se hit.wav                      # sound effect (PCM WAV; on PS2 it is converted to ADPCM at compile time)
  group intro                     # group … endgroup: in Play, all those steps run with one click
    show saito right
    saito: Hello!
  endgroup
  choice                          # branching choice
    - Press on -> closer          #   - label -> target_scene
    - Change the subject -> subject
  goto ending                     # jump to another scene
  end                             # end of the game
```

Header (before the first `scene`):

```
title: My novel
character louise "Louise" color=#ff9ec2   # id, display name and name color
sprite louise louise.png                  # the character's base sprite
sprite louise happy louise_happy.png      # an expression: `show louise happy`
```

Rules: each `- option` attaches to the immediately preceding `choice`; `goto`
and `end` cut the scene's flow; the game starts at the **first** declared scene.
Lines starting with `#` are comments.

## Assets

`bg file.png` and `sprite <char> file.png` are resolved **relative to the `.vn`**
and embedded as data URIs, so the resulting HTML is self-contained and shareable
(it does not need the assets folder next to it). If a character has no `sprite`, a
placeholder with its initial and its color is drawn.

## Minimal example

```
title: Test
character a "Ana" color=#8fd
scene one
  bg grad:#202040,#404080
  show a center
  a: Hello.
  * End of the test.
  end
```

*Scope:* the same `.vn` comes out as an HTML player (`znt vn build`) or as a blob for the
native PS2 player (`znt iso build`, see [`build-ps2.md`](build-ps2.md)). Packing it
into the original game's format (.HD/.BIN, the engine's Squirrel) is not included.
