/* Lector del blob .vnp (espejo EXACTO de znt/vniso.py). Little-endian.
 * Parsea in-place: los punteros apuntan dentro del buffer cargado (no copia). */
#ifndef VNP_H
#define VNP_H
#include <stdint.h>

/* opcodes (== OP en vniso.py) */
enum { OP_BG=1, OP_SHOW=2, OP_HIDE=3, OP_SAY=4, OP_ANIM=5,
       OP_BGM=6, OP_SE=7, OP_CHOICE=8, OP_GOTO=9, OP_END=10 };
/* códigos de animación (== ANIM en vniso.py) */
enum { AN_LINEAR=0, AN_ACCEL=1, AN_DECEL=2, AN_MOVE=3,
       AN_WAVE=10, AN_WAVEONCE=11, AN_JUMP=12, AN_JUMPONCE=13, AN_FALL=14, AN_VIBRATE=15 };
#define VNP_NONE16 0xFFFF
#define VNP_NONE32 0xFFFFFFFFu

typedef struct { const char *ptr; uint16_t len; } VnpStr;   /* no NUL-terminado */

typedef struct { uint32_t name; uint32_t color; uint16_t sprite; } VnpChar;

typedef struct { uint16_t w, h; uint8_t fmt; uint32_t len; const uint8_t *rgba; } VnpImage;

/* Un paso ya decodificado a campos (unión por op). */
typedef struct {
    uint8_t op;
    /* bg */
    uint8_t  bg_kind;        /* 0 solid, 1 grad, 2 img */
    uint32_t bg_a, bg_b;     /* colores rgba (solid usa bg_a) */
    uint16_t bg_img;
    /* show / hide / anim */
    uint16_t chr;
    int16_t  x, y, z;
    uint16_t zoom; uint8_t opacity; uint32_t tint;
    /* anim */
    uint8_t  an_kind, an_curve;
    int16_t  an_x; uint16_t an_time; int16_t an_vib; uint16_t an_cycle; int16_t an_dist;
    /* say */
    uint16_t who; uint32_t text;
    /* bgm/se */
    uint8_t  bgm_stop; uint16_t audio;   /* índice en la tabla de audio (0xFFFF none) */
    /* choice */
    uint8_t  n_opts; uint32_t opt_label[16]; uint16_t opt_target[16];
    /* goto */
    uint16_t target;
} VnpStep;

typedef struct {
    const uint8_t *buf; uint32_t size;
    uint16_t version, start;
    uint32_t n_strings; const uint8_t *strings;   /* sección cruda; usar vnp_str() */
    uint32_t n_chars;   const VnpChar *chars;      /* NO: se copian; ver impl */
    uint32_t n_images;
    uint32_t n_scenes;
    /* fuente (opcional) */
    uint8_t  has_font; uint16_t font_w, font_h; uint32_t font_n;
    const uint8_t *font_cps;   /* font_n * u32 (codepoints ascendentes) */
    const uint8_t *font_bmp;   /* font_n * font_h * ceil(font_w/8) bytes 1bpp */
    /* audio */
    uint32_t n_audio; const uint8_t *p_audio;
    /* índices calculados en vnp_open (offsets a cada sección) */
    const uint8_t *p_strings, *p_chars, *p_images, *p_scenes;
} VnpDoc;

/* Abre y valida el blob (no copia). Devuelve 0 si OK. */
int vnp_open(VnpDoc *d, const uint8_t *buf, uint32_t size);

/* Resuelve un índice de string a (ptr,len). idx==VNP_NONE32 -> len 0. */
VnpStr vnp_str(const VnpDoc *d, uint32_t idx);

/* Copia el personaje i. */
void vnp_char(const VnpDoc *d, uint32_t i, VnpChar *out);

/* Devuelve la imagen i (ptr al RGBA dentro del buffer). */
void vnp_image(const VnpDoc *d, uint32_t i, VnpImage *out);

/* Bitmap 1bpp del glifo de un codepoint (font_h * ceil(font_w/8) bytes), o NULL. */
const uint8_t *vnp_glyph(const VnpDoc *d, uint32_t codepoint);

/* Datos de un audio embebido (bytes del archivo original: wav/ogg/...). */
typedef struct { uint32_t name; const uint8_t *data; uint32_t len; } VnpAudio;
void vnp_audio(const VnpDoc *d, uint32_t i, VnpAudio *out);

/* Itera los pasos de una escena: vnp_scene_begin + vnp_step hasta que devuelva 0. */
typedef struct { const uint8_t *p; uint32_t left; } VnpScene;
int  vnp_scene_begin(const VnpDoc *d, uint32_t scene, VnpScene *sc);  /* 0 si OK */
int  vnp_step(VnpScene *sc, VnpStep *out);                            /* 0 al terminar */

#endif
