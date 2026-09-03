/* VN player para PS2 (camino C del spike) — PROOF OF LIFE.
 *
 * Estado: el LECTOR del blob (vnp.c) está verificado en host contra vniso.py.
 * Este main.c es un esqueleto gsKit para COMPILAR con ps2dev e ITERAR en PCSX2.
 * La lógica del intérprete (nuestra) es sólida; el glue de gsKit (marcado /*GSKIT*/)
 * puede necesitar ajustes según tu versión de gsKit — verificá esos puntos al build.
 *
 * Cubre: bg (solid/grad/img), sprites (Z, zoom, opacidad), caja de diálogo, avance
 * y choices con el pad. Falta (siguiente iteración): texto con fuente, animación por
 * tiempo, audio (SPU2). Ver ps2/README.md.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <kernel.h>
#include <gsKit.h>
#include <dmaKit.h>
#include <libpad.h>
#include <sifrpc.h>
#include <loadfile.h>
#include "vnp.h"

#define SCR_W 640
#define SCR_H 448
#define MAX_LAYERS 16

/* --- carga del blob: proba host: (PCSX2), mass: (USB) y cdrom0: (ISO) --- */
static uint8_t *load_blob(uint32_t *size)
{
    const char *paths[] = { "host:ZNTVN.VNP", "mass:ZNTVN.VNP", "cdrom0:\\ZNTVN.VNP;1", 0 };
    for (int i = 0; paths[i]; i++) {
        FILE *f = fopen(paths[i], "rb");
        if (!f) continue;
        fseek(f, 0, SEEK_END); long n = ftell(f); fseek(f, 0, SEEK_SET);
        uint8_t *b = malloc(n);
        if (fread(b, 1, n, f) == (size_t)n) { fclose(f); *size = n; return b; }
        fclose(f); free(b);
    }
    return 0;
}

/* --- capa activa en el stage --- */
typedef struct {
    int used, chr;
    int x, y, z, zoom, opacity;
    GSTEXTURE tex;      /*GSKIT*/  int has_tex;
} Layer;

static VnpDoc doc;
static Layer layers[MAX_LAYERS];
static uint32_t cur_scene;

/* sube una imagen RGBA del blob a una GSTEXTURE (PSMCT32). /*GSKIT*/ */
static void upload_image(GSGLOBAL *gs, uint16_t img_idx, GSTEXTURE *t)
{
    VnpImage im; vnp_image(&doc, img_idx, &im);
    memset(t, 0, sizeof(*t));
    t->Width = im.w; t->Height = im.h;
    t->PSM = GS_PSM_CT32;
    t->Filter = GS_FILTER_LINEAR;
    /* El GS quiere RGBA con alfa 0..0x80. Nuestro alfa es 0..255 -> escalar /2. */
    uint32_t n = (uint32_t)im.w * im.h;
    uint32_t *px = memalign(128, n * 4);
    for (uint32_t i = 0; i < n; i++) {
        const uint8_t *s = im.rgba + i * 4;
        uint8_t a = s[3] >> 1;                 /* 0..127 (0x80 = opaco en PS2) */
        px[i] = (a << 24) | (s[2] << 16) | (s[1] << 8) | s[0];
    }
    t->Mem = px;
    gsKit_setup_tbw(t);                        /*GSKIT*/
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
    memset(layers, 0, sizeof(layers));
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
            if (s.bg_kind == 2) {
                Layer *L = &layers[0]; L->used = 1; L->chr = -1;
                L->x = 0; L->y = 0; L->z = -1000; L->zoom = 100; L->opacity = 100;
                upload_image(gs, s.bg_img, &L->tex); L->has_tex = 1;
            }
            break;
        case OP_SHOW: {
            int slot = -1;
            for (int i = 1; i < MAX_LAYERS; i++) if (!layers[i].used) { slot = i; break; }
            if (slot < 0) break;
            Layer *L = &layers[slot];
            L->used = 1; L->chr = s.chr;
            L->x = s.x; L->y = s.y; L->z = s.z; L->zoom = s.zoom; L->opacity = s.opacity;
            VnpChar c; vnp_char(&doc, s.chr, &c);
            if (c.sprite != VNP_NONE16) { upload_image(gs, c.sprite, &L->tex); L->has_tex = 1; }
            break; }
        case OP_HIDE:
            for (int i = 1; i < MAX_LAYERS; i++) if (layers[i].used && layers[i].chr == s.chr) layers[i].used = 0;
            break;
        case OP_SAY:   blk.kind = 1; blk.step = s; return blk;
        case OP_CHOICE:blk.kind = 2; blk.step = s; return blk;
        case OP_GOTO:  return enter_scene(gs, s.target);
        case OP_END:   blk.kind = 3; return blk;
        default: break; /* anim/bgm/se: siguiente iteración */
        }
    }
    blk.kind = 3; return blk;
}

/* dibuja el frame: capas por Z (mayor Z al fondo) + caja de diálogo. /*GSKIT*/ */
static void draw_frame(GSGLOBAL *gs, const Block *blk)
{
    gsKit_clear(gs, GS_SETREG_RGBAQ(0x10, 0x18, 0x30, 0x80, 0));
    /* orden: dibujar de mayor z (fondo) a menor z (frente) */
    for (int pass = 1000; pass >= -1000; pass--) {
        for (int i = 0; i < MAX_LAYERS; i++) {
            Layer *L = &layers[i];
            if (!L->used || !L->has_tex || L->z != pass) continue;
            gsKit_TexManager_bind(gs, &L->tex);           /*GSKIT: sube a VRAM este frame*/
            float w = L->tex.Width * L->zoom / 100.0f;
            float h = L->tex.Height * L->zoom / 100.0f;
            float cx = SCR_W / 2.0f + L->x;                /* centrado en x */
            float x0 = cx - w / 2.0f, y0 = SCR_H - h + L->y;
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
    /* TODO(siguiente): texto del diálogo / opciones con fuente bitmap. */
}

/* --- pad --- */
static char pad_buf[256] __attribute__((aligned(64)));
static int pad_pressed(u32 *prev)
{
    struct padButtonStatus b; padRead(0, 0, &b);
    u32 now = 0xffff ^ b.btns; u32 hit = now & ~(*prev); *prev = now; return hit;
}

int main(void)
{
    SifInitRpc(0);
    uint32_t size; uint8_t *blob = load_blob(&size);
    if (!blob || vnp_open(&doc, blob, size)) { printf("VNP no encontrado/invalido\n"); SleepThread(); }

    GSGLOBAL *gs = gsKit_init_global();                   /*GSKIT*/
    dmaKit_init(D_CTRL_RELE_OFF, D_CTRL_MFD_OFF, D_CTRL_STS_UNSPEC,
                D_CTRL_STD_OFF, D_CTRL_RCYC_8, 1 << DMA_CHANNEL_GIF);
    dmaKit_chan_init(DMA_CHANNEL_GIF);
    gs->Mode = GS_MODE_NTSC; gs->Width = SCR_W; gs->Height = SCR_H;
    gs->PSM = GS_PSM_CT24; gs->PSMZ = GS_PSMZ_16S;
    gsKit_init_screen(gs); gsKit_mode_switch(gs, GS_ONESHOT);
    gsKit_TexManager_init(gs);

    /* pad */
    SifLoadModule("rom0:SIO2MAN", 0, 0); SifLoadModule("rom0:PADMAN", 0, 0);
    padInit(0); padPortOpen(0, 0, pad_buf);
    u32 prev = 0;

    Block blk = enter_scene(gs, doc.start);
    int choice_sel = 0;

    while (blk.kind != 3) {
        u32 hit = pad_pressed(&prev);
        if (blk.kind == 1 && (hit & PAD_CROSS)) {          /* avanzar diálogo: continúa el cursor */
            blk = advance(gs);
        } else if (blk.kind == 2) {
            if (hit & PAD_UP)   choice_sel = (choice_sel + blk.step.n_opts - 1) % blk.step.n_opts;
            if (hit & PAD_DOWN) choice_sel = (choice_sel + 1) % blk.step.n_opts;
            if (hit & PAD_CROSS) { blk = enter_scene(gs, blk.step.opt_target[choice_sel]); choice_sel = 0; }
        }
        gsKit_TexManager_nextFrame(gs);
        draw_frame(gs, &blk);
        gsKit_queue_exec(gs); gsKit_sync_flip(gs);
    }
    /* fin */
    while (1) { gsKit_clear(gs, GS_SETREG_RGBAQ(0,0,0,0x80,0)); gsKit_sync_flip(gs); }
    return 0;
}
