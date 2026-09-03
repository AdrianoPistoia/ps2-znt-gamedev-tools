# API del engine hacia los scripts Squirrel

Catálogo de qué expone el motor de *Zero no Tsukaima: KtHC* al código Squirrel de
las escenas. Es el insumo de la **capa 1** (runtime off-console): todo lo marcado
como *nativo* hay que implementarlo en el host; todo lo *script-side* corre tal
cual en el intérprete.

**Cómo se obtuvo** (`python -m znt scan scripts/ --elf SLPS_257.09`): sobre las
1920 escenas se separan las *definiciones* (class/function/local/slot) de las
*llamadas* (`nombre(` global vs `.método(`). Un identificador llamado como función
global y **nunca definido en el corpus** es un nativo candidato; se confirma
cruzándolo con los strings del ELF, donde SqPlus registra cada binding por nombre.
Resultado: **36 nativos globales candidatos, 35 confirmados en el ELF** (`[E]`).

> Heurístico por regex, no un parser de Squirrel. Las firmas son *ejemplos de
> uso* reales, no declaraciones: dan aridad y tipos por inspección, no contrato.

---

## 1. Nativos globales (implementar en el host)

Agrupados por subsistema. Entre paréntesis, un uso real del corpus.

### Audio
- `MusicPlay(canal, name, volumen)` [E] — reproduce BGM/SE en un canal (0 = música, 1 = SE).
- `MusicStop(canal, tiempo)` [E] — para el canal, con fade opcional en ms.
- `MusicFade(canal, volumen)` [E] — fade al volumen dado.
- `MusicPlayingNow(canal)` [E] — ¿suena algo en el canal? (0/id).
- `MusicCurrent(...)` [E] — pista actual del canal.

### Diálogo / voz
- `Talk(0, voice)` [E] — arranca la reproducción de una línea de voz.
- `TalkLength(0)` [E] — largo de la voz en curso (para timing del texto).
- `TalkStop(0)` [E] — corta la voz.
- `Talkingnow(...)` [E] — ¿hay voz sonando?
- `isVoiceOn(nameVoice)` [E] — ¿la voz de este personaje está activada en opciones?
- `AddHistory(talkName, nameVoice, voiceId, text)` [E] — empuja la línea al backlog.
- `getCharSpeed()` [E] — velocidad de tipeo configurada.
- `getAutoWait()` [E] — espera del modo auto.
- `isAllSkip()` [E] — ¿skip global activo?

### Progreso / guardado
- `getReaded(scene)` [E] / `setReaded(scene, line)` [E] — marca de líneas ya leídas por escena (para el skip de lo leído).
- `SetClearFlag(route)` [E] — marca una ruta como terminada.
- `SetMovieNo(num)` [E] — registra el último movie visto.

### Elección / mapas de navegación (menús del juego)
- `SelectAdd(text)` [E] / `SelectClear()` [E] — arma la lista de opciones de un `select`.
- `MoveAdd(room, pose)` [E] / `MoveClear()` [E] — destinos del mapa de movimiento.
- `DateAdd(chr)` [E] / `DateClear()` [E] — candidatos del sistema de citas.
- `BattleAdd(name)` [E] / `BattleClear()` [E] / `BattleEnemy(pos, name, pose)` [E] — setup de batalla.

### Sistema / entrada / carga
- `_vibrate(n)` [E] — vibración del control (n intensidad/duración).
- `swapStart(name, time)` [E] / `swapStop()` [E] — transición ("swap") entre pantallas.
- `loadStop()` [E] — detiene una carga en curso.
- `isDriveImage()` [E] — ¿está leyendo del disco? (para gating de carga).
- `getThread(scene)` [E] — obtiene el hilo/corrutina de una escena (control de flujo entre escenas).

### Callback (dirección inversa: el engine llama al script)
- `onSEFadeComplsted(...)` — **único no confirmado en el ELF**. Nombre mal escrito
  ("Complsted"); es un handler que el motor invoca al terminar un fade de SE. No es
  un nativo a implementar sino un hook que el script define y el engine llama.

---

## 2. Clases nativas y sus métodos

Dos clases se instancian desde el script pero las define el engine. Sus métodos
también aparecen como strings en el ELF.

### `Layer(esForeground)` — capa gráfica
Instancia: `Layer(fore)`, `Layer(true)`. Es la primitiva de dibujo; todo lo visual
(fondos, sprites, UI) es un Layer. La biblioteca Squirrel (§3) la envuelve.

Métodos observados (con ejemplo de uso):
- `loadImage(imageId)` — carga una textura (índice de SCENEDAT/NORMAL) en la capa.
- `loadChangeImage(image, tipo, frameTime)` — carga con transición animada.
- `copyImage(otherLayer)` — copia el contenido de otra capa.
- `show(bool)` — visibilidad.
- `setPos(x, y)` — posición.
- `setOpacity(a)` / `getOpacity()` — alfa 0..100.
- `setColor(r, g, b, a)` — tinte (valores ~0..100, alfa 0..128).
- `setZoom(z)` — escala.
- `setRotate(áng)` — rotación.
- `setAffineOrigin(ax, ay)` — origen de las transformaciones afines.
- `setLevel(n)` — orden Z (0 = fondo, mayor = adelante).
- `setActionOffset(dx, dy)` — desplazamiento temporal (para vibración/shake).
- `stopAction()` — corta la acción en curso.
- `getWidth()` / `getHeight()` — dimensiones de la imagen cargada.
- `fadeIn(frames)` / `fadeOut(frames)` — fades sobre la capa.
- `sync(fore)` — sincroniza doble buffer fore/back.

### `MessageWindow(x, y, modo)` — cuadro de diálogo
Instancia: `MessageWindow(48, 336, 1)`, `MessageWindow(xpos, ypos, 8)`.

Métodos observados:
- `write(texto)` — escribe/anima el texto (acepta concatenación con datos del juego).
- `ShowNamePlate(name)` — muestra la placa con el nombre del hablante.
- `showCursor(bool)` — cursor de "seguir".
- `fore()` / `back(bool)` — traer al frente / mandar atrás.
- `clear()` — limpia el cuadro.

> Otros `.método()` llamados (`.len`, `.append`, `.slice`, `.tointeger`,
> `.tofloat`, `.remove`, `.getstatus`, `.call`, `.wakeup`) son **delegates
> builtin de Squirrel** (arrays, strings, enteros, hilos), no del engine: los
> aporta la VM, no hay que implementarlos como API del juego.

---

## 3. Biblioteca script-side (corre tal cual en el intérprete)

No hay que reimplementar nada de esto: son `.nut` del propio juego. La capa 1 solo
tiene que **ejecutarlos**. Definen 40 clases e incluyen todo el framework de
animación construido sobre el `Layer` nativo:

- **Wrappers de capa**: `AdvLayer`, `BasicLayer`, `ActionLayer`, `ScreenLayer`.
- **Módulos de animación** (`LayerModule` y familia): `LayerMoveModule`,
  `LayerNormalMoveModule`, `LayerAccelMoveModule`, `LayerDecelMoveModule`,
  `LayerRotateModule`, `LayerNormalRotateModule`, `LayerZoomModule`,
  `LayerNormalZoomModule`, `LayerFadeModeModule`, `LayerFadeToModeModule`,
  `LayerFallActionModule`, `LayerJumpActionModule`, `LayerJumpOnceActionModule`,
  `LayerVibrateActionModule`, `LayerWaveActionModule`, `LayerWaveOnceActionModule`,
  `LayerModeModule`.
- **Audio script-side**: `AdvBGM`, `AdvSE`, `AdvSoundTrack` (envuelven `Music*`).
- **Estados/otros**: `Item`, y enums de escena (`BATTLE`, `MOVE`, `DATE`, `SELECT`,
  `MOVIE`, `WAIT`, `CHANGE`, `DONE`, `COFFEE`, `Like`, `Tundele`, `SYSSAVE`).

**Comandos de escena** definidos en la biblioteca (por eso NO salen como nativos):
`reset`, `init`, `initVariable`, `select`, `selectInit`, `restrict`, `fadeIn`,
`fadeOut`, `voice`. Son el "lenguaje" que usa cada escena — 1505 empiezan con
`if (`, 395 con `reset();`, 12 con `selectInit();`.

---

## 4. Builtins de Squirrel a proveer (los da la VM)

Si la capa 1 usa un runtime Squirrel real (recomendado: no reescribir la VM),
esto viene gratis: `print`, `format`, `array`, `type`, funciones de `math`
(`sin`, `cos`, `sqrt`, `rand`, `min`, `max`, `abs`, `floor`, `PI`…), y los
delegates de array/string/tabla/hilo (`len`, `append`, `slice`, `find`, `tointeger`,
`getstatus`, `wakeup`, `call`…). El corpus usa corrutinas (`getThread`, `.wakeup`,
`.getstatus`), así que el runtime tiene que soportar `newthread`/`suspend`.

---

## 5. Qué implica para la capa 1

| Pieza | De dónde sale | Trabajo en capa 1 |
|---|---|---|
| VM Squirrel + builtins + corrutinas | runtime existente (bindear, no reescribir) | integrar |
| Clases nativas `Layer`, `MessageWindow` | **implementar en el host** | dibujo TIM2 + texto con la fuente (capa 2 ya lee ambos) |
| 36 nativos globales (audio, voz, flags, select…) | **implementar en el host** | audio con stubs primero; flags/select/history con estado en memoria |
| Biblioteca de animación + comandos de escena | `.nut` del juego (capa 2 los extrae) | ejecutar tal cual |

El camino mínimo para "una escena en una ventana": VM + `Layer` (loadImage/show/
setPos/setLevel) + `MessageWindow` (write/ShowNamePlate) + `reset`/`select`, con el
resto de nativos como stubs que no rompan el flujo.

*Regenerar este catálogo:* `python -m znt scan <scripts/> --elf <ELF> --json api.json`.
