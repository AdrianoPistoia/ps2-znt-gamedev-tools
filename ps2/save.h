/* The player's saved game. It is written to the memory card, so the format has
 * to survive a truncated file, one from another game or one half-overwritten:
 * hence magic, version and checksum. Packed by hand (no dumping a struct: the
 * padding depends on the compiler). Compiles the same on the host and on the EE. */
#ifndef VNP_SAVE_H
#define VNP_SAVE_H
#include <stdint.h>

#define SAVE_MAGIC   "ZNSV"
#define SAVE_VERSION 1
#define SAVE_SIZE    16          /* magic 4, version 2, scene 2, step 4, bgm 2, crc 2 */

/* Writes SAVE_SIZE bytes into buf. */
void save_pack(uint8_t *buf, uint16_t scene, uint32_t step, uint16_t bgm);

/* Reads a saved game. Returns 0 if usable, -1 if it is short, not ours,
 * from another version or the checksum does not match. */
int save_unpack(const uint8_t *buf, int len, uint16_t *scene, uint32_t *step, uint16_t *bgm);

#endif
