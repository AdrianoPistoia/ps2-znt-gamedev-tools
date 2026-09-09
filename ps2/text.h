/* Corte de líneas del cuadro de diálogo. Fuente monoespaciada: una columna por
 * codepoint. Se compila igual en el host (test) y en el EE. */
#ifndef VNP_TEXT_H
#define VNP_TEXT_H

/* siguiente codepoint UTF-8 en s[*i..len) */
unsigned int text_utf8_next(const char *s, int len, int *i);

/* cuántos codepoints tiene s[0..len) */
int text_utf8_count(const char *s, int len);

typedef struct { const char *s; int len, pos; } TextWrap;

void text_wrap_init(TextWrap *w, const char *s, int len);

/* Toma la proxima linea de hasta `cols` columnas: deja el tramo de bytes en off y n,
 * y devuelve 1, o 0 cuando no queda nada. Corta en el ultimo espacio; una palabra mas
 * larga que la linea se parte. Un salto de linea explicito corta. */
int text_wrap_next(TextWrap *w, int cols, int *off, int *n);

#endif
