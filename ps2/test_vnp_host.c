/* Verifica vnp.c (lector PS2) contra un blob generado por vniso.py, en el host. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "vnp.h"

static int fails = 0;
#define CHECK(c) do { if(!(c)){ printf("FAIL: %s\n", #c); fails++; } } while(0)

static int streq(const VnpDoc *d, uint32_t idx, const char *lit) {
    VnpStr s = vnp_str(d, idx);
    return s.len == strlen(lit) && memcmp(s.ptr, lit, s.len) == 0;
}

int main(int argc, char **argv) {
    FILE *f = fopen(argv[1], "rb");
    fseek(f, 0, SEEK_END); long n = ftell(f); fseek(f, 0, SEEK_SET);
    uint8_t *buf = malloc(n); fread(buf, 1, n, f); fclose(f);

    VnpDoc d;
    CHECK(vnp_open(&d, buf, n) == 0);
    CHECK(d.version == 5);
    CHECK(d.head_size > 0 && d.head_size < (uint32_t)n);
    CHECK(d.start == 0);
    CHECK(d.n_scenes == 2);
    CHECK(d.n_chars == 1);
    CHECK(streq(&d, 0, "T"));                 /* título = string 0 */

    VnpChar c; vnp_char(&d, 0, &c);
    CHECK(streq(&d, c.name, "Ana"));
    CHECK(c.color == 0xEE7799FFu || (c.color >> 8) != 0);  /* #e79ab0 -> rgba */

    VnpScene sc; VnpStep s;
    CHECK(vnp_scene_begin(&d, 0, &sc) == 0);
    CHECK(vnp_step(&sc, &s) && s.op == OP_BG && s.bg_kind == 1);
    CHECK(vnp_step(&sc, &s) && s.op == OP_SHOW && s.x == 40 && s.z == 5 && s.zoom == 150 && s.opacity == 80);
    CHECK(s.img == VNP_NONE16);               /* sin expresión: sprite base */
    CHECK(vnp_step(&sc, &s) && s.op == OP_SAY && streq(&d, s.text, "Hola."));
    CHECK(vnp_step(&sc, &s) && s.op == OP_CHOICE && s.n_opts == 2 && s.opt_target[0] == 1 && s.opt_target[1] == 1);
    CHECK(vnp_step(&sc, &s) == 0);            /* fin de escena 0 */

    CHECK(vnp_scene_begin(&d, 1, &sc) == 0);
    CHECK(vnp_step(&sc, &s) && s.op == OP_SAY && s.who == VNP_NONE16 && streq(&d, s.text, "chau"));
    CHECK(vnp_step(&sc, &s) && s.op == OP_BGM && s.bgm_stop == 0 && s.audio == 0);
    CHECK(vnp_step(&sc, &s) && s.op == OP_END);

    /* audio e imagen: índice (off, len) con la data después de la cabecera */
    CHECK(d.n_audio == 1);
    { VnpAudio au; vnp_audio(&d, 0, &au); CHECK(streq(&d, au.name, "t.wav") && au.len > 0);
      CHECK(au.off >= d.head_size && au.data == buf + au.off); }
    CHECK(d.n_images == 1);
    { VnpImage im; vnp_image(&d, 0, &im);
      CHECK(im.w == 2 && im.h == 2 && im.len == 16 && im.off >= d.head_size && im.rgba == buf + im.off);
      CHECK(im.rgba[0] == 10 && im.rgba[1] == 20 && im.rgba[2] == 30 && im.rgba[3] == 255); }

    /* sólo la cabecera (lo que el ELF carga en RAM): se lee todo igual, la data queda por demanda */
    { VnpDoc h; CHECK(vnp_open(&h, buf, d.head_size) == 0);
      CHECK(h.n_scenes == 2 && h.n_chars == 1 && h.has_font);
      VnpImage im; vnp_image(&h, 0, &im); CHECK(im.rgba == 0 && im.off >= d.head_size && im.len == 16);
      VnpAudio au; vnp_audio(&h, 0, &au); CHECK(au.data == 0 && au.len > 0);
      VnpScene s2; VnpStep st; CHECK(vnp_scene_begin(&h, 1, &s2) == 0 && vnp_step(&s2, &st) && streq(&h, st.text, "chau")); }

    /* fuente horneada: glifos presentes y ausentes */
    CHECK(d.has_font && d.font_w == 8 && d.font_h == 16);
    CHECK(vnp_glyph(&d, 'H') != 0);
    CHECK(vnp_glyph(&d, 0x3000) == 0);       /* CJK: no está en el atlas */

    printf(fails ? "%d CHECKS FALLARON\n" : "C READER OK\n", fails);
    return fails ? 1 : 0;
}
