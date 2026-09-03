# ELF player VN para PS2. Requiere PS2SDK (ps2dev). Build: `make` con $PS2SDK seteado.
# Salida: ZNTVN.ELF  (probar en PCSX2 con Run ELF, o meter en un .iso con `znt iso build --elf`).
EE_BIN = ZNTVN.ELF
EE_OBJS = main.o vnp.o
EE_LIBS = -lgskit -ldmakit -lpad -laudsrv -lpatches -lc -lkernel
EE_INCS += -I$(PS2SDK)/ports/include
EE_LDFLAGS += -L$(PS2SDK)/ports/lib

all: $(EE_BIN)

clean:
	rm -f *.o $(EE_BIN)

# test del LECTOR en el host (no necesita PS2SDK): make -f Makefile host && ./test_vnp <blob.vnp>
host:
	cc -Wall -o test_vnp test_vnp_host.c vnp.c

include $(PS2SDK)/samples/Makefile.pref
include $(PS2SDK)/samples/Makefile.eeglobal
