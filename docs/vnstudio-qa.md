# VN Studio (web) — mapa de features y QA

Estado al 2026-09-04, rama `web-studio`. El editor corre sobre el engine real
(`znt.vnstudio.VNRuntime`); el server Python es la fuente de verdad y el browser
compone con CSS. Este documento es el inventario + lo que encontró el QA + lo que
falta para la visión.

## 1. Mapa de features (lo que existe)

### Proyecto
| Feature | Dónde | Cómo |
|---|---|---|
| Nuevo / Abrir / Guardar / Guardar como / Exportar HTML | topbar | diálogos propios + explorador de archivos 📁 |
| Validar (gotos rotos, personajes inexistentes, escenas sin salida, assets) | topbar | panel de problemas en el inspector |
| Undo / Redo | topbar, Ctrl+Z / Ctrl+Y | historial en el server |
| Server: `--restart`, `--stop`, `--port`, aviso de versión de API | CLI | pidfile + barrido de /proc |

### Escenas y pasos
| Feature | Dónde |
|---|---|
| Escenas: agregar, duplicar, renombrar, subir/bajar | outliner |
| Pasos: agregar (10 tipos), duplicar, borrar, mover, reordenar arrastrando | timeline |
| Timeline con pistas por tipo, regla, playhead, scrub, Ctrl+rueda zoom | timeline |
| Inspector por tipo de paso con secciones plegables | inspector |
| Campos numéricos con scrub (arrastrar la etiqueta, Shift fino) | inspector |

### Personajes y capas
| Feature | Dónde |
|---|---|
| Crear personaje (id, nombre, color) | topbar ＋ Personaje |
| Sección Personaje única: elegir, nombre, color, sprite (📁/⇧ subir), renombrar id | inspector |
| Capas del paso (al frente primero), selección sincronizada, doble click → su `show` | outliner |
| Arrastrar sprite con snap y guías (Shift libre); handles de esquina = zoom | viewport |
| Orden Z ▲/▼, opacidad, tinte, x/y/z/zoom | inspector |

### Reproducción
| Feature | Dónde |
|---|---|
| Play desde el paso elegido; click/Espacio/⏭ avanza; choices funcionan | viewport |
| El timeline sigue al runtime (escena y paso), click en clip = reproducir desde ahí | timeline |
| UI apagada en Play salvo juego + timeline | todo |
| ▶ Probar paso: transición renderizada por el engine (APNG), se cierra sola | viewport |
| Guías (centro/tercios/zona segura), ojo para apagar diálogo/opciones | viewport |

### Robustez
- Errores del server, del fetch y de assets ilegibles → toast + panel de problemas.
- PNG 1/2/4/8/16 bits, paleta y gris; entrelazado avisa.
- Op desconocida, ruta inexistente, guardar sin ruta → error explícito.

## 2. Herramientas de QA

- `tests/run_all.sh` — todo: demo del core, tests Python, tests JS (node), lector C,
  DOM real (chromium `--dump-dom`) y masterizado ISO.
- `tests/browser/qa.js` — **QA real**: maneja chromium por Chrome DevTools
  Protocol (clicks, teclado, arrastre) contra el server real y junta las
  excepciones JS. `node tests/browser/qa.js [flujo…]`, `QA_DEBUG=1` vuelca el
  estado de la app al fallar. Cada flujo arranca limpio.

## 3. Hallazgos del QA

(se completa abajo a medida que se corre)

## 4. Gaps para la visión

(ídem)
