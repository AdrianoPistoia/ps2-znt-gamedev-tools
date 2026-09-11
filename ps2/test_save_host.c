/* Host test of the saved-game format. `cc -I ps2 ps2/test_save_host.c ps2/save.c` */
#include <stdio.h>
#include <string.h>
#include "save.h"

static int fails = 0;
#define CHECK(c) do { if(!(c)){ printf("FAIL line %d: %s\n", __LINE__, #c); fails++; } } while(0)

int main(void)
{
    uint8_t buf[SAVE_SIZE];
    uint16_t sc, bgm; uint32_t st;

    /* round trip */
    save_pack(buf, 3, 17, 2);
    CHECK(save_unpack(buf, sizeof(buf), &sc, &st, &bgm) == 0);
    CHECK(sc == 3 && st == 17 && bgm == 2);

    /* no BGM and at the start */
    save_pack(buf, 0, 0, 0xFFFF);
    CHECK(save_unpack(buf, sizeof(buf), &sc, &st, &bgm) == 0 && sc == 0 && st == 0 && bgm == 0xFFFF);

    /* large values: the scene fits in u16 and the step in u32 */
    save_pack(buf, 65535, 4000000000u, 0);
    CHECK(save_unpack(buf, sizeof(buf), &sc, &st, &bgm) == 0 && sc == 65535 && st == 4000000000u);

    /* short file: rejected */
    save_pack(buf, 1, 1, 1);
    CHECK(save_unpack(buf, SAVE_SIZE - 1, &sc, &st, &bgm) == -1);
    CHECK(save_unpack(buf, 0, &sc, &st, &bgm) == -1);

    /* from another game */
    save_pack(buf, 1, 1, 1); memcpy(buf, "XXXX", 4);
    CHECK(save_unpack(buf, sizeof(buf), &sc, &st, &bgm) == -1);

    /* from another version */
    save_pack(buf, 1, 1, 1); buf[4] = 99;
    CHECK(save_unpack(buf, sizeof(buf), &sc, &st, &bgm) == -1);

    /* half-overwritten: any byte that changes breaks the checksum */
    for (int i = 6; i < SAVE_SIZE - 2; i++) {
        save_pack(buf, 7, 9, 1); buf[i] ^= 0xFF;
        CHECK(save_unpack(buf, sizeof(buf), &sc, &st, &bgm) == -1);
    }

    /* the format does not change size by accident */
    CHECK(SAVE_SIZE == 16);

    printf(fails ? "%d CHECKS FAILED\n" : "SAVE OK\n", fails);
    return fails ? 1 : 0;
}
