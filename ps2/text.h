/* Line wrapping for the dialogue box. Monospaced font: one column per
 * codepoint. Compiles the same on the host (test) and on the EE. */
#ifndef VNP_TEXT_H
#define VNP_TEXT_H

/* next UTF-8 codepoint in s[*i..len) */
unsigned int text_utf8_next(const char *s, int len, int *i);

/* how many codepoints s[0..len) has */
int text_utf8_count(const char *s, int len);

typedef struct { const char *s; int len, pos; } TextWrap;

void text_wrap_init(TextWrap *w, const char *s, int len);

/* Takes the next line of up to `cols` columns: leaves the byte span in off and n,
 * and returns 1, or 0 when nothing is left. Breaks at the last space; a word longer
 * than the line gets split. An explicit newline breaks. */
int text_wrap_next(TextWrap *w, int cols, int *off, int *n);

#endif
