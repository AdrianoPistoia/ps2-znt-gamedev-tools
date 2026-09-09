/* Corte de líneas del cuadro de diálogo. Ver text.h. Sólo stdlib mínima. */
#include "text.h"

unsigned int text_utf8_next(const char *s, int len, int *i)
{
    unsigned char c = s[*i]; (*i)++;
    if (c < 0x80) return c;
    if ((c >> 5) == 6 && *i < len)     { unsigned int r = (c & 0x1F) << 6 | (s[*i] & 0x3F); (*i)++; return r; }
    if ((c >> 4) == 14 && *i + 1 < len) { unsigned int r = (c & 0x0F) << 12 | (s[*i] & 0x3F) << 6 | (s[*i+1] & 0x3F); *i += 2; return r; }
    if (*i + 2 < len) { unsigned int r = (c & 0x07) << 18 | (s[*i] & 0x3F) << 12 | (s[*i+1] & 0x3F) << 6 | (s[*i+2] & 0x3F); *i += 3; return r; }
    return '?';
}

int text_utf8_count(const char *s, int len)
{
    int i = 0, n = 0;
    while (i < len) { text_utf8_next(s, len, &i); n++; }
    return n;
}

void text_wrap_init(TextWrap *w, const char *s, int len)
{
    w->s = s; w->len = len; w->pos = 0;
}

int text_wrap_next(TextWrap *w, int cols, int *off, int *n)
{
    const char *s = w->s;
    while (w->pos < w->len && s[w->pos] == ' ') w->pos++;      /* la línea no empieza con espacios */
    if (w->pos >= w->len) return 0;

    int start = w->pos, i = w->pos, taken = 0, last_space = -1;
    while (i < w->len && taken < cols) {
        if (s[i] == '\n') break;
        int j = i;
        unsigned int cp = text_utf8_next(s, w->len, &j);
        if (cp == ' ') last_space = i;
        i = j; taken++;
    }

    int end;
    if (i < w->len && s[i] == '\n') { end = i; w->pos = i + 1; }   /* salto explícito */
    else if (i >= w->len)           { end = i; w->pos = i; }       /* último renglón */
    else if (s[i] == ' ')           { end = i; w->pos = i; }       /* justo terminó una palabra */
    else if (last_space >= 0)       { end = last_space; w->pos = last_space; }  /* volver al espacio */
    else                            { end = i; w->pos = i; }       /* palabra más larga que el renglón */

    while (end > start && s[end - 1] == ' ') end--;                /* sin espacios colgando */
    *off = start; *n = end - start;
    return 1;
}
