/* Test en host del corte de líneas (ps2/text.c). `cc -I ps2 ps2/test_text_host.c ps2/text.c` */
#include <stdio.h>
#include <string.h>
#include "text.h"

static int fails = 0;
#define CHECK(c) do { if(!(c)){ printf("FAIL linea %d: %s\n", __LINE__, #c); fails++; } } while(0)

/* corta `s` en líneas de `cols` y las junta con '|' para comparar de un vistazo */
static const char *lines(const char *s, int cols)
{
    static char out[256]; out[0] = 0;
    TextWrap w; text_wrap_init(&w, s, strlen(s));
    int off, n, first = 1;
    while (text_wrap_next(&w, cols, &off, &n)) {
        if (!first) strcat(out, "|");
        strncat(out, s + off, n); first = 0;
    }
    return out;
}

int main(void)
{
    CHECK(!strcmp(lines("hola mundo", 10), "hola mundo"));
    CHECK(!strcmp(lines("hola mundo", 5), "hola|mundo"));
    CHECK(!strcmp(lines("hola mundo", 6), "hola|mundo"));      /* no parte "mundo" */
    CHECK(!strcmp(lines("abcdefghij", 4), "abcd|efgh|ij"));    /* palabra sola: se parte */
    CHECK(!strcmp(lines("ab cdefghij", 4), "ab|cdef|ghij"));
    CHECK(!strcmp(lines("uno dos tres", 8), "uno dos|tres"));
    CHECK(!strcmp(lines("a\nb", 10), "a|b"));                  /* salto explícito */
    CHECK(!strcmp(lines("uno\ndos tres", 20), "uno|dos tres"));
    CHECK(!strcmp(lines("hola   mundo", 5), "hola|mundo"));    /* espacios de más */
    CHECK(!strcmp(lines("", 10), ""));
    CHECK(!strcmp(lines("   ", 10), ""));
    CHECK(!strcmp(lines("a\n\nb", 10), "a||b"));         /* renglon vacio: se respeta */

    /* UTF-8: las columnas cuentan codepoints, no bytes */
    CHECK(text_utf8_count("ñandú", strlen("ñandú")) == 5);
    CHECK(!strcmp(lines("ñandú corre", 5), "ñandú|corre"));
    CHECK(!strcmp(lines("áéíóú", 2), "áé|íó|ú"));

    /* el diálogo real que se veía cortado a mitad de palabra */
    CHECK(!strcmp(lines("Tipeo, crossfade, tween en x e y, BGM y SE. Todo junto.", 30),
                  "Tipeo, crossfade, tween en x e|y, BGM y SE. Todo junto."));

    printf(fails ? "%d CHECKS FALLARON\n" : "TEXT OK\n", fails);
    return fails ? 1 : 0;
}
