# Checklist para cerrar VN Studio y el player PS2

Cada ítem tiene su check automático en `tests/checklist.sh`, que los corre **en
orden** y se frena en el primero que falla. Marcar `[x]` sólo cuando el check pasa. Estado: **9/9 en verde** (2026-09-08).

## VN Studio
- [x] 1. Grupos (Ctrl+G): el flujo QA `grupos` pasa y el trabajo está commiteado.
- [x] 9. `docs/authoring.md` documenta todas las ops del parser.

## Player PS2
- [x] 2. Toolchain: `docker run ps2dev/ps2dev make` produce `ps2/ZNTVN.ELF`.
- [x] 3. Boot: el ELF arranca en PCSX2 con un blob mínimo (`host:ZNTVN.VNP`).
- [x] 4. Memoria: el ELF no carga el blob entero; imágenes por demanda (fseek).
- [x] 5. Fade de fondo: `bg X fade=ms` viaja en el blob (v5) y el ELF hace crossfade.
- [x] 6. Tween en `y`: `animate move y=` viaja en el blob y el ELF lo interpola.
- [x] 7. Tipeo: el ELF revela el texto por tiempo; el primer click completa.
- [x] 8. SE: efectos por ADPCM (`audsrv_load_adpcm`), encoder WAV→VAG en el SDK.

## Cómo correr
```sh
tests/checklist.sh            # todo, en orden
tests/checklist.sh 4          # sólo desde el ítem 4
```
