/* Lector del blob .vnp. Ver el layout en vnp.h y la fuente en znt/vniso.py. */
#include "vnp.h"
#include <string.h>

static uint16_t rd16(const uint8_t *p) { return p[0] | (p[1] << 8); }
static uint32_t rd32(const uint8_t *p) { return p[0] | (p[1]<<8) | (p[2]<<16) | ((uint32_t)p[3]<<24); }

/* avanza p una escena entera (u32 nsteps + pasos), devolviendo el puntero siguiente */
static const uint8_t *skip_scene(const uint8_t *p);
static const uint8_t *skip_step(const uint8_t *p);

int vnp_open(VnpDoc *d, const uint8_t *buf, uint32_t size)
{
    if (size < 8 || memcmp(buf, "VNP1", 4) != 0) return -1;
    memset(d, 0, sizeof(*d));
    d->buf = buf; d->size = size;
    const uint8_t *p = buf + 4;
    d->version = rd16(p); p += 2;
    d->start   = rd16(p); p += 2;
    d->head_size = rd32(p); p += 4;
    if (d->version < 5 || size < d->head_size) return -1;
    /* strings */
    d->n_strings = rd32(p); p += 4; d->p_strings = p;
    for (uint32_t i = 0; i < d->n_strings; i++) { uint16_t n = rd16(p); p += 2 + n; }
    /* characters (10 bytes c/u) */
    d->n_chars = rd32(p); p += 4; d->p_chars = p;
    p += (uint32_t)d->n_chars * 10;
    /* images */
    d->n_images = rd32(p); p += 4; d->p_images = p;
    p += (uint32_t)d->n_images * 13;                       /* u16 w, u16 h, u8 fmt, u32 len, u32 off */
    /* font (opcional) */
    d->has_font = *p++;
    if (d->has_font) {
        d->font_w = rd16(p); p += 2; d->font_h = rd16(p); p += 2;
        d->font_n = rd32(p); p += 4;
        d->font_cps = p; p += d->font_n * 4;
        d->font_bmp = p;
        uint32_t stride = (d->font_w + 7) / 8;
        p += d->font_n * d->font_h * stride;
    }
    /* audio */
    d->n_audio = rd32(p); p += 4; d->p_audio = p;
    p += (uint32_t)d->n_audio * 12;                        /* u32 name, u32 len, u32 off */
    /* scenes */
    d->n_scenes = rd32(p); p += 4; d->p_scenes = p;
    return 0;
}

void vnp_audio(const VnpDoc *d, uint32_t i, VnpAudio *out)
{
    const uint8_t *p = d->p_audio + i * 12;
    out->name = rd32(p); out->len = rd32(p + 4); out->off = rd32(p + 8);
    out->data = (out->off + out->len <= d->size) ? d->buf + out->off : 0;
}

const uint8_t *vnp_glyph(const VnpDoc *d, uint32_t cp)
{
    if (!d->has_font) return 0;
    uint32_t lo = 0, hi = d->font_n;             /* codepoints ascendentes -> binaria */
    while (lo < hi) {
        uint32_t mid = (lo + hi) / 2, v = rd32(d->font_cps + mid * 4);
        if (v == cp) {
            uint32_t stride = (d->font_w + 7) / 8;
            return d->font_bmp + mid * d->font_h * stride;
        }
        if (v < cp) lo = mid + 1; else hi = mid;
    }
    return 0;
}

VnpStr vnp_str(const VnpDoc *d, uint32_t idx)
{
    VnpStr s = { 0, 0 };
    if (idx == VNP_NONE32 || idx >= d->n_strings) return s;
    const uint8_t *p = d->p_strings;
    for (uint32_t i = 0; i < idx; i++) { uint16_t n = rd16(p); p += 2 + n; }
    s.len = rd16(p); s.ptr = (const char *)(p + 2);
    return s;
}

void vnp_char(const VnpDoc *d, uint32_t i, VnpChar *out)
{
    const uint8_t *p = d->p_chars + i * 10;
    out->name = rd32(p); out->color = rd32(p + 4); out->sprite = rd16(p + 8);
}

void vnp_image(const VnpDoc *d, uint32_t i, VnpImage *out)
{
    const uint8_t *p = d->p_images + i * 13;
    out->w = rd16(p); out->h = rd16(p + 2); out->fmt = p[4];
    out->len = rd32(p + 5); out->off = rd32(p + 9);
    out->rgba = (out->off + out->len <= d->size) ? d->buf + out->off : 0;
}

int vnp_scene_begin(const VnpDoc *d, uint32_t scene, VnpScene *sc)
{
    if (scene >= d->n_scenes) return -1;
    const uint8_t *p = d->p_scenes;
    for (uint32_t k = 0; k < scene; k++) p = skip_scene(p);
    sc->left = rd32(p); sc->p = p + 4;
    return 0;
}

int vnp_step(VnpScene *sc, VnpStep *o)
{
    if (sc->left == 0) return 0;
    sc->left--;
    const uint8_t *p = sc->p;
    memset(o, 0, sizeof(*o));
    o->op = *p++;
    switch (o->op) {
    case OP_BG:
        o->bg_kind = *p++;
        if (o->bg_kind == 0) { o->bg_a = rd32(p); p += 4; }
        else if (o->bg_kind == 1) { o->bg_a = rd32(p); o->bg_b = rd32(p+4); p += 8; }
        else { o->bg_img = rd16(p); p += 2; }
        o->bg_fade = rd16(p); p += 2;                /* v5 */
        break;
    case OP_SHOW:
        o->chr = rd16(p); p += 2;
        o->img = rd16(p); p += 2;                   /* v4 */
        o->x = (int16_t)rd16(p); p += 2; o->y = (int16_t)rd16(p); p += 2;
        o->z = (int16_t)rd16(p); p += 2; o->zoom = rd16(p); p += 2;
        o->opacity = *p++; o->tint = rd32(p); p += 4;
        break;
    case OP_HIDE:
        o->chr = rd16(p); p += 2; break;
    case OP_SAY:
        o->who = rd16(p); p += 2; o->text = rd32(p); p += 4; break;
    case OP_ANIM:
        o->an_kind = *p++; o->an_curve = *p++;
        o->an_x = (int16_t)rd16(p); p += 2; o->an_y = (int16_t)rd16(p); p += 2;   /* v5: y */
        o->an_time = rd16(p); p += 2;
        o->an_vib = (int16_t)rd16(p); p += 2; o->an_cycle = rd16(p); p += 2;
        o->an_dist = (int16_t)rd16(p); p += 2; break;
    case OP_BGM:
        o->bgm_stop = *p++; o->audio = rd16(p); p += 2; break;
    case OP_SE:
        o->audio = rd16(p); p += 2; break;
    case OP_CHOICE:
        o->n_opts = *p++;
        for (uint8_t i = 0; i < o->n_opts && i < 16; i++) {
            o->opt_label[i] = rd32(p); p += 4; o->opt_target[i] = rd16(p); p += 2;
        }
        break;
    case OP_GOTO:
        o->target = rd16(p); p += 2; break;
    case OP_END:
    default:
        break;
    }
    sc->p = p;
    return 1;
}

static const uint8_t *skip_step(const uint8_t *p)
{
    VnpScene sc = { p, 1 }; VnpStep s; vnp_step(&sc, &s); return sc.p;
}
static const uint8_t *skip_scene(const uint8_t *p)
{
    uint32_t n = rd32(p); p += 4;
    for (uint32_t i = 0; i < n; i++) p = skip_step(p);
    return p;
}
