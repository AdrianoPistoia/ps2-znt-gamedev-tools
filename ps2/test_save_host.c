/* Test en host del formato de partida. `cc -I ps2 ps2/test_save_host.c ps2/save.c` */
#include <stdio.h>
#include <string.h>
#include "save.h"

static int fails = 0;
#define CHECK(c) do { if(!(c)){ printf("FAIL linea %d: %s\n", __LINE__, #c); fails++; } } while(0)

int main(void)
{
    uint8_t buf[SAVE_SIZE];
    uint16_t sc, bgm; uint32_t st;

    /* ida y vuelta */
    save_pack(buf, 3, 17, 2);
    CHECK(save_unpack(buf, sizeof(buf), &sc, &st, &bgm) == 0);
    CHECK(sc == 3 && st == 17 && bgm == 2);

    /* sin BGM y en el arranque */
    save_pack(buf, 0, 0, 0xFFFF);
    CHECK(save_unpack(buf, sizeof(buf), &sc, &st, &bgm) == 0 && sc == 0 && st == 0 && bgm == 0xFFFF);

    /* valores grandes: la escena entra en u16 y el paso en u32 */
    save_pack(buf, 65535, 4000000000u, 0);
    CHECK(save_unpack(buf, sizeof(buf), &sc, &st, &bgm) == 0 && sc == 65535 && st == 4000000000u);

    /* archivo corto: no se acepta */
    save_pack(buf, 1, 1, 1);
    CHECK(save_unpack(buf, SAVE_SIZE - 1, &sc, &st, &bgm) == -1);
    CHECK(save_unpack(buf, 0, &sc, &st, &bgm) == -1);

    /* de otro juego */
    save_pack(buf, 1, 1, 1); memcpy(buf, "XXXX", 4);
    CHECK(save_unpack(buf, sizeof(buf), &sc, &st, &bgm) == -1);

    /* de otra versión */
    save_pack(buf, 1, 1, 1); buf[4] = 99;
    CHECK(save_unpack(buf, sizeof(buf), &sc, &st, &bgm) == -1);

    /* pisado a medias: cualquier byte que cambie rompe el checksum */
    for (int i = 6; i < SAVE_SIZE - 2; i++) {
        save_pack(buf, 7, 9, 1); buf[i] ^= 0xFF;
        CHECK(save_unpack(buf, sizeof(buf), &sc, &st, &bgm) == -1);
    }

    /* el formato no cambia de tamaño sin querer */
    CHECK(SAVE_SIZE == 16);

    printf(fails ? "%d CHECKS FALLARON\n" : "SAVE OK\n", fails);
    return fails ? 1 : 0;
}
