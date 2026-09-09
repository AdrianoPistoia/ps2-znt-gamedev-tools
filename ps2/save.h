/* Partida guardada del player. Se escribe en la memory card, así que el formato
 * tiene que resistir un archivo truncado, de otro juego o pisado a medias: por eso
 * lleva magic, versión y checksum. Empaquetado a mano (nada de volcar un struct:
 * el padding depende del compilador). Se compila igual en el host y en el EE. */
#ifndef VNP_SAVE_H
#define VNP_SAVE_H
#include <stdint.h>

#define SAVE_MAGIC   "ZNSV"
#define SAVE_VERSION 1
#define SAVE_SIZE    16          /* magic 4, version 2, scene 2, step 4, bgm 2, crc 2 */

/* Escribe SAVE_SIZE bytes en buf. */
void save_pack(uint8_t *buf, uint16_t scene, uint32_t step, uint16_t bgm);

/* Lee una partida. Devuelve 0 si sirve, -1 si está corta, no es nuestra,
 * es de otra versión o el checksum no da. */
int save_unpack(const uint8_t *buf, int len, uint16_t *scene, uint32_t *step, uint16_t *bgm);

#endif
