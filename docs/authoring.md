# Autoría de una VN nueva (capa 3)

Escribís tu historia en un archivo `.vn` de texto y `znt vn build` la compila a un
**player HTML de una sola pieza** (JSON de escenas + motorcito JS + assets
embebidos), que se juega en cualquier browser: click o espacio para avanzar,
botones para elegir. Corre sobre el modelo de escena de la capa 1 (fondo +
sprites + cuadro de diálogo), sin dependencias.

```sh
python3 -m znt vn build historia.vn player.html
python3 -m znt vn demo-build player.html          # genera un ejemplo jugable
```

## Formato `.vn`

Una directiva por línea. `#` es comentario.

### Cabecera
```
title: Mi Historia
character saito "Saito" color=#7cc4ff
character louise "Louise" color=#ff9ec2
sprite saito saito.png            # opcional: arte del personaje (si no, placeholder)
```
`narrator` existe por defecto (nombre vacío, para narración).

### Escenas y pasos
```
scene intro                       # abre una escena; los pasos siguen hasta el próximo 'scene'
  bg grad:#101830,#2a4a80         # fondo: degradé
  bg #223                         #   o color sólido
  bg cuarto.png                   #   o imagen (se embebe en el HTML)
  show louise left                # mostrar sprite: left | center | right
  hide louise
  louise: ¿Otra vez despierto?    # diálogo: <personaje>: texto
  * Un silencio llenó la sala.    # narración (equivale a  narrator: ...)
  choice                          # elección ramificada
    - Insistir -> acerca          #   - etiqueta -> escena_destino
    - Cambiar de tema -> tema
  goto fin                        # saltar a otra escena
  end                             # fin del juego
```

Reglas: cada `- opción` se engancha al `choice` inmediatamente anterior; `goto`
y `end` cortan el flujo de la escena; el juego arranca en la **primera** escena
declarada.

## Assets

`bg archivo.png` y `sprite <char> archivo.png` se resuelven **relativos al `.vn`**
y se embeben como data URI, así el HTML resultante es autocontenido y compartible
(no necesita la carpeta de assets al lado). Si un personaje no tiene `sprite`, se
dibuja un placeholder con su inicial y su color.

## Ejemplo mínimo

```
title: Prueba
character a "Ana" color=#8fd
scene uno
  bg grad:#202040,#404080
  show a center
  a: Hola.
  * Fin de la prueba.
  end
```

*Alcance:* player PC (browser). Empaquetar la misma `.vn` al formato del juego
(.HD/.BIN para PS2) requeriría un encoder PNG→TIM2 y emitir Squirrel del engine
— es la extensión "motor real" de la capa 3, no incluida.
