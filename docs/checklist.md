# Checklist para cerrar VN Studio y el player PS2

Cada ítem tiene su check automático en `tests/checklist.sh`, que los corre **en
orden** y se frena en el primero que falla. Marcar `[x]` sólo cuando el check pasa. Estado: **19/19 en verde** (2026-09-09).

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
- [x] 11. BGM: el thread de audio alimenta el stream PCM (prioridad + audsrv de un solo thread).
- [x] 12. ISO booteable: arranca del CD y lee a más de 1 MB/s (datos alineados al sector).
- [x] 13. Ramificación verificada sin joystick: choice, goto entre escenas y end (autoplay).
- [x] 14. El texto del diálogo corta por palabra, no a mitad (`ps2/text.c`).
- [x] 15. Texturas de 8 bits con paleta cuando no se pierde nada (4x menos VRAM y disco).
- [x] 16. Play del editor con los dos ritmos: paso a paso y como el jugador.
- [x] 17. Formato de partida con magic, versión y CRC (aguanta un archivo pisado).
- [x] 18. Guardar y cargar en la memory card, reanudando a mitad de escena.
- [x] 19. Menú de pausa (Start), historial de diálogos (Select) y avance rápido (Triángulo).

## Cómo correr
```sh
tests/checklist.sh            # todo, en orden
tests/checklist.sh 4          # sólo desde el ítem 4
```
