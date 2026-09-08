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
  bg grad:#101830,#2a4a80         # fondo: degradé vertical (arriba,abajo)
  bg #223                         #   o color sólido
  bg cuarto.png                   #   o imagen (se embebe en el HTML / va al blob PS2)
  bg noche.png fade=600           #   fade=ms: crossfade desde el fondo anterior
  show louise left                # mostrar sprite: left | center | right (x=-180 / 0 / 180)
  show louise feliz right         # con expresión (ver 'sprite'); sin posición mantiene la que tenía
  show louise x=40 y=0 z=5 zoom=120 opacity=80 tint=#ff8080   # capa: x/y en px desde el centro/piso,
                                  #   z mayor = al frente, zoom y opacity en %, tint color
  hide louise
  animate louise move x=200 y=-40 curve=accel time=400   # tween a esa x/y (curve: linear|accel|decel)
  animate louise wave vib=16 cycle=340                    # acciones: wave | waveonce | jump | jumponce
  animate louise fall dist=120 time=600                   #   | fall (dist, time) | vibrate (vib, wait)
  louise: ¿Otra vez despierto?    # diálogo: <personaje>: texto
  * Un silencio llenó la sala.    # narración (equivale a  narrator: ...)
  bgm tema.wav                    # música en loop (WAV PCM para PS2; el HTML acepta lo que el browser toque)
  bgm stop
  se golpe.wav                    # efecto (WAV PCM; en PS2 se convierte a ADPCM al compilar)
  group intro                     # group … endgroup: en Play, todos esos pasos corren con un click
    show saito right
    saito: ¡Hola!
  endgroup
  choice                          # elección ramificada
    - Insistir -> acerca          #   - etiqueta -> escena_destino
    - Cambiar de tema -> tema
  goto fin                        # saltar a otra escena
  end                             # fin del juego
```

Cabecera (antes de la primera `scene`):

```
title: Mi novela
character louise "Louise" color=#ff9ec2   # id, nombre visible y color del nombre
sprite louise louise.png                  # sprite base del personaje
sprite louise feliz louise_feliz.png      # una expresión: `show louise feliz`
```

Reglas: cada `- opción` se engancha al `choice` inmediatamente anterior; `goto`
y `end` cortan el flujo de la escena; el juego arranca en la **primera** escena
declarada. Las líneas que empiezan con `#` son comentarios.

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

*Alcance:* la misma `.vn` sale como player HTML (`znt vn build`) o como blob para el
player nativo de PS2 (`znt iso build`, ver [`build-ps2.md`](build-ps2.md)). Empaquetarla
al formato del juego original (.HD/.BIN, Squirrel del engine) no está incluido.
