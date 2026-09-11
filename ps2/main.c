/* VN player for PS2 (path C of the spike) — PROOF OF LIFE.
 *
 * Status: the blob READER (vnp.c) is verified on the host against vniso.py.
 * This main.c is a gsKit skeleton to BUILD with ps2dev and ITERATE in PCSX2.
 * The interpreter logic (ours) is solid; the gsKit glue (marked [GSKIT]) may
 * need adjusting for your gsKit version — check those spots at build time.
 *
 * Covers: bg (solid/grad/img), sprites (Z, zoom, opacity), dialogue box, advancing
 * and choices with the pad. Missing (next iteration): text with font, time-based
 * animation, audio (SPU2). See ps2/README.md.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <malloc.h>
#include <kernel.h>
#include <delaythread.h>
#include <timer.h>
#include <ps2sdkapi.h>
#include <fcntl.h>
#include <unistd.h>
#include <sbv_patches.h>
#include <gsKit.h>
#include <dmaKit.h>
#include <libpad.h>
#include <sifrpc.h>
#include <loadfile.h>
#include <audsrv.h>
#include "vnp.h"
#include "text.h"
#include "save.h"
#include <libmc.h>

#define SCR_W 640
#define SCR_H 448
#define MAX_LAYERS 16

static VnpDoc doc;                 /* the open blob (vnp.c parses in place) */

/* --- blob loading: tries host: (PCSX2), mass: (USB) and cdrom0: (ISO) ---
 * Only the HEADER stays in RAM (v5: head_size); images and audio are read on
 * demand with blob_read(). The descriptor stays open.
 *
 * open/read instead of fopen/fread: stdio splits the request into chunks of its
 * internal buffer and against cdrom0 that gives 166 KB/s (a 1.1 MB background took
 * 6.7 s). With direct, sector-aligned reads the driver delivers whole sectors at once. */
#define SECTOR 2048
#define SECTOR_UP(n) (((n) + SECTOR - 1) & ~(uint32_t)(SECTOR - 1))
static int g_fd = -1;
static uint8_t *load_blob(uint32_t *size)
{
    const char *paths[] = { "host:ZNTVN.VNP", "mass:ZNTVN.VNP", "cdrom0:\\ZNTVN.VNP;1", 0 };
    for (int i = 0; paths[i]; i++) {
        int fd = open(paths[i], O_RDONLY);
        if (fd < 0) continue;
        uint8_t hdr[16] __attribute__((aligned(64)));
        if (read(fd, hdr, 16) == 16 && !memcmp(hdr, "VNP1", 4)) {
            uint32_t n = hdr[8] | (hdr[9] << 8) | (hdr[10] << 16) | ((uint32_t)hdr[11] << 24);
            uint8_t *b = memalign(64, SECTOR_UP(n));
            if (b && lseek(fd, 0, SEEK_SET) == 0 && read(fd, b, SECTOR_UP(n)) >= (int)n) {
                g_fd = fd; *size = n; return b;
            }
            free(b);
        }
        close(fd);
    }
    return 0;
}

static u32 g_io_bytes, g_io_ms;      /* how much was read from the medium and how long it took (see ZNTVN: io) */
static u32 ms_now(void) { return (u32)((GetTimerSystemTime() >> 8) / (PS2_CLOCKS_PER_SEC / 1000)); }

/* fetches `len` bytes of the file at `off` (128-aligned buffer for the GS). NULL on failure. */
static void *blob_read(uint32_t off, uint32_t len)
{
    /* the blob aligns every datum to the sector (see znt/vniso.py), so we ask for
     * the span rounded up: always whole sectors, a single round trip */
    uint32_t want = SECTOR_UP(len ? len : 1);
    uint8_t *b = memalign(128, want);
    if (!b) return 0;
    u32 t0 = ms_now();
    if (lseek(g_fd, off, SEEK_SET) != (int)off) { free(b); return 0; }
    int got = read(g_fd, b, want);                    /* the last datum may come up short: len is enough */
    if (got < (int)len) { free(b); return 0; }
    u32 dt = ms_now() - t0;
    g_io_bytes += len; g_io_ms += dt;
    printf("ZNTVN: io %u bytes in %u ms (%u KB/s cumulative)\n", (unsigned)len, (unsigned)dt,
           (unsigned)(g_io_ms ? g_io_bytes / g_io_ms * 1000 / 1024 : 0));
    return b;
}

/* --- AUDIO (audsrv) ------------------------------------------------------
 * BGM: looping PCM (WAV) stream. SE: ADPCM on SPU2 channels, on top of the BGM.
 * audsrv.irx is embedded in the ELF (bin2c).
 *
 * TWO RULES THAT COST A MUTE BGM AND A HANG:
 *
 * 1. PRIORITIES. The main runs at 0 (the highest) and `gsKit_sync_flip` busy-spins
 *    on the GS register: it never yields the CPU. An audio thread of lower priority
 *    never runs at all (the BGM stayed mute while the SE, which plays on the SPU2
 *    without a thread, worked). audio_init() lowers the main to PRIO_MAIN and leaves
 *    the audio thread above it; that thread only wakes up to fill the ring buffer and
 *    blocks again in audsrv_wait_audio()/DelayThread(), which do yield.
 *
 * 2. A SINGLE THREAD TALKS TO audsrv. The audsrv RPC client is not reentrant:
 *    with the main firing an SE while the thread was streaming, the console hung.
 *    Here the main does NOT call audsrv: it reads the file from the blob (the only
 *    one touching the FILE*) and leaves the request in a slot; the thread makes
 *    every call.
 */
#define PRIO_MAIN 60
#define PRIO_BGM  40
#define BGM_CHUNK 2048            /* ~46 ms at 22 kHz 16-bit mono: SE latency between chunks */
#define MAX_SE 64

static int g_audio_ok;
static u32 le32(const uint8_t *p){ return p[0]|(p[1]<<8)|(p[2]<<16)|((u32)p[3]<<24); }

/* parses a PCM WAV: returns ptr/len of the samples and the format. 0 if not a WAV. */
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

/* --- request slots: written by the main, consumed by the audio thread --- */
static volatile int g_req_bgm;               /* 1 = a new BGM (or a stop) is waiting */
static uint8_t *g_req_bgm_buf; static const uint8_t *g_req_bgm_pcm;
static int g_req_bgm_len, g_req_bgm_freq, g_req_bgm_bits, g_req_bgm_ch;
static volatile int g_req_se = -1;           /* index of the SE to fire (-1 = none) */
static uint8_t *g_req_se_buf; static int g_req_se_len;

/* --- audio thread state (only it touches this) --- */
static uint8_t *g_bgm_buf; static const uint8_t *g_bgm_pcm;
static int g_bgm_len, g_bgm_play, g_bgm_gen, g_bgm_fed;
static audsrv_adpcm_t g_se[MAX_SE]; static int g_se_loaded[MAX_SE];

/* MAIN: leaves the requested BGM (VNP_NONE16 = stop). Reads the file here, not in the thread. */
static void audio_set_bgm(uint16_t idx)
{
    if (!g_audio_ok) return;
    uint8_t *buf = 0; const uint8_t *pcm = 0;
    int plen = 0, freq = 0, bits = 16, ch = 2;
    if (idx != VNP_NONE16) {
        VnpAudio a; vnp_audio(&doc, idx, &a);
        buf = blob_read(a.off, a.len);
        if (!buf) return;
        if (!wav_parse(buf, a.len, &pcm, &plen, &freq, &bits, &ch)) { free(buf); return; }  /* PCM WAV only */
    }
    while (g_req_bgm) DelayThread(1000);      /* the thread has not taken the previous one yet */
    g_req_bgm_buf = buf; g_req_bgm_pcm = pcm; g_req_bgm_len = plen;
    g_req_bgm_freq = freq; g_req_bgm_bits = bits; g_req_bgm_ch = ch;
    g_req_bgm = 1;
}

/* MAIN: leaves an SE request. The first time it attaches the .adp so the thread uploads it. */
static void audio_play_se(uint16_t idx)
{
    if (!g_audio_ok || idx == VNP_NONE16 || idx >= MAX_SE) return;
    if (g_req_se >= 0) return;                /* previous request not consumed yet: dropped */
    uint8_t *buf = 0; int len = 0;
    if (!g_se_loaded[idx]) {
        VnpAudio a; vnp_audio(&doc, idx, &a);
        buf = blob_read(a.off, a.len);
        if (!buf || a.len < 16 || memcmp(buf, "APCM", 4)) { free(buf); return; }   /* not an .adp */
        len = a.len;
    }
    g_req_se_buf = buf; g_req_se_len = len; g_req_se = idx;
}

/* --- THREAD: the only one that calls audsrv --- */
static void bgm_take_request(void)
{
    if (!g_req_bgm) return;
    audsrv_stop_audio();                                  /*AUDIO: drain before changing format*/
    free(g_bgm_buf);
    g_bgm_buf = g_req_bgm_buf; g_bgm_pcm = g_req_bgm_pcm; g_bgm_len = g_req_bgm_len;
    if (g_bgm_pcm) {
        struct audsrv_fmt_t f; f.freq = g_req_bgm_freq; f.bits = g_req_bgm_bits; f.channels = g_req_bgm_ch;
        audsrv_set_format(&f);                            /*AUDIO*/
    }
    g_bgm_play = g_bgm_pcm != 0; g_bgm_gen++; g_req_bgm = 0;
}

static void se_take_request(void)
{
    int idx = g_req_se;
    if (idx < 0) return;
    if (!g_se_loaded[idx] && g_req_se_buf) {
        if (audsrv_load_adpcm(&g_se[idx], g_req_se_buf, g_req_se_len) == 0) g_se_loaded[idx] = 1;  /*AUDIO*/
        free(g_req_se_buf); g_req_se_buf = 0;             /* already in SPU2 RAM */
    }
    if (g_se_loaded[idx]) {
        int ch = audsrv_ch_play_adpcm(-1, &g_se[idx]);    /*AUDIO*/
        if (ch >= 0) audsrv_adpcm_set_volume_and_pan(ch, MAX_VOLUME, 0);
        printf("ZNTVN: se %d channel %d\n", idx, ch);
    }
    g_req_se = -1;
}

static char g_bgm_stack[16 * 1024] __attribute__((aligned(16)));
static void bgm_thread(void *arg)
{
    (void)arg;
    while (1) {
        bgm_take_request(); se_take_request();
        if (g_bgm_play && g_bgm_pcm) {
            int gen = g_bgm_gen, pos = 0;
            while (gen == g_bgm_gen && pos < g_bgm_len) {
                bgm_take_request(); se_take_request();    /* new requests between chunks */
                if (gen != g_bgm_gen) break;
                int n = g_bgm_len - pos; if (n > BGM_CHUNK) n = BGM_CHUNK;
                audsrv_wait_audio(n);                     /*AUDIO: blocks and yields the CPU*/
                audsrv_play_audio((char *)g_bgm_pcm + pos, n);
                if (!g_bgm_fed++) printf("ZNTVN: bgm playing (chunk of %d bytes)\n", n);
                pos += n;
            }                                             /* when done: loop */
        } else
            DelayThread(20 * 1000);                       /* really sleep: the main needs the CPU */
    }
}

extern unsigned char audsrv_irx[]; extern unsigned int size_audsrv_irx;   /* embedded (bin2c) */
static void audio_init(void)
{
    SifLoadModule("rom0:LIBSD", 0, 0);
    if (SifExecModuleBuffer(audsrv_irx, size_audsrv_irx, 0, 0, 0) < 0) return;
    if (audsrv_init() != 0) return;                    /*AUDIO*/
    audsrv_adpcm_init(); audsrv_set_volume(MAX_VOLUME); g_audio_ok = 1;
    ChangeThreadPriority(GetThreadId(), PRIO_MAIN);    /* see note 1 above */
    ee_thread_t t; memset(&t, 0, sizeof(t));
    t.func = bgm_thread; t.stack = g_bgm_stack; t.stack_size = sizeof(g_bgm_stack);
    t.gp_reg = &_gp; t.initial_priority = PRIO_BGM;
    int id = CreateThread(&t); if (id >= 0) StartThread(id, 0);
}

/* --- font: glyph atlas built from the blob --- */
static GSTEXTURE g_font;      /*GSKIT*/ static int g_font_cols, g_have_font;
static int g_choice_sel;      /* highlighted option in a choice */

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
                    px[(cy + y) * aw + (cx + x)] = 0x80FFFFFF;   /* white, alpha 0x80 */
    }
    memset(&g_font, 0, sizeof(g_font));
    g_font.Width = aw; g_font.Height = ah; g_font.PSM = GS_PSM_CT32;
    g_font.Filter = GS_FILTER_NEAREST; g_font.Mem = px;
    gsKit_setup_tbw(&g_font);                                   /*GSKIT*/
    g_font_cols = cols; g_have_font = 1;
}

static int font_cell(uint32_t cp)   /* cell index, or -1 */
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

#define TYPING_CPS 40                /* characters per second (same default as the editor) */
static float g_say_ms;               /* ms since the current dialogue started (typing) */

/* draws ONE already-wrapped line, without looking at the width */
static void draw_line(GSGLOBAL *gs, float x, float y, const char *s, int len,
                      uint8_t r, uint8_t g_, uint8_t b, int maxcp)
{
    int fw = doc.font_w, fh = doc.font_h, i = 0, shown = 0;
    float pen = x;
    while (i < len && (maxcp < 0 || shown++ < maxcp)) {
        unsigned int cp = text_utf8_next(s, len, &i);
        int cell = font_cell(cp);
        if (cell >= 0) {
            int cx = (cell % g_font_cols) * fw, cy = (cell / g_font_cols) * fh;
            gsKit_prim_sprite_texture(gs, &g_font, pen, y, cx, cy, pen+fw, y+fh, cx+fw, cy+fh,
                                      4, GS_SETREG_RGBAQ(r, g_, b, 0x80, 0));
        }
        pen += fw;
    }
}

/* draws UTF-8 text wrapping by word (ps2/text.c); `maxcp` = codepoints to show
 * (-1 all), for the typing effect. Returns how many lines it took.  [GSKIT] */
static int draw_text(GSGLOBAL *gs, float x, float y, const char *s, int len,
                     uint8_t r, uint8_t g_, uint8_t b, int maxcp)
{
    if (!g_have_font || !s) return 0;
    int fw = doc.font_w, fh = doc.font_h;
    int cols = (int)((SCR_W - 32 - x) / fw); if (cols < 1) cols = 1;
    TextWrap w; text_wrap_init(&w, s, len);
    int off, n, rows = 0, left = maxcp;
    while (text_wrap_next(&w, cols, &off, &n)) {
        if (left == 0) break;
        draw_line(gs, x, y + rows * (fh + 2), s + off, n, r, g_, b, left);
        if (left > 0) { int cp = text_utf8_count(s + off, n); left = cp >= left ? 0 : left - cp; }
        rows++;
    }
    return rows;
}

/* --- active layer on the stage --- */
typedef struct {
    int used, chr;
    float x, y; int z, zoom, opacity;
    GSTEXTURE tex;      /*GSKIT*/  int has_tex;
    /* animation (same model as engine.py): one tween per coordinate */
    struct { int active, curve; float from, to, dur, t; } twx, twy;
    int   ac_kind, ac_done;    float ac_vib, ac_cycle, ac_dist, ac_time, ac_now, ac_next, ac_ox, ac_oy;
} Layer;

/* ease() from engine.py: normal t, accel t^2, decel 1-(1-t)^2 */
static float easef(int curve, float k)
{
    if (curve == AN_ACCEL) return k * k;
    if (curve == AN_DECEL) return 1.0f - (1.0f - k) * (1.0f - k);
    return k;
}
static uint32_t g_rng = 0x2545F491;
static int rnd_range(int n) { g_rng = g_rng * 1103515245u + 12345u; return n > 0 ? (int)((g_rng >> 16) % (uint32_t)n) : 0; }

/* Action.tick() from engine.py. For vibrate, ac_cycle is used as waitTime. */
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
/* current and previous background (crossfade): kind -1 = none, 0 solid, 1 grad, 2 image */
typedef struct { int kind; uint32_t a, b; GSTEXTURE tex; int has_tex; } Bg;
static Bg g_bg = { -1 }, g_bgprev = { -1 };
static Tween g_fade;                       /* opacity of the new background over the previous one */
static float g_bg_alpha = 1.0f;
static uint32_t g_frames;

/* frees a texture: whatever VRAM it holds and its buffers.  [GSKIT] */
static void tex_free(GSGLOBAL *gs, GSTEXTURE *t)
{
    if (t->Mem) gsKit_TexManager_free(gs, t);
    free(t->Mem); free(t->Clut);
    t->Mem = 0; t->Clut = 0;
}

/* RGBA from the blob -> GS format: alpha 0..255 becomes 0..0x80 and the channels are swapped */
static u32 gs_color(const uint8_t *s) { return ((u32)(s[3] >> 1) << 24) | (s[2] << 16) | (s[1] << 8) | s[0]; }

/* uploads an image from the blob into a GSTEXTURE. fmt 0 = RGBA32, fmt 1 = 8bpp + CLUT
 * (4x less VRAM and 4x fewer disk bytes; the CLUT already comes in GS order).  [GSKIT] */
static void upload_image(GSGLOBAL *gs, uint16_t img_idx, GSTEXTURE *t)
{
    VnpImage im; vnp_image(&doc, img_idx, &im);
    memset(t, 0, sizeof(*t));
    t->Width = im.w; t->Height = im.h;
    t->Filter = GS_FILTER_LINEAR;
    uint32_t n = (uint32_t)im.w * im.h;

    if (im.fmt == 1) {
        uint8_t *raw = blob_read(im.off, 1024 + n);        /* CLUT + one byte per pixel */
        if (!raw) return;
        u32 *clut = memalign(128, 1024);
        if (!clut) { free(raw); return; }
        for (int i = 0; i < 256; i++) clut[i] = gs_color(raw + i * 4);
        memmove(raw, raw + 1024, n);                       /* indices to the front: free(raw) still works */
        t->PSM = GS_PSM_T8; t->ClutPSM = GS_PSM_CT32;
        t->Clut = clut; t->Mem = (u32 *)raw;
    } else {
        u32 *px = blob_read(im.off, n * 4);                /* on demand; converted in place */
        if (!px) return;
        for (uint32_t i = 0; i < n; i++) px[i] = gs_color((uint8_t *)px + i * 4);
        t->PSM = GS_PSM_CT32; t->Mem = px;
    }
    gsKit_setup_tbw(t);                        /*GSKIT*/
    printf("ZNTVN: img %u %ux%u fmt=%u %u bytes\n", (unsigned)img_idx, (unsigned)im.w,
           (unsigned)im.h, (unsigned)im.fmt, (unsigned)im.len);
    /* the actual upload to VRAM is done by gsKit_TexManager_bind per frame (streaming). */
}

/* applies the scene's non-blocking steps up to a say/choice/goto/end.
 * The g_sc cursor is global -> "advance" continues from where it left off (resumable). */
typedef struct { int kind; /*1 say,2 choice,3 end*/ VnpStep step; } Block;

static VnpScene g_sc;
static Block advance(GSGLOBAL *gs);   /* continues the current cursor */

static int g_autoplay;              /* argv "autoplay": advances and chooses on its own (for the harness) */
enum { UI_PLAY = 0, UI_MENU, UI_LOG };
static int g_ui;                    /* screen over the game: pause menu or history */
static int g_savetest;              /* argv "savetest": saves, reads back and verifies (for the harness) */

static uint32_t g_step_n;           /* steps consumed from the scene */
static uint32_t g_block_idx;        /* index of the step where the current block stopped (what gets saved) */
static uint16_t g_bgm_idx = VNP_NONE16;   /* BGM playing, so the save remembers it */

/* --- dialogue history (Select). Stores indices into the blob's string pool,
 *     which is already in RAM: no text is copied. --- */
#define LOG_N 24
static struct { uint16_t who; uint32_t text; } g_log[LOG_N];
static int g_log_n;
static void log_push(uint16_t who, uint32_t text)
{
    int i = g_log_n % LOG_N;
    g_log[i].who = who; g_log[i].text = text; g_log_n++;
}

/* --- saved game on the memory card --------------------------------------------
 * Saves where we stopped (scene + step) and which music was playing; on load the
 * scene is replayed up to that step, so sprites and background return to place. The
 * format (magic, version, CRC) is in ps2/save.c, tested on the host. */
#define SAVE_DIR  "/ZNTVN"
#define SAVE_PATH "/ZNTVN/SAVE.BIN"

/* The memory card goes through libmc, not open()/write(): the SDK's newlib port
 * does not expose mc0: (and warns that mixing fio with newlib causes trouble). All
 * calls are asynchronous: each one is closed with mcSync. */
static int mc_wait(void) { int r = -1; mcSync(MC_WAIT, NULL, &r); return r; }

static int g_mc_fmt = -1;          /* -1 unknown, 0 unformatted, 1 formatted */

static void mc_init(void)
{
    SifLoadModule("rom0:MCMAN", 0, 0);
    SifLoadModule("rom0:MCSERV", 0, 0);
    if (mcInit(MC_TYPE_MC) < 0) printf("ZNTVN: memory card not available\n");
}

/* 0 = ready to use, -2 = unformatted, -1 = no card */
static int mc_status(void)
{
    int type = 0, freeb = 0, fmt = 0;
    mcGetInfo(0, 0, &type, &freeb, &fmt);
    int r = mc_wait();
    /* With MCMAN/MCSERV the `fmt` parameter always comes back 0: the real state is in
     * the return value (0 the same card as before, -1 another formatted one, -2 another
     * unformatted one, -10 or less none). Hence what was seen the first time is remembered. */
    if (r <= -10) { g_mc_fmt = -1; return -1; }
    if (r == -2) g_mc_fmt = 0;
    else if (r == -1) g_mc_fmt = 1;
    return g_mc_fmt == 0 ? -2 : 0;
}

static int game_save(void)
{
    uint8_t buf[SAVE_SIZE] __attribute__((aligned(64)));
    save_pack(buf, (uint16_t)cur_scene, g_block_idx, g_bgm_idx);
    int st = mc_status();
    if (st) { printf(st == -2 ? "ZNTVN: save FAILED: memory card unformatted\n"
                              : "ZNTVN: save FAILED: no memory card\n"); return -1; }
    mcMkDir(0, 0, SAVE_DIR); mc_wait();        /* if it already exists, the error does not matter */
    /* CAREFUL: mcOpen's `mode` is NOT the open() flags: it is the attributes that get
     * recorded on the card. O_RDONLY is 0, i.e. "no permissions", and reading afterwards
     * gave -5 (permission denied). Read AND write must be requested. */
    mcOpen(0, 0, SAVE_PATH, MC_ATTR_READABLE | MC_ATTR_WRITEABLE | O_CREAT);
    int fd = mc_wait();
    if (fd < 0) { printf("ZNTVN: save FAILED to open (%d)\n", fd); return -1; }
    mcWrite(fd, buf, SAVE_SIZE); int n = mc_wait();
    mcClose(fd); mc_wait();
    if (n != SAVE_SIZE) { printf("ZNTVN: save FAILED to write (%d)\n", n); return -1; }
    printf("ZNTVN: save scene %u step %u\n", (unsigned)cur_scene, (unsigned)g_block_idx);
    return 0;
}

static int game_load(uint16_t *scene, uint32_t *step, uint16_t *bgm)
{
    uint8_t buf[SAVE_SIZE] __attribute__((aligned(64)));
    if (mc_status()) { printf("ZNTVN: no usable memory card\n"); return -1; }
    mcOpen(0, 0, SAVE_PATH, MC_ATTR_READABLE);      /* see the note in game_save */
    int fd = mc_wait();
    if (fd < 0) { printf("ZNTVN: no saved game\n"); return -1; }
    mcRead(fd, buf, SAVE_SIZE); int n = mc_wait();
    mcClose(fd); mc_wait();
    if (save_unpack(buf, n, scene, step, bgm)) { printf("ZNTVN: invalid save\n"); return -1; }
    if (*scene >= doc.n_scenes) { printf("ZNTVN: save from another VN\n"); return -1; }
    printf("ZNTVN: load scene %u step %u\n", (unsigned)*scene, (unsigned)*step);
    return 0;
}

static Block enter_scene(GSGLOBAL *gs, uint32_t scene)
{
    printf("ZNTVN: scene %u\n", (unsigned)scene);
    for (int i = 0; i < MAX_LAYERS; i++) if (layers[i].has_tex) tex_free(gs, &layers[i].tex);
    memset(layers, 0, sizeof(layers));                  /* the background persists across scenes */
    cur_scene = scene; g_step_n = 0; g_block_idx = 0;
    Block blk; memset(&blk, 0, sizeof(blk));
    if (vnp_scene_begin(&doc, scene, &g_sc)) { blk.kind = 3; return blk; }
    return advance(gs);
}

/* Replays the scene up to step `k` (loading a save): advances block by block
 * applying everything, so the background and sprites end up as they were. */
static Block enter_scene_at(GSGLOBAL *gs, uint32_t scene, uint32_t k)
{
    Block blk = enter_scene(gs, scene);
    while (blk.kind != 3 && g_block_idx < k) blk = advance(gs);
    return blk;
}

static Block advance(GSGLOBAL *gs)
{
    VnpStep s; Block blk; memset(&blk, 0, sizeof(blk));
    while (vnp_step(&g_sc, &s)) {
        g_block_idx = g_step_n++;               /* where we are standing (what the save records) */
        switch (s.op) {
        case OP_BG:
            /* solid/grad: background colour; img: full-screen texture (layer 0). */
            if (g_bgprev.has_tex) tex_free(gs, &g_bgprev.tex);
            if (s.bg_fade && g_bg.kind >= 0) {          /* the old background stays underneath while the fade lasts */
                g_bgprev = g_bg; tween_start(&g_fade, 0.0f, 1.0f, s.bg_fade, AN_LINEAR); g_bg_alpha = 0.0f;
            } else {
                if (g_bg.has_tex) tex_free(gs, &g_bg.tex);
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
            if (L->has_tex) tex_free(gs, &L->tex);     /* slot recycled from a hide */
            memset(L, 0, sizeof(*L));
            L->used = 1; L->chr = s.chr;
            L->x = s.x; L->y = s.y; L->z = s.z; L->zoom = s.zoom; L->opacity = s.opacity;
            VnpChar c; vnp_char(&doc, s.chr, &c);
            uint16_t img = (s.img != VNP_NONE16) ? s.img : c.sprite;   /* expression or base */
            if (img != VNP_NONE16) { upload_image(gs, img, &L->tex); L->has_tex = L->tex.Mem != 0; }
            break; }
        case OP_HIDE:
            for (int i = 1; i < MAX_LAYERS; i++) if (layers[i].used && layers[i].chr == s.chr) layers[i].used = 0;
            break;
        case OP_SAY:   blk.kind = 1; blk.step = s; log_push(s.who, s.text); return blk;
        case OP_CHOICE:blk.kind = 2; blk.step = s;
                       printf("ZNTVN: choice with %d options\n", s.n_opts); return blk;
        case OP_ANIM: {
            Layer *L = 0;
            for (int i = 1; i < MAX_LAYERS; i++) if (layers[i].used && layers[i].chr == s.chr) L = &layers[i];
            if (!L) break;
            if (s.an_kind <= AN_MOVE) {                 /* movement with curve, per given coordinate */
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
        case OP_BGM:   g_bgm_idx = s.bgm_stop ? VNP_NONE16 : s.audio; audio_set_bgm(g_bgm_idx); break;
        case OP_SE:    audio_play_se(s.audio); break;
        case OP_GOTO:  return enter_scene(gs, s.target);
        case OP_END:   blk.kind = 3; return blk;
        default: break;
        }
    }
    blk.kind = 3; return blk;
}

/* background: flat colour, vertical gradient or image, with alpha (blob colours: 0xRRGGBBAA) */
#define BGCOL(c, a) GS_SETREG_RGBAQ(((c) >> 24) & 0xff, ((c) >> 16) & 0xff, ((c) >> 8) & 0xff, (a), 0)
static void draw_bg(GSGLOBAL *gs, Bg *bg, float alpha)
{
    uint8_t a = (uint8_t)(alpha * 0x80);
    if (bg->kind == 0) {
        gsKit_prim_sprite(gs, 0, 0, SCR_W, SCR_H, 1, BGCOL(bg->a, a));
    } else if (bg->kind == 1) {          /* (gsKit prims are macros with their own ';': braces) */
        gsKit_prim_quad_gouraud(gs, 0, 0, SCR_W, 0, 0, SCR_H, SCR_W, SCR_H, 1,
                                BGCOL(bg->a, a), BGCOL(bg->a, a), BGCOL(bg->b, a), BGCOL(bg->b, a));
    } else if (bg->has_tex) {
        gsKit_TexManager_bind(gs, &bg->tex);
        gsKit_prim_sprite_texture(gs, &bg->tex, 0, 0, 0, 0, SCR_W, SCR_H, bg->tex.Width, bg->tex.Height,
                                  1, GS_SETREG_RGBAQ(0x80, 0x80, 0x80, a, 0));
    }
}

/* draws the frame: layers by Z (higher Z in front) + dialogue box.  [GSKIT] */
static void draw_frame(GSGLOBAL *gs, const Block *blk)
{
    gsKit_clear(gs, GS_SETREG_RGBAQ(0, 0, 0, 0x80, 0));
    if (g_bgprev.kind >= 0) draw_bg(gs, &g_bgprev, 1.0f);   /* crossfade: the old one underneath, the new one with alpha */
    if (g_bg.kind >= 0) draw_bg(gs, &g_bg, g_bg_alpha);
    /* order: lowest z first (background, z=-1000) and highest z in front (same convention as the editor) */
    for (int pass = -1000; pass <= 1000; pass++) {
        for (int i = 0; i < MAX_LAYERS; i++) {
            Layer *L = &layers[i];
            if (!L->used || !L->has_tex || L->z != pass) continue;
            gsKit_TexManager_bind(gs, &L->tex);           /*GSKIT: uploads to VRAM this frame (if it fits)*/
            float w = L->tex.Width * L->zoom / 100.0f;
            float h = L->tex.Height * L->zoom / 100.0f;
            float cx = SCR_W / 2.0f + L->x + L->ac_ox;     /* centred on x + action offset */
            float x0 = cx - w / 2.0f, y0 = SCR_H - h + L->y + L->ac_oy;
            uint8_t a = (uint8_t)(L->opacity * 0x80 / 100);
            gsKit_prim_sprite_texture(gs, &L->tex, x0, y0, 0, 0,
                                      x0 + w, y0 + h, L->tex.Width, L->tex.Height,
                                      2, GS_SETREG_RGBAQ(0x80, 0x80, 0x80, a, 0));
        }
    }
    /* dialogue box (semi-transparent rect at the bottom) */
    if (blk->kind == 1 || blk->kind == 2)
        gsKit_prim_sprite(gs, 24, SCR_H - 108, SCR_W - 24, SCR_H - 12, 3,
                          GS_SETREG_RGBAQ(0x0b, 0x13, 0x30, 0x60, 0));
    if (g_have_font) gsKit_TexManager_bind(gs, &g_font);          /*GSKIT*/
    if (blk->kind == 1) {                                          /* dialogue */
        if (blk->step.who != VNP_NONE16) {
            VnpChar c; vnp_char(&doc, blk->step.who, &c);
            VnpStr nm = vnp_str(&doc, c.name);
            draw_text(gs, 36, SCR_H - 102, nm.ptr, nm.len, 0xe8, 0xb0, 0x4b, -1);
        }
        VnpStr t = vnp_str(&doc, blk->step.text);
        draw_text(gs, 36, SCR_H - 82, t.ptr, t.len, 0xff, 0xff, 0xff, (int)(g_say_ms * TYPING_CPS / 1000.0f));
    } else if (blk->kind == 2) {                                   /* options */
        for (int i = 0; i < blk->step.n_opts; i++) {
            VnpStr l = vnp_str(&doc, blk->step.opt_label[i]);
            int sel = (i == g_choice_sel);
            draw_text(gs, sel ? 52 : 40, SCR_H - 100 + i * 20, l.ptr, l.len,
                      sel ? 0xff : 0xa0, sel ? 0xd0 : 0xa0, sel ? 0x40 : 0xa0, -1);
        }
    }
}

/* --- pause menu (Start) and history (Select) ------------------------------ */
static int g_menu_sel;
static const char *MENU[] = { "Resume", "Save", "Load" };
#define MENU_N 3

static void draw_panel(GSGLOBAL *gs, float x0, float y0, float x1, float y1)
{
    gsKit_prim_sprite(gs, x0, y0, x1, y1, 6, GS_SETREG_RGBAQ(0x08, 0x0c, 0x20, 0x70, 0));
}

static void draw_overlay(GSGLOBAL *gs)
{
    if (g_ui == UI_MENU) {
        draw_panel(gs, 180, 120, 460, 260);
        if (g_have_font) gsKit_TexManager_bind(gs, &g_font);
        draw_text(gs, 200, 136, "Pause", 5, 0xe8, 0xb0, 0x4b, -1);
        for (int i = 0; i < MENU_N; i++) {
            int sel = (i == g_menu_sel);
            draw_text(gs, sel ? 216 : 204, 176 + i * 24, MENU[i], (int)strlen(MENU[i]),
                      sel ? 0xff : 0xa0, sel ? 0xd0 : 0xa0, sel ? 0x40 : 0xa0, -1);
        }
    } else if (g_ui == UI_LOG) {
        draw_panel(gs, 40, 40, SCR_W - 40, SCR_H - 40);
        if (g_have_font) gsKit_TexManager_bind(gs, &g_font);
        draw_text(gs, 56, 52, "History (Select to close)", 25, 0xe8, 0xb0, 0x4b, -1);
        int n = g_log_n < LOG_N ? g_log_n : LOG_N;      /* the last n, in order */
        int first = g_log_n - n;
        float y = 80;
        for (int k = 0; k < n && y < SCR_H - 80; k++) {
            int i = (first + k) % LOG_N;
            if (g_log[i].who != VNP_NONE16) {
                VnpChar c; vnp_char(&doc, g_log[i].who, &c);
                VnpStr nm = vnp_str(&doc, c.name);
                draw_text(gs, 56, y, nm.ptr, nm.len, 0xe8, 0xb0, 0x4b, -1);
                y += doc.font_h + 2;
            }
            VnpStr t = vnp_str(&doc, g_log[i].text);
            y += draw_text(gs, 72, y, t.ptr, t.len, 0xff, 0xff, 0xff, -1) * (doc.font_h + 2) + 6;
        }
    }
}

/* --- pad --- */
static char pad_buf[256] __attribute__((aligned(64)));
static u32 g_pad_now;                     /* buttons held down NOW (for the skip) */
static u32 pad_pressed(u32 *prev)
{
    struct padButtonStatus b;
    if (padGetState(0, 0) != PAD_STATE_STABLE || !padRead(0, 0, &b)) { g_pad_now = 0; return 0; }
    u32 now = 0xffff ^ b.btns; u32 hit = now & ~(*prev); *prev = now; g_pad_now = now; return hit;
}

int main(int argc, char **argv)
{
    SifInitRpc(0);
    for (int i = 1; i < argc; i++) {
        if (!argv[i]) continue;
        if (!strcmp(argv[i], "autoplay")) g_autoplay = 1;
        if (!strcmp(argv[i], "savetest")) g_savetest = 1;
        if (!strcmp(argv[i], "menu")) g_ui = UI_MENU;      /* to take a screenshot of the menu */
        if (!strcmp(argv[i], "log")) g_ui = UI_LOG;
    }
    if (g_autoplay) printf("ZNTVN: autoplay\n");
    sbv_patch_enable_lmb(); sbv_patch_disable_prefix_check();   /* for SifExecModuleBuffer */
    uint32_t size = 0; uint8_t *blob = load_blob(&size);
    if (!blob || vnp_open(&doc, blob, size)) { printf("VNP not found/invalid\n"); SleepThread(); }
    printf("ZNTVN: blob OK v%u, header %u bytes in RAM, %u scenes, %u images, font %ux%u x%u\n", (unsigned)doc.version, (unsigned)size, (unsigned)doc.n_scenes, (unsigned)doc.n_images, (unsigned)doc.font_w, (unsigned)doc.font_h, (unsigned)doc.font_n);

    GSGLOBAL *gs = gsKit_init_global();                   /*GSKIT*/
    dmaKit_init(D_CTRL_RELE_OFF, D_CTRL_MFD_OFF, D_CTRL_STS_UNSPEC,
                D_CTRL_STD_OFF, D_CTRL_RCYC_8, 1 << DMA_CHANNEL_GIF);
    dmaKit_chan_init(DMA_CHANNEL_GIF);
    gs->Mode = GS_MODE_NTSC; gs->Width = SCR_W; gs->Height = SCR_H;
    gs->PSM = GS_PSM_CT24; gs->PSMZ = GS_PSMZ_16S;
    /* VRAM (4 MB): a single framebuffer and no Z (the order is painter's by z) leaves ~3 MB
     * for RGBA32 textures: a 640x448 background (1.1 MB) + several sprites. With double buffer
     * + Z only 1.3 MB was left and the second sprite did not fit (bind failed silently). */
    gs->DoubleBuffering = GS_SETTING_OFF; gs->ZBuffering = GS_SETTING_OFF;
    gs->PrimAlphaEnable = GS_SETTING_ON;                  /* PNG with alpha + layer opacity */
    gsKit_init_screen(gs);
    gsKit_set_primalpha(gs, GS_SETREG_ALPHA(0, 1, 0, 1, 0), 0);   /* out = src*a + dst*(1-a) */ gsKit_mode_switch(gs, GS_ONESHOT);
    gsKit_TexManager_init(gs);
    build_font_atlas(gs);
    audio_init();

    /* pad */
    SifLoadModule("rom0:SIO2MAN", 0, 0); SifLoadModule("rom0:PADMAN", 0, 0);
    padInit(0); padPortOpen(0, 0, pad_buf);
    mc_init();
    u32 prev = 0;

    Block blk = enter_scene(gs, doc.start);
    g_choice_sel = 0; g_say_ms = 0;

    if (g_savetest) {                       /* the harness verifies the full round trip */
        if (mc_status() == -2) {            /* test mode only: an unformatted card has nothing to lose */
            printf("ZNTVN: formatting memory card (savetest)\n");
            mcFormat(0, 0); mc_wait(); g_mc_fmt = 1;
        }
        blk = advance(gs);
        uint16_t sc = 0, bg = 0; uint32_t stp = 0;
        int ok = game_save() == 0 && game_load(&sc, &stp, &bg) == 0
                 && sc == cur_scene && stp == g_block_idx;
        printf(ok ? "ZNTVN: savetest OK\n" : "ZNTVN: savetest FAILED\n");
    }

    int auto_t = 0, skip_t = 0;
    while (blk.kind != 3) {
        u32 hit = pad_pressed(&prev);
        if (g_autoplay && ++auto_t >= 45) {          /* ~0.75 s: as if someone pressed X */
            auto_t = 0; hit |= PAD_CROSS;
            if (g_ui == UI_PLAY && blk.kind == 2) g_choice_sel = blk.step.n_opts - 1;  /* the last one: exercises goto */
        }
        /* Triangle held: skip text fast (no typing) */
        if (g_ui == UI_PLAY && blk.kind == 1 && (g_pad_now & PAD_TRIANGLE) && ++skip_t >= 6) {
            skip_t = 0; g_say_ms = 1e9f; hit |= PAD_CROSS;
        }

        if (g_ui == UI_MENU) {
            if (hit & PAD_UP)   g_menu_sel = (g_menu_sel + MENU_N - 1) % MENU_N;
            if (hit & PAD_DOWN) g_menu_sel = (g_menu_sel + 1) % MENU_N;
            if (hit & (PAD_CIRCLE | PAD_START)) g_ui = UI_PLAY;
            else if (hit & PAD_CROSS) {
                if (g_menu_sel == 1) game_save();
                else if (g_menu_sel == 2) {
                    uint16_t sc, bg; uint32_t stp;
                    if (game_load(&sc, &stp, &bg) == 0) {
                        blk = enter_scene_at(gs, sc, stp);
                        g_bgm_idx = bg; audio_set_bgm(bg); g_say_ms = 0; g_choice_sel = 0;
                    }
                }
                g_ui = UI_PLAY;
            }
        } else if (g_ui == UI_LOG) {
            if (hit & (PAD_SELECT | PAD_CIRCLE | PAD_CROSS | PAD_START)) g_ui = UI_PLAY;
        } else if (hit & PAD_START) {
            g_ui = UI_MENU; g_menu_sel = 0;
        } else if (hit & PAD_SELECT) {
            g_ui = UI_LOG;
        } else if (blk.kind == 1 && (hit & PAD_CROSS)) {   /* X: completes the typing; the next one advances */
            VnpStr t = vnp_str(&doc, blk.step.text);
            if (g_say_ms * TYPING_CPS / 1000.0f < text_utf8_count(t.ptr, t.len)) g_say_ms = 1e9f;
            else { blk = advance(gs); g_say_ms = 0; }
        } else if (blk.kind == 2) {
            if (hit & PAD_UP)   g_choice_sel = (g_choice_sel + blk.step.n_opts - 1) % blk.step.n_opts;
            if (hit & PAD_DOWN) g_choice_sel = (g_choice_sel + 1) % blk.step.n_opts;
            if (hit & PAD_CROSS) {
                printf("ZNTVN: choose %d -> scene %u\n", g_choice_sel, (unsigned)blk.step.opt_target[g_choice_sel]);
                blk = enter_scene(gs, blk.step.opt_target[g_choice_sel]); g_choice_sel = 0; g_say_ms = 0;
            }
        }
        for (int i = 0; i < MAX_LAYERS; i++) if (layers[i].used) layer_tick(&layers[i], 16.0f);  /* ~60fps */
        g_say_ms += 16.0f;
        g_bg_alpha = tween_tick(&g_fade, 16.0f, g_bg_alpha);
        if (!g_fade.active && g_bgprev.kind >= 0) {          /* fade finished: the old one goes away */
            if (g_bgprev.has_tex) tex_free(gs, &g_bgprev.tex);
            g_bgprev.kind = -1; g_bgprev.has_tex = 0;
        }
        gsKit_TexManager_nextFrame(gs);
        draw_frame(gs, &blk);
        draw_overlay(gs);
        gsKit_queue_exec(gs); gsKit_sync_flip(gs);
        if (++g_frames == 1) printf("ZNTVN: frame OK (scene %u, block %d)\n", (unsigned)cur_scene, blk.kind);
    }
    printf("ZNTVN: end\n");
    while (1) { gsKit_clear(gs, GS_SETREG_RGBAQ(0,0,0,0x80,0)); gsKit_sync_flip(gs); }
    return 0;
}
