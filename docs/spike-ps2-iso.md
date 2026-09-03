# Spike — generar un `.iso` booteable en PS2 desde una VN autoral

**Pregunta:** ¿podemos, con este proyecto, producir un `.iso` que corra en un
emulador de PS2 (PCSX2) y reproduzca una VN creada en VN Studio?

**Respuesta corta:** sí, es posible, y **de-riesgado en partes** por lo que ya
tenemos reverseado — pero el tramo "sale un ELF que bootea" es un proyecto de
**homebrew de PS2** aparte, no una extensión chica del exporter. Hay tres caminos;
el recomendado es un **ELF homebrew mínimo** que interpreta nuestro `.vn`.
Estimación del camino recomendado hasta "una escena real bootea en PCSX2":
**~1 semana** a proof-of-life, **~4–8 semanas** a un player usable.

> Spike = investigación acotada. No implementa nada; fija alcance, riesgos y el
> primer experimento a correr.

---

## Lo que YA tenemos (cimientos, cualquiera sea el camino)

- Formatos del juego resueltos: contenedor `.HD/.BIN`, codec (decode + `compress_store`),
  TIM2 (decode a RGBA), fuente BMP + mapeo. (capa 2)
- La API del engine mapeada (`docs/engine_api.md`) y 1920 escenas que parsean/transpilan.
- El **modelo de runtime** (bg + capas + animación por curvas/acciones + diálogo +
  choices + bgm/se) ya especificado y con implementación de referencia headless
  (`VNRuntime`) — sirve de **spec** para portarlo a PS2.
- El formato autoral `.vn` y su compilación.

## Lo que FALTA (piezas nuevas, por camino)

| Pieza | ¿Nueva? | Notas |
|---|---|---|
| **ELF homebrew** (GS 2D + input + lectura de datos) | **sí, grande** | PS2SDK/ps2dev; gsKit para blits; libpad; cdvd/isofs |
| **Encoder de textura** | depende | Camino A: **TIM2 encoder** con cuantización a paleta. B/C: subir **RGBA 32-bit** al GS → sin cuantizar en la 1ª versión |
| **Fuente con acentos** | sí | dibujar glifos latinos/acentuados + mapeo (compartido con la traducción) |
| **Mastering ISO9660** | sí, chico | `genisoimage` + `SYSTEM.CNF` apuntando al ELF |
| **Audio (SPU2 / bgm-se)** | sí | reproducir ADPCM por SPU2; formato `SOUND_ID` del juego no está reverseado → **diferible** |
| **Intérprete de escena en PS2** | sí | Camino A: emitir Squirrel del engine. B/C: intérprete propio del `.vn` compilado |

---

## Los tres caminos

### A. Reusar el juego como cáscara (repack en el engine de ZnT)
Emitir nuestras escenas como **Squirrel del engine** (usando `set/talk/select/next`
y el vocabulario `LayerModule`), codificar nuestras imágenes a **TIM2**,
`compress_store`, y remasterizar el ISO del juego.

- **A favor:** el engine, boot, input y (parte del) audio **ya funcionan**.
- **En contra:**
  - Necesita un **encoder TIM2** (cuantización a 256 colores + re-swizzle del CLUT).
  - La fuente sigue sin acentos (hay que dibujarlos — tarea abierta de la traducción).
  - **Legal:** el ISO resultante lleva el ELF y el engine **del juego con copyright**.
    Distribuir contenido original dentro de la cáscara de ZnT es turbio y raro
    (tu VN arrastra el motor y la marca de ZnT). Solo un **parche binario** sobre la
    copia del usuario es defendible, y esto no es un parche: es contenido nuevo.
  - **Riesgo de sectores:** si el ELF lee archivos por LBA absoluto (pregunta 5 del
    README, sin confirmar), cambiar tamaños rompe el layout → hay que reconstruir el
    ISO y quizá parchear la tabla de archivos.
- **Veredicto:** atajo técnico para "ver algo bootear", **no recomendado como producto**.

### B. Homebrew PS2 completo (nuestro engine en un ELF)
Portar el runtime a un ELF nativo (C/C++ con PS2SDK): GS, input, lectura de ISO,
un intérprete (Squirrel embebido o propio), animación, audio, saves.

- **A favor:** limpio de origen (código nuestro + assets del usuario), sin ZnT,
  `.iso` propio, legalmente sano.
- **En contra:** es **un engine de VN homebrew desde cero** — disciplina entera
  (GS, DMA, SPU2, memoria). **Meses.** Complejidad ALTA.
- **Veredicto:** el "camino correcto" a largo plazo, pero grande.

### C. ELF homebrew MÍNIMO que interpreta el `.vn` (recomendado)
Un ELF chico que **no** porta el engine de ZnT ni una VM Squirrel: compila el `.vn`
a un blob binario compacto y lo interpreta con lo justo — bg + sprites + texto +
choices + input. Animación/audio se agregan después.

- **A favor:**
  - **B/C no necesitan TIM2 ni cuantización** en la 1ª versión: el GS acepta
    texturas **32-bit (PSMCT32)** directas → subimos RGBA (más memoria, cero
    algoritmo nuevo). La cuantización a 8-bit es optimización posterior.
  - Reusa nuestro modelo de escena como spec; el `.vn`→blob lo hace nuestro SDK.
  - Legalmente limpio.
  - **PCSX2 bootea un `.elf` directo** (Run ELF) → iterás sin masterizar ISO; el
    ISO queda como último paso de empaquetado.
- **En contra:** igual hay que aprender GS/gsKit/libpad y escribir C de PS2.
- **Veredicto:** ruta realista a "una VN original bootea en PCSX2".

---

## Plan por etapas (camino C)

1. **Toolchain** — imagen `ps2dev` (docker) con `mips64r5900el-ps2-elf-gcc`, gsKit,
   libpad. *Bajo esfuerzo.*
2. **Proof-of-life ELF** — limpiar pantalla, subir una textura RGBA y dibujar un
   string con una fuente bitmap; **bootear en PCSX2** (Run ELF). *~días–1 semana.*
3. **Compilador `.vn` → blob** — en nuestro SDK (Python): serializar escenas,
   personajes, y **atlas de assets** (PNG→RGBA crudo o TIM2). Con self-check. *~días.*
4. **Player mínimo (ELF)** — leer el blob, componer bg+sprites (nuestro modelo Z),
   caja de texto + fuente con acentos, `choice` con el pad, `goto/end`. *~semanas.*
5. **Mastering ISO** — `SYSTEM.CNF` (`BOOT2 = cdrom0:\VN.ELF;1`) + `genisoimage`;
   probar el `.iso` en PCSX2. *~días.*
6. **Después:** animación (curvas/acciones ya especificadas), audio SPU2, saves.

**Primer experimento (1–2 días, máxima información):**
levantar `ps2dev`, compilar el sample gsKit que dibuja un sprite, **bootearlo en
PCSX2**, y en paralelo escribir en el SDK un **encoder de textura** (empezar por
RGBA→PSMCT32; validar round-trip contra nuestro decoder). Eso confirma toolchain +
render + el puente de assets, que es el 80% del riesgo.

---

## Complejidad y riesgo (resumen)

| Dimensión | A (cáscara ZnT) | B (homebrew full) | C (ELF mínimo) |
|---|---|---|---|
| Esfuerzo a "bootea algo" | medio | alto | **medio** |
| Esfuerzo a paridad | medio-alto | muy alto | alto |
| Piezas nuevas grandes | TIM2 encoder, font | engine entero | ELF + font (32-bit evita cuantizar) |
| Legal | **problemático** | limpio | **limpio** |
| Riesgo técnico | sectores/ISO, engine ajeno | amplio | acotado y por etapas |
| Reusa lo hecho | codec/TIM2/containers | modelo de escena | **modelo + .vn + SDK** |

**Conclusión.** Es viable y vale la pena; el atajo (A) no conviene por lo legal y
por depender del motor ajeno. El objetivo — *tu VN original booteando en PCSX2* —
se alcanza mejor con **C**: un ELF homebrew mínimo que interpreta el `.vn`, con el
GS en 32-bit para saltear la cuantización al principio, y PCSX2 booteando el ELF
directo para iterar rápido. El SDK actual ya cubre el lado autoral y de datos; lo
nuevo y grande es el ELF de PS2. Próximo paso concreto: el experimento de 1–2 días
de arriba.
