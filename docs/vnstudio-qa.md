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

## 3. Hallazgos del QA (browser real) y qué se hizo

| # | Hallazgo | Impacto | Estado |
|---|---|---|---|
| 1 | Enter en los diálogos ejecutaba **Cancelar** (era el primer botón submit del `<form method=dialog>`) | crear escena/personaje "no hacía nada" | arreglado |
| 2 | Los campos del paso (texto, pos, tipo, opciones…) **no aplicaban** hasta tocar "Aplicar"; el resto del inspector sí aplicaba solo | edits perdidos, inconsistencia | arreglado: todo aplica al cambiar, sin botón |
| 3 | **Validar** sin problemas no decía nada | parecía roto | arreglado: "✓ proyecto válido" / "N problemas" |
| 4 | En una **confirmación** sin campos, Enter caía en Cancelar (primer foco) | borrar no borraba | arreglado: foco en Sí |
| 5 | Una regla de id con `display:flex` le ganaba a `[hidden]` | la barra del preview quedaba visible siempre | arreglado |
| 6 | El **velo negro** del choice se dibujaba también en edición | "se oscurece todo y no sé por qué" | arreglado: previsualización suave + cartel |
| 7 | **Server viejo** ignoraba ops nuevas en silencio; puerto ocupado = traceback | "no funciona de mi lado" | arreglado: versión de API + `--restart` |
| 8 | **Guardar sin ruta** era un no-op; el proyecto vivía sólo en memoria | trabajo perdido | arreglado: guardar como + autosave + ● |
| 9 | El **choice** se editaba en un textarea "etiqueta -> escena" | propenso a typos | arreglado: filas con desplegable de escenas |
| 10 | Los **params de animación** eran texto `k=v` | había que saber los nombres | arreglado: campos por tipo, con scrub |
| 11 | Agregar un diálogo requería: elegir tipo, ＋, ir al inspector, tipear | lento para lo más común | arreglado: barra de **diálogo rápido** (Enter agrega y sigue) |
| 12 | Borrar escena/personaje no existía | proyectos sucios | arreglado (con reglas: nunca la última; personaje en uso se niega y dice dónde) |

Falsos positivos del harness que se corrigieron en el harness (no en la app):
conteo de pasos del proyecto de prueba, Enter sintético sin `text`, flujos que
dependían del orden (ahora cada flujo arranca limpio), la escena nueva trae un
`end` por diseño.

## 4. Gaps para la visión (backlog, por valor)

1. **Expresiones por personaje** (`show ana feliz`): hoy hay un sprite por
   personaje. Es lo que más le falta a una VN real. Toca formato `.vn`, engine,
   inspector (selector de expresión) y player HTML/PS2.
2. **Transiciones de fondo** (fade/crossfade) y **efecto de tipeo** del texto en
   Play y en el player exportado.
3. **Audio en el browser**: escuchar bgm/se al elegirlos y durante Play.
4. **Copiar/pegar y multi-selección** de pasos (también entre escenas).
5. **Búsqueda** de texto en diálogos (ir al paso).
6. **Vista de flujo** (grafo de escenas con gotos/choices); validar cubre lo básico.
7. **Exportar ISO/ELF desde la UI** (hoy `python -m znt iso build`).
8. **Atajos de tipo de paso** (p.ej. B fondo, H hide) y **arrastrar un archivo**
   al escenario para crear/asignar sprite o fondo.
9. Tema claro y escalado de UI; i18n del editor.

## 5. Cómo correr el QA

```sh
./tests/run_all.sh                       # todo (incluye qa.js si hay chromium)
node tests/browser/qa.js                 # sólo los flujos de usuario
QA_DEBUG=1 node tests/browser/qa.js play # un flujo, con volcado de estado al fallar
```
