/* VN player para PS2 (camino C del spike) — PROOF OF LIFE.
 *
 * Estado: el LECTOR del blob (vnp.c) está verificado en host contra vniso.py.
 * Este main.c es un esqueleto gsKit para COMPILAR con ps2dev e ITERAR en PCSX2.
 * La lógica del intérprete (nuestra) es sólida; el glue de gsKit (marcado [GSKIT])
 * puede necesitar ajustes según tu versión de gsKit — verificá esos puntos al build.
 *
 * Cubre: bg (solid/grad/img), sprites (Z, zoom, opacidad), caja de diálogo, avance
 * y choices con el pad. Falta (siguiente iteración): texto con fuente, animación por
 * tiempo, audio (SPU2). Ver ps2/README.md.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <malloc.h>
#include <kernel.h>
#include <sbv_patches.h>
#include <gsKit.h>
#include <dmaKit.h>
#include <libpad.h>
#include <sifrpc.h>
#include <loadfile.h>
#include <audsrv.h>
#include "vnp.h"

#define SCR_W 640
#define SCR_H 448
#define MAX_LAYERS 16

static VnpDoc doc;                 /* el blob abierto (vnp.c parsea in-place) */

/* --- carga del blob: proba host: (PCSX2), mass: (USB) y cdrom0: (ISO) ---
 * Sólo la CABECERA queda en RAM (v5: head_size); imágenes y audio se leen por
 * demanda con blob_read(). El archivo queda abierto. */
static FILE *g_file;
static uint8_t *load_blob(uint32_t *size)
{
    const char *paths[] = { "host:ZNTVN.VNP", "mass:ZNTVN.VNP", "cdrom0:\\ZNTVN.VNP;1", 0 };
    for (int i = 0; paths[i]; i++) {
        FILE *f = fopen(paths[i], "rb");
        if (!f) continue;
        uint8_t hdr[12];
        if (fread(hdr, 1, 12, f) == 12 && !memcmp(hdr, "VNP1", 4)) {
            uint32_t n = hdr[8] | (hdr[9] << 8) | (hdr[10] << 16) | ((uint32_t)hdr[11] << 24);
            uint8_t *b = malloc(n);
            fseek(f, 0, SEEK_SET);
            if (b && fread(b, 1, n, f) == n) { g_file = f; *size = n; return b; }
            free(b);
        }
        fclose(f);
    }
    return 0;
}

/* trae `len` bytes del archivo en `off` (buffer alineado a 128 para el GS). NULL si falla. */
static void *blob_read(uint32_t off, uint32_t len)
{
    void *b = memalign(128, len ? len : 1);
    if (!b) return 0;
    if (fseek(g_file, off, SEEK_SET) || fread(b, 1, len, g_file) != len) { free(b); return 0; }
    return b;
}

/* --- AUDIO (audsrv). PARTE MÁS CRUDA / SIN TESTEAR: verificar al build. -----
 * BGM: se reproduce WAV/PCM en un thread, en loop. SE: TODO (audsrv es un solo
 * stream PCM; un SE simultáneo necesita canal ADPCM/VAG en la SPU2). La carga del
 * módulo audsrv.irx depende de tu entorno (ver README). */
static const uint8_t *g_bgm_pcm; static int g_bgm_len, g_bgm_play, g_bgm_gen;
static uint8_t *g_bgm_buf, *g_bgm_old;   /* buffer del BGM actual y el anterior (se libera al próximo cambio) */
static u32 le32(const uint8_t *p){ return p[0]|(p[1]<<8)|(p[2]<<16)|((u32)p[3]<<24); }

/* parsea un WAV PCM: devuelve ptr/len de los samples y el formato. 0 si no es WAV. */
static int wav_parse(const uint8_t *d, int n, const uint8_t **pcm, int *plen,
                     int *freq, int *bits, int *ch)
{
    if (n < 44 || memcmp(d, "RIFF", 4) || memcmp(d + 8, "WAVE", 4)) return 0;
    int i = 12;
    while (i + 8 <= n) {
        u32 sz = le32(d + i + 4);
        if (!memcmp(d + i, "fmt ", 4)) { *ch = d[i+10]|(d[i+11]<<8); *freq = le32(d+i+12); *bits = d[i+22]|(d[i+23]<<8); }
        else if (!memcmp(d + i, "data", 4)) { *pcm = d + i + 8; *plen = (int)sz; return 1; }
        i += 8 + sz + (sz & 1);
    }
    return 0;
}

static void audio_set_bgm(uint16_t idx)
{
    g_bgm_play = 0; g_bgm_gen++;
    if (idx == VNP_NONE16) return;
    VnpAudio a; vnp_audio(&doc, idx, &a);
    uint8_t *buf = blob_read(a.off, a.len);            /* por demanda: sólo el BGM que suena */
    if (!buf) return;
    const uint8_t *pcm; int plen = 0, freq = 0, bits = 16, ch = 2;
    if (!wav_parse(buf, a.len, &pcm, &plen, &freq, &bits, &ch)) { free(buf); return; }  /* sólo WAV */
    free(g_bgm_old); g_bgm_old = g_bgm_buf; g_bgm_buf = buf;   /* el viejo puede estar sonando un chunk más */
    struct audsrv_fmt_t f; f.freq = freq; f.bits = bits; f.channels = ch;
    audsrv_set_format(&f);                              /*AUDIO*/
    g_bgm_pcm = pcm; g_bgm_len = plen; g_bgm_play = 1;
}

static char g_bgm_stack[16 * 1024] __attribute__((aligned(16)));
static void bgm_thread(void *arg)
{
    (void)arg;
    while (1) {
        if (g_bgm_play && g_bgm_pcm) {                  /* por chunks: un cambio de BGM corta enseguida */
            int gen = g_bgm_gen, pos = 0;
            while (g_bgm_play && gen == g_bgm_gen && pos < g_bgm_len) {
                int n = g_bgm_len - pos; if (n > 4096) n = 4096;
                audsrv_wait_audio(n); audsrv_play_audio((char *)g_bgm_pcm + pos, n);   /*AUDIO*/
                pos += n;
            }                                           /* al terminar: loop */
        } else
            for (int k = 0; k < 20000; k++) nopdelay();
    }
}

extern unsigned char audsrv_irx[]; extern unsigned int size_audsrv_irx;   /* embebido (bin2c) */
static void audio_init(void)
{
    SifLoadModule("rom0:LIBSD", 0, 0);
    if (SifExecModuleBuffer(audsrv_irx, size_audsrv_irx, 0, 0, 0) < 0) return;
    if (audsrv_init() != 0) return;                    /*AUDIO*/
    ee_thread_t t; memset(&t, 0, sizeof(t));
    t.func = bgm_thread; t.stack = g_bgm_stack; t.stack_size = sizeof(g_bgm_stack);
    t.gp_reg = &_gp; t.initial_priority = 0x40;
    int id = CreateThread(&t); if (id >= 0) StartThread(id, 0);
}

/* --- fuente: atlas de glifos construido del blob --- */
static GSTEXTURE g_font;      /*GSKIT*/ static int g_font_cols, g_have_font;
static int g_choice_sel;      /* opción resaltada en un choice */

static void build_font_atlas(GSGLOBAL *gs)
{
    if (!doc.has_font) return;
    int w = doc.font_w, h = doc.font_h, n = doc.font_n;
    int cols = 1024 / w; if (cols > n) cols = n; if (cols < 1) cols = 1;
    int rows = (n + cols - 1) / cols;
    int aw = cols * w, ah = rows * h, stride = (w + 7) / 8;
    u32 *px = memalign(128, (uint32_t)aw * ah * 4);
    memset(px, 0, (uint32_t)aw * ah * 4);
    for (int g = 0; g < n; g++) {
        const uint8_t *bmp = doc.font_bmp + (uint32_t)g * h * stride;
        int cx = (g % cols) * w, cy = (g / cols) * h;
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
                if (bmp[y*stride + (x>>3)] & (0x80 >> (x & 7)))
                    px[(cy + y) * aw + (cx + x)] = 0x80FFFFFF;   /* blanco, alfa 0x80 */
    }
    memset(&g_font, 0, sizeof(g_font));
    g_font.Width = aw; g_font.Height = ah; g_font.PSM = GS_PSM_CT32;
    g_font.Filter = GS_FILTER_NEAREST; g_font.Mem = px;
    gsKit_setup_tbw(&g_font);                                   /*GSKIT*/
    g_font_cols = cols; g_have_font = 1;
}

static int font_cell(uint32_t cp)   /* índice de celda, o -1 */
{
    uint32_t lo = 0, hi = doc.font_n;
    while (lo < hi) {
        uint32_t mid = (lo + hi) / 2;
        uint32_t v = doc.font_cps[mid*4] | (doc.font_cps[mid*4+1]<<8)
                   | (doc.font_cps[mid*4+2]<<16) | ((uint32_t)doc.font_cps[mid*4+3]<<24);
        if (v == cp) return (int)mid;
        if (v < cp) lo = mid + 1; else hi = mid;
    }
    return -1;
}

/* siguiente codepoint UTF-8 en s[*i..len) */
static uint32_t utf8_next(const char *s, int len, int *i)
{
    unsigned char c = s[*i]; (*i)++;
    if (c < 0x80) return c;
    if ((c >> 5) == 6 && *i < len)      { uint32_t r = (c&0x1F)<<6 | (s[*i]&0x3F); (*i)++; return r; }
    if ((c >> 4) == 14 && *i+1 < len)   { uint32_t r=(c&0x0F)<<12 | (s[*i]&0x3F)<<6 | (s[*i+1]&0x3F); *i+=2; return r; }
    if (*i+2 < len)                     { uint32_t r=(c&0x07)<<18 | (s[*i]&0x3F)<<12 | (s[*i+1]&0x3F)<<6 | (s[*i+2]&0x3F); *i+=3; return r; }
    return '?';
}

#define TYPING_CPS 40                /* caracteres por segundo (mismo default que el editor) */
static float g_say_ms;               /* ms desde que empezó el diálogo actual (tipeo) */
static int utf8_count(const char *s, int len) { int i = 0, n = 0; while (i < len) { utf8_next(s, len, &i); n++; } return n; }

/* dibuja texto (UTF-8) desde (x,y) con wrap simple; `maxcp` = cuántos codepoints mostrar (-1 todos).  [GSKIT] */
static void draw_text(GSGLOBAL *gs, float x, float y, const char *s, int len, uint8_t r, uint8_t g_, uint8_t b, int maxcp)
{
    if (!g_have_font) return;
    int fw = doc.font_w, fh = doc.font_h;
    float pen = x, py = y, maxx = SCR_W - 32;
    int i = 0, shown = 0;
    while (i < len && (maxcp < 0 || shown++ < maxcp)) {
        uint32_t cp = utf8_next(s, len, &i);
        if (cp == '\n' || pen > maxx) { pen = x; py += fh + 2; if (cp == '\n') continue; }
        int cell = font_cell(cp);
        if (cell >= 0) {
            int cx = (cell % g_font_cols) * fw, cy = (cell / g_font_cols) * fh;
            gsKit_prim_sprite_texture(gs, &g_font, pen, py, cx, cy, pen+fw, py+fh, cx+fw, cy+fh,
                                      4, GS_SETREG_RGBAQ(r, g_, b, 0x80, 0));
        }
        pen += fw;
    }
}

/* --- capa activa en el stage --- */
typedef struct {
    int used, chr;
    float x, y; int z, zoom, opacity;
    GSTEXTURE tex;      /*GSKIT*/  int has_tex;
    /* animación (mismo modelo que engine.py): un tween por coordenada */
    struct { int active, curve; float from, to, dur, t; } twx, twy;
    int   ac_kind, ac_done;    float ac_vib, ac_cycle, ac_dist, ac_time, ac_now, ac_next, ac_ox, ac_oy;
} Layer;

/* ease() de engine.py: normal t, accel t^2, decel 1-(1-t)^2 */
static float easef(int curve, float k)
{
    if (curve == AN_ACCEL) return k * k;
    if (curve == AN_DECEL) return 1.0f - (1.0f - k) * (1.0f - k);
    return k;
}
static uint32_t g_rng = 0x2545F491;
static int rnd_range(int n) { g_rng = g_rng * 1103515245u + 12345u; return n > 0 ? (int)((g_rng >> 16) % (uint32_t)n) : 0; }

/* Action.tick() de engine.py. Para vibrate, ac_cycle se usa como waitTime. */
static void action_tick(Layer *L, float dt)
{
    if (!L->ac_kind || L->ac_done) { L->ac_ox = L->ac_oy = 0; return; }
    L->ac_now += dt;
    float w = 2.0f * M_PI * L->ac_now / L->ac_cycle;
    switch (L->ac_kind) {
    case AN_WAVE:     L->ac_ox = L->ac_vib * sinf(w); L->ac_oy = 0; break;
    case AN_WAVEONCE: if (L->ac_now >= L->ac_cycle / 2) { L->ac_done = 1; L->ac_ox = L->ac_oy = 0; }
                      else { L->ac_ox = L->ac_vib * sinf(M_PI + w); L->ac_oy = 0; } break;
    case AN_JUMP:     L->ac_ox = 0; L->ac_oy = L->ac_vib * sinf(w) + L->ac_vib; break;
    case AN_JUMPONCE: if (L->ac_now >= L->ac_cycle / 2) { L->ac_done = 1; L->ac_ox = L->ac_oy = 0; }
                      else { L->ac_ox = 0; L->ac_oy = L->ac_vib * sinf(M_PI + w) + L->ac_vib; } break;
    case AN_FALL:     if (L->ac_now >= L->ac_time) { L->ac_done = 1; L->ac_ox = L->ac_oy = 0; }
                      else { L->ac_ox = 0; L->ac_oy = -L->ac_dist + L->ac_dist * L->ac_now / L->ac_time; } break;
    case AN_VIBRATE:  if (L->ac_now >= L->ac_next) {
                          L->ac_ox = rnd_range((int)L->ac_vib) - L->ac_vib / 2;
                          L->ac_oy = rnd_range((int)L->ac_vib);
                          L->ac_next += (L->ac_cycle > 0 ? L->ac_cycle : 40);
                      } break;
    }
}

typedef struct { int active, curve; float from, to, dur, t; } Tween;
static float tween_tick(Tween *tw, float dt, float cur)
{
    if (!tw->active) return cur;
    tw->t += dt; float k = tw->t / tw->dur;
    if (k >= 1.0f) { k = 1.0f; tw->active = 0; }
    return tw->from + (tw->to - tw->from) * easef(tw->curve, k);
}
static void tween_start(Tween *tw, float from, float to, float dur, int curve)
{
    tw->active = 1; tw->from = from; tw->to = to; tw->dur = dur > 0 ? dur : 1; tw->t = 0; tw->curve = curve;
}
static void layer_tick(Layer *L, float dt)
{
    L->x = tween_tick((Tween *)&L->twx, dt, L->x);
    L->y = tween_tick((Tween *)&L->twy, dt, L->y);
    action_tick(L, dt);
}

static Layer layers[MAX_LAYERS];
static uint32_t cur_scene;
/* fondo actual y anterior (crossfade): kind -1 = nada, 0 solid, 1 grad, 2 imagen */
typedef struct { int kind; uint32_t a, b; GSTEXTURE tex; int has_tex; } Bg;
static Bg g_bg = { -1 }, g_bgprev = { -1 };
static Tween g_fade;                       /* opacidad del fondo nuevo sobre el anterior */
static float g_bg_alpha = 1.0f;
static uint32_t g_frames;

/* sube una imagen RGBA del blob a una GSTEXTURE (PSMCT32).  [GSKIT] */
static void upload_image(GSGLOBAL *gs, uint16_t img_idx, GSTEXTURE *t)
{
    VnpImage im; vnp_image(&doc, img_idx, &im);
    memset(t, 0, sizeof(*t));
    t->Width = im.w; t->Height = im.h;
    t->PSM = GS_PSM_CT32;
    t->Filter = GS_FILTER_LINEAR;
    /* El GS quiere RGBA con alfa 0..0x80. Nuestro alfa es 0..255 -> escalar /2. */
    uint32_t n = (uint32_t)im.w * im.h;
    u32 *px = blob_read(im.off, n * 4);       /* por demanda; se convierte in-place */
    if (!px) return;
    for (uint32_t i = 0; i < n; i++) {
        uint8_t *s = (uint8_t *)px + i * 4;
        uint8_t a = s[3] >> 1;                 /* 0..127 (0x80 = opaco en PS2) */
        px[i] = (a << 24) | (s[2] << 16) | (s[1] << 8) | s[0];
    }
    t->Mem = px;
    gsKit_setup_tbw(t);                        /*GSKIT*/
    printf("ZNTVN: img %u %ux%u off=%u len=%u mem=%p\n", (unsigned)img_idx, (unsigned)im.w, (unsigned)im.h, (unsigned)im.off, (unsigned)im.len, px);
    /* la subida real a VRAM la hace gsKit_TexManager_bind por frame (streaming). */
}

/* aplica los pasos no bloqueantes de la escena hasta un say/choice/goto/end.
 * El cursor g_sc es global -> "avanzar" continúa desde donde quedó (reanudable). */
typedef struct { int kind; /*1 say,2 choice,3 end*/ VnpStep step; } Block;

static VnpScene g_sc;
static Block advance(GSGLOBAL *gs);   /* continúa el cursor actual */

static Block enter_scene(GSGLOBAL *gs, uint32_t scene)
{
    for (int i = 0; i < MAX_LAYERS; i++) if (layers[i].has_tex) free(layers[i].tex.Mem);
    memset(layers, 0, sizeof(layers));                  /* el fondo persiste entre escenas */
    cur_scene = scene;
    Block blk; memset(&blk, 0, sizeof(blk));
    if (vnp_scene_begin(&doc, scene, &g_sc)) { blk.kind = 3; return blk; }
    return advance(gs);
}

static Block advance(GSGLOBAL *gs)
{
    VnpStep s; Block blk; memset(&blk, 0, sizeof(blk));
    while (vnp_step(&g_sc, &s)) {
        switch (s.op) {
        case OP_BG:
            /* solid/grad: color de fondo; img: textura full-screen (capa 0). */
            if (g_bgprev.has_tex) free(g_bgprev.tex.Mem);
            if (s.bg_fade && g_bg.kind >= 0) {          /* el fondo viejo queda abajo mientras dura el fade */
                g_bgprev = g_bg; tween_start(&g_fade, 0.0f, 1.0f, s.bg_fade, AN_LINEAR); g_bg_alpha = 0.0f;
            } else {
                if (g_bg.has_tex) free(g_bg.tex.Mem);
                g_bgprev.kind = -1; g_bgprev.has_tex = 0; g_fade.active = 0; g_bg_alpha = 1.0f;
            }
            memset(&g_bg, 0, sizeof(g_bg));
            g_bg.kind = s.bg_kind; g_bg.a = s.bg_a; g_bg.b = s.bg_b;
            if (s.bg_kind == 2) { upload_image(gs, s.bg_img, &g_bg.tex); g_bg.has_tex = g_bg.tex.Mem != 0; }
            break;
        case OP_SHOW: {
            int slot = -1;
            for (int i = 1; i < MAX_LAYERS; i++) if (!layers[i].used) { slot = i; break; }
            if (slot < 0) break;
            Layer *L = &layers[slot];
            if (L->has_tex) free(L->tex.Mem);          /* slot reciclado de un hide */
            memset(L, 0, sizeof(*L));
            L->used = 1; L->chr = s.chr;
            L->x = s.x; L->y = s.y; L->z = s.z; L->zoom = s.zoom; L->opacity = s.opacity;
            VnpChar c; vnp_char(&doc, s.chr, &c);
            uint16_t img = (s.img != VNP_NONE16) ? s.img : c.sprite;   /* expresión o base */
            if (img != VNP_NONE16) { upload_image(gs, img, &L->tex); L->has_tex = L->tex.Mem != 0; }
            break; }
        case OP_HIDE:
            for (int i = 1; i < MAX_LAYERS; i++) if (layers[i].used && layers[i].chr == s.chr) layers[i].used = 0;
            break;
        case OP_SAY:   blk.kind = 1; blk.step = s; return blk;
        case OP_CHOICE:blk.kind = 2; blk.step = s; return blk;
        case OP_ANIM: {
            Layer *L = 0;
            for (int i = 1; i < MAX_LAYERS; i++) if (layers[i].used && layers[i].chr == s.chr) L = &layers[i];
            if (!L) break;
            if (s.an_kind <= AN_MOVE) {                 /* movimiento con curva, por coordenada dada */
                int curve = (s.an_kind == AN_MOVE) ? s.an_curve : s.an_kind;
                if (s.an_x != VNP_NOCOORD) tween_start((Tween *)&L->twx, L->x, s.an_x, s.an_time, curve);
                if (s.an_y != VNP_NOCOORD) tween_start((Tween *)&L->twy, L->y, s.an_y, s.an_time, curve);
            } else {                                    /* action offset */
                L->ac_kind = s.an_kind; L->ac_done = 0; L->ac_now = 0; L->ac_next = 0;
                L->ac_vib = s.an_vib; L->ac_cycle = s.an_cycle ? s.an_cycle : 1;
                L->ac_dist = s.an_dist; L->ac_time = s.an_time ? s.an_time : 1;
            }
            break;
        }
        case OP_BGM:   audio_set_bgm(s.bgm_stop ? VNP_NONE16 : s.audio); break;
        case OP_SE:    /* TODO: SE necesita un canal ADPCM/VAG en la SPU2 */ break;
        case OP_GOTO:  return enter_scene(gs, s.target);
        case OP_END:   blk.kind = 3; return blk;
        default: break;
        }
    }
    blk.kind = 3; return blk;
}

/* fondo: color plano, degradé vertical o imagen, con alfa (colores del blob: 0xRRGGBBAA) */
#define BGCOL(c, a) GS_SETREG_RGBAQ(((c) >> 24) & 0xff, ((c) >> 16) & 0xff, ((c) >> 8) & 0xff, (a), 0)
static void draw_bg(GSGLOBAL *gs, Bg *bg, float alpha)
{
    uint8_t a = (uint8_t)(alpha * 0x80);
    if (bg->kind == 0) {
        gsKit_prim_sprite(gs, 0, 0, SCR_W, SCR_H, 1, BGCOL(bg->a, a));
    } else if (bg->kind == 1) {          /* (las prims de gsKit son macros con ';' propio: llaves) */
        gsKit_prim_quad_gouraud(gs, 0, 0, SCR_W, 0, 0, SCR_H, SCR_W, SCR_H, 1,
                                BGCOL(bg->a, a), BGCOL(bg->a, a), BGCOL(bg->b, a), BGCOL(bg->b, a));
    } else if (bg->has_tex) {
        gsKit_TexManager_bind(gs, &bg->tex);
        gsKit_prim_sprite_texture(gs, &bg->tex, 0, 0, 0, 0, SCR_W, SCR_H, bg->tex.Width, bg->tex.Height,
                                  1, GS_SETREG_RGBAQ(0x80, 0x80, 0x80, a, 0));
    }
}

/* dibuja el frame: capas por Z (mayor Z al frente) + caja de diálogo.  [GSKIT] */
static void draw_frame(GSGLOBAL *gs, const Block *blk)
{
    gsKit_clear(gs, GS_SETREG_RGBAQ(0, 0, 0, 0x80, 0));
    if (g_bgprev.kind >= 0) draw_bg(gs, &g_bgprev, 1.0f);   /* crossfade: el viejo abajo, el nuevo con alfa */
    if (g_bg.kind >= 0) draw_bg(gs, &g_bg, g_bg_alpha);
    /* orden: menor z primero (fondo, z=-1000) y mayor z al frente (misma convención que el editor) */
    for (int pass = -1000; pass <= 1000; pass++) {
        for (int i = 0; i < MAX_LAYERS; i++) {
            Layer *L = &layers[i];
            if (!L->used || !L->has_tex || L->z != pass) continue;
            gsKit_TexManager_bind(gs, &L->tex);           /*GSKIT: sube a VRAM este frame (si entra)*/
            float w = L->tex.Width * L->zoom / 100.0f;
            float h = L->tex.Height * L->zoom / 100.0f;
            float cx = SCR_W / 2.0f + L->x + L->ac_ox;     /* centrado en x + offset de acción */
            float x0 = cx - w / 2.0f, y0 = SCR_H - h + L->y + L->ac_oy;
            uint8_t a = (uint8_t)(L->opacity * 0x80 / 100);
            gsKit_prim_sprite_texture(gs, &L->tex, x0, y0, 0, 0,
                                      x0 + w, y0 + h, L->tex.Width, L->tex.Height,
                                      2, GS_SETREG_RGBAQ(0x80, 0x80, 0x80, a, 0));
        }
    }
    /* caja de diálogo (rect semitransparente abajo) */
    if (blk->kind == 1 || blk->kind == 2)
        gsKit_prim_sprite(gs, 24, SCR_H - 108, SCR_W - 24, SCR_H - 12, 3,
                          GS_SETREG_RGBAQ(0x0b, 0x13, 0x30, 0x60, 0));
    if (g_have_font) gsKit_TexManager_bind(gs, &g_font);          /*GSKIT*/
    if (blk->kind == 1) {                                          /* diálogo */
        if (blk->step.who != VNP_NONE16) {
            VnpChar c; vnp_char(&doc, blk->step.who, &c);
            VnpStr nm = vnp_str(&doc, c.name);
            draw_text(gs, 36, SCR_H - 102, nm.ptr, nm.len, 0xe8, 0xb0, 0x4b, -1);
        }
        VnpStr t = vnp_str(&doc, blk->step.text);
        draw_text(gs, 36, SCR_H - 82, t.ptr, t.len, 0xff, 0xff, 0xff, (int)(g_say_ms * TYPING_CPS / 1000.0f));
    } else if (blk->kind == 2) {                                   /* opciones */
        for (int i = 0; i < blk->step.n_opts; i++) {
            VnpStr l = vnp_str(&doc, blk->step.opt_label[i]);
            int sel = (i == g_choice_sel);
            draw_text(gs, sel ? 52 : 40, SCR_H - 100 + i * 20, l.ptr, l.len,
                      sel ? 0xff : 0xa0, sel ? 0xd0 : 0xa0, sel ? 0x40 : 0xa0, -1);
        }
    }
}

/* --- pad --- */
static char pad_buf[256] __attribute__((aligned(64)));
static int pad_pressed(u32 *prev)
{
    struct padButtonStatus b;
    if (padGetState(0, 0) != PAD_STATE_STABLE || !padRead(0, 0, &b)) return 0;   /* sin pad listo: nada apretado */
    u32 now = 0xffff ^ b.btns; u32 hit = now & ~(*prev); *prev = now; return hit;
}

int main(void)
{
    SifInitRpc(0);
    sbv_patch_enable_lmb(); sbv_patch_disable_prefix_check();   /* para SifExecModuleBuffer */
    uint32_t size = 0; uint8_t *blob = load_blob(&size);
    if (!blob || vnp_open(&doc, blob, size)) { printf("VNP no encontrado/invalido\n"); SleepThread(); }
    printf("ZNTVN: blob OK v%u, cabecera %u bytes en RAM, %u escenas, %u imagenes, fuente %ux%u x%u\n", (unsigned)doc.version, (unsigned)size, (unsigned)doc.n_scenes, (unsigned)doc.n_images, (unsigned)doc.font_w, (unsigned)doc.font_h, (unsigned)doc.font_n);

    GSGLOBAL *gs = gsKit_init_global();                   /*GSKIT*/
    dmaKit_init(D_CTRL_RELE_OFF, D_CTRL_MFD_OFF, D_CTRL_STS_UNSPEC,
                D_CTRL_STD_OFF, D_CTRL_RCYC_8, 1 << DMA_CHANNEL_GIF);
    dmaKit_chan_init(DMA_CHANNEL_GIF);
    gs->Mode = GS_MODE_NTSC; gs->Width = SCR_W; gs->Height = SCR_H;
    gs->PSM = GS_PSM_CT24; gs->PSMZ = GS_PSMZ_16S;
    /* VRAM (4 MB): un solo framebuffer y sin Z (el orden es painter's por z) deja ~3 MB
     * para texturas RGBA32: un fondo 640x448 (1.1 MB) + varios sprites. Con doble buffer
     * + Z sólo quedaba 1.3 MB y el segundo sprite no entraba (bind fallaba en silencio). */
    gs->DoubleBuffering = GS_SETTING_OFF; gs->ZBuffering = GS_SETTING_OFF;
    gs->PrimAlphaEnable = GS_SETTING_ON;                  /* PNG con alfa + opacidad de capa */
    gsKit_init_screen(gs);
    gsKit_set_primalpha(gs, GS_SETREG_ALPHA(0, 1, 0, 1, 0), 0);   /* out = src*a + dst*(1-a) */ gsKit_mode_switch(gs, GS_ONESHOT);
    gsKit_TexManager_init(gs);
    build_font_atlas(gs);
    audio_init();

    /* pad */
    SifLoadModule("rom0:SIO2MAN", 0, 0); SifLoadModule("rom0:PADMAN", 0, 0);
    padInit(0); padPortOpen(0, 0, pad_buf);
    u32 prev = 0;

    Block blk = enter_scene(gs, doc.start);
    g_choice_sel = 0; g_say_ms = 0;

    while (blk.kind != 3) {
        u32 hit = pad_pressed(&prev);
        if (blk.kind == 1 && (hit & PAD_CROSS)) {          /* click: completa el tipeo; el siguiente avanza */
            VnpStr t = vnp_str(&doc, blk.step.text);
            if (g_say_ms * TYPING_CPS / 1000.0f < utf8_count(t.ptr, t.len)) g_say_ms = 1e9f;
            else { blk = advance(gs); g_say_ms = 0; }
        } else if (blk.kind == 2) {
            if (hit & PAD_UP)   g_choice_sel = (g_choice_sel + blk.step.n_opts - 1) % blk.step.n_opts;
            if (hit & PAD_DOWN) g_choice_sel = (g_choice_sel + 1) % blk.step.n_opts;
            if (hit & PAD_CROSS) { blk = enter_scene(gs, blk.step.opt_target[g_choice_sel]); g_choice_sel = 0; g_say_ms = 0; }
        }
        for (int i = 0; i < MAX_LAYERS; i++) if (layers[i].used) layer_tick(&layers[i], 16.0f);  /* ~60fps */
        g_say_ms += 16.0f;
        g_bg_alpha = tween_tick(&g_fade, 16.0f, g_bg_alpha);
        if (!g_fade.active && g_bgprev.kind >= 0) {          /* terminó el fade: el viejo se va */
            if (g_bgprev.has_tex) free(g_bgprev.tex.Mem);
            g_bgprev.kind = -1; g_bgprev.has_tex = 0;
        }
        gsKit_TexManager_nextFrame(gs);
        draw_frame(gs, &blk);
        gsKit_queue_exec(gs); gsKit_sync_flip(gs);
        if (++g_frames == 1) printf("ZNTVN: frame OK (escena %u, bloque %d)\n", (unsigned)cur_scene, blk.kind);
    }
    /* fin */
    while (1) { gsKit_clear(gs, GS_SETREG_RGBAQ(0,0,0,0x80,0)); gsKit_sync_flip(gs); }
    return 0;
}
