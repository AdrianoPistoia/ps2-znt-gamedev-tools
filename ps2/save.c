/* Saved-game format. See save.h. */
#include "save.h"
#include <string.h>

/* CRC-16/CCITT: cheap and catches the ugly memory-card case, a file
 * half-overwritten by a power cut. */
static uint16_t crc16(const uint8_t *p, int n)
{
    uint16_t c = 0xFFFF;
    for (int i = 0; i < n; i++) {
        c ^= (uint16_t)p[i] << 8;
        for (int b = 0; b < 8; b++)
            c = (c & 0x8000) ? (uint16_t)((c << 1) ^ 0x1021) : (uint16_t)(c << 1);
    }
    return c;
}

static void put16(uint8_t *p, uint16_t v) { p[0] = v & 0xFF; p[1] = v >> 8; }
static void put32(uint8_t *p, uint32_t v) { p[0] = v; p[1] = v >> 8; p[2] = v >> 16; p[3] = v >> 24; }
static uint16_t get16(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }
static uint32_t get32(const uint8_t *p) { return p[0] | (p[1] << 8) | (p[2] << 16) | ((uint32_t)p[3] << 24); }

void save_pack(uint8_t *buf, uint16_t scene, uint32_t step, uint16_t bgm)
{
    memcpy(buf, SAVE_MAGIC, 4);
    put16(buf + 4, SAVE_VERSION);
    put16(buf + 6, scene);
    put32(buf + 8, step);
    put16(buf + 12, bgm);
    put16(buf + 14, crc16(buf, SAVE_SIZE - 2));
}

int save_unpack(const uint8_t *buf, int len, uint16_t *scene, uint32_t *step, uint16_t *bgm)
{
    if (len < SAVE_SIZE) return -1;
    if (memcmp(buf, SAVE_MAGIC, 4)) return -1;
    if (get16(buf + 4) != SAVE_VERSION) return -1;
    if (get16(buf + 14) != crc16(buf, SAVE_SIZE - 2)) return -1;
    *scene = get16(buf + 6);
    *step  = get32(buf + 8);
    *bgm   = get16(buf + 12);
    return 0;
}
