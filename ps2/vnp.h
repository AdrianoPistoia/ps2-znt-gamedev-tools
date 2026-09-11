/* Reader for the .vnp blob (EXACT mirror of znt/vniso.py). Little-endian.
 * Parses in place: the pointers point inside the loaded buffer (no copy).
 * v5: loading the header (`head_size` bytes) is enough; images and audio carry
 * absolute `off`/`len` in the file and are read on demand. If the buffer does not
 * cover the data, `rgba`/`data` are left NULL. */
#ifndef VNP_H
#define VNP_H
#include <stdint.h>

/* opcodes (== OP in vniso.py) */
enum { OP_BG=1, OP_SHOW=2, OP_HIDE=3, OP_SAY=4, OP_ANIM=5,
       OP_BGM=6, OP_SE=7, OP_CHOICE=8, OP_GOTO=9, OP_END=10 };
/* animation codes (== ANIM in vniso.py) */
enum { AN_LINEAR=0, AN_ACCEL=1, AN_DECEL=2, AN_MOVE=3,
       AN_WAVE=10, AN_WAVEONCE=11, AN_JUMP=12, AN_JUMPONCE=13, AN_FALL=14, AN_VIBRATE=15 };
#define VNP_NONE16 0xFFFF
#define VNP_NONE32 0xFFFFFFFFu
#define VNP_NOCOORD 0x7FFF        /* anim: coordinate not given (left untouched) */

typedef struct { const char *ptr; uint16_t len; } VnpStr;   /* not NUL-terminated */

typedef struct { uint32_t name; uint32_t color; uint16_t sprite; } VnpChar;

typedef struct { uint16_t w, h; uint8_t fmt; uint32_t len, off; const uint8_t *rgba; } VnpImage;

/* A step already decoded into fields (union by op). */
typedef struct {
    uint8_t op;
    /* bg */
    uint8_t  bg_kind;        /* 0 solid, 1 grad, 2 img */
    uint32_t bg_a, bg_b;     /* rgba colours (solid uses bg_a) */
    uint16_t bg_img;
    uint16_t bg_fade;        /* v5: crossfade in ms (0 = cut) */
    /* show / hide / anim */
    uint16_t chr;
    uint16_t img;            /* show: image of the expression (VNP_NONE16 = character's sprite) */
    int16_t  x, y, z;
    uint16_t zoom; uint8_t opacity; uint32_t tint;
    /* anim */
    uint8_t  an_kind, an_curve;
    int16_t  an_x, an_y;     /* VNP_NOCOORD = not given */
    uint16_t an_time; int16_t an_vib; uint16_t an_cycle; int16_t an_dist;
    /* say */
    uint16_t who; uint32_t text;
    /* bgm/se */
    uint8_t  bgm_stop; uint16_t audio;   /* index into the audio table (0xFFFF none) */
    /* choice */
    uint8_t  n_opts; uint32_t opt_label[16]; uint16_t opt_target[16];
    /* goto */
    uint16_t target;
} VnpStep;

typedef struct {
    const uint8_t *buf; uint32_t size;
    uint16_t version, start;
    uint32_t head_size;        /* v5: header bytes (what has to be in RAM) */
    uint32_t n_strings; const uint8_t *strings;   /* raw section; use vnp_str() */
    uint32_t n_chars;   const VnpChar *chars;      /* NO: they are copied; see impl */
    uint32_t n_images;
    uint32_t n_scenes;
    /* font (optional) */
    uint8_t  has_font; uint16_t font_w, font_h; uint32_t font_n;
    const uint8_t *font_cps;   /* font_n * u32 (ascending codepoints) */
    const uint8_t *font_bmp;   /* font_n * font_h * ceil(font_w/8) bytes 1bpp */
    /* audio */
    uint32_t n_audio; const uint8_t *p_audio;
    /* indices computed in vnp_open (offsets to each section) */
    const uint8_t *p_strings, *p_chars, *p_images, *p_scenes;
} VnpDoc;

/* Opens and validates the blob (no copy). Returns 0 if OK. */
int vnp_open(VnpDoc *d, const uint8_t *buf, uint32_t size);

/* Resolves a string index to (ptr,len). idx==VNP_NONE32 -> len 0. */
VnpStr vnp_str(const VnpDoc *d, uint32_t idx);

/* Copies character i. */
void vnp_char(const VnpDoc *d, uint32_t i, VnpChar *out);

/* Returns image i (rgba points into the buffer if the data is loaded; otherwise NULL and off/len). */
void vnp_image(const VnpDoc *d, uint32_t i, VnpImage *out);

/* 1bpp bitmap of a codepoint's glyph (font_h * ceil(font_w/8) bytes), or NULL. */
const uint8_t *vnp_glyph(const VnpDoc *d, uint32_t codepoint);

/* Data of an embedded audio (bytes of the original file: wav/ogg/...). */
typedef struct { uint32_t name; const uint8_t *data; uint32_t len, off; } VnpAudio;
void vnp_audio(const VnpDoc *d, uint32_t i, VnpAudio *out);

/* Iterates the steps of a scene: vnp_scene_begin + vnp_step until it returns 0. */
typedef struct { const uint8_t *p; uint32_t left; } VnpScene;
int  vnp_scene_begin(const VnpDoc *d, uint32_t scene, VnpScene *sc);  /* 0 if OK */
int  vnp_step(VnpScene *sc, VnpStep *out);                            /* 0 when done */

#endif
