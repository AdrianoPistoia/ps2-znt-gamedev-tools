# VN player ELF for PS2. Requires PS2SDK (ps2dev). Build: `make` with $PS2SDK set.
# Output: ZNTVN.ELF  (try it in PCSX2 with Run ELF, or put it in a .iso with `znt iso build --elf`).
EE_BIN = ZNTVN.ELF
EE_OBJS = main.o vnp.o text.o save.o audsrv_irx.o
EE_LIBS = -lgskit -ldmakit -lpad -laudsrv -lmc -lpatches -lc -lkernel
EE_INCS += -I$(PS2SDK)/ports/include -I$(PS2DEV)/gsKit/include
EE_LDFLAGS += -L$(PS2SDK)/ports/lib -L$(PS2DEV)/gsKit/lib

all: $(EE_BIN)

audsrv_irx.c: $(PS2SDK)/iop/irx/audsrv.irx
	bin2c $< $@ audsrv_irx

clean:
	rm -f *.o audsrv_irx.c $(EE_BIN)

# test of the READER on the host (no PS2SDK needed): make -f Makefile host && ./test_vnp <blob.vnp>
host:
	cc -Wall -o test_vnp test_vnp_host.c vnp.c
	cc -Wall -o test_text test_text_host.c text.c
	cc -Wall -o test_save test_save_host.c save.c

include $(PS2SDK)/samples/Makefile.pref
include $(PS2SDK)/samples/Makefile.eeglobal
