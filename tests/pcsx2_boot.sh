#!/usr/bin/env bash
# Bootea ps2/ZNTVN.ELF en PCSX2 (host fs) con ps2/ZNTVN.VNP al lado y verifica en el
# log del EE que el player abrió el blob y dibujó un frame. Uso: tests/pcsx2_boot.sh [segundos]
# No toca la config del usuario: usa un datapath propio con la BIOS enlazada.
cd "$(dirname "$0")/.." || exit 1
SECS=${1:-20}
DP=${ZNT_PCSX2_DATA:-/tmp/znt-pcsx2-$USER}
SRC=~/.config/PCSX2
[ -f ps2/ZNTVN.ELF ] || { echo "falta ps2/ZNTVN.ELF (ps2/build.sh)"; exit 1; }
[ -f ps2/ZNTVN.VNP ] || { echo "falta ps2/ZNTVN.VNP (python3 -m znt iso build x.vn ps2/ZNTVN.VNP)"; exit 1; }
# ZNT_ISO=x.iso bootea ese ISO (lee el blob del CD, no del host: el camino real)
if [ -n "$ZNT_ISO" ]; then BOOT=(-fastboot "$ZNT_ISO"); else BOOT=(-elf "$PWD/ps2/ZNTVN.ELF"); fi
command -v pcsx2-qt >/dev/null || { echo "falta pcsx2-qt"; exit 1; }
rm -rf "$DP"; mkdir -p "$DP/PCSX2/inis" "$DP/PCSX2/logs"      # -datapath X usa X/PCSX2
ln -s "$SRC/bios" "$DP/PCSX2/bios"
sed -e 's/^EnableEEConsole *=.*/EnableEEConsole = true/' -e 's/^EnableFileLogging *=.*/EnableFileLogging = true/' -e 's/^EnableIOPConsole *=.*/EnableIOPConsole = true/' \
    -e 's/^HostFs *=.*/HostFs = true/' -e 's/^ConfirmShutdown *=.*/ConfirmShutdown = false/' \
    "$SRC/inis/PCSX2.ini" > "$DP/PCSX2/inis/PCSX2.ini"
if [ -n "$ZNT_SHOT" ]; then     # ZNT_SHOT=salida.png: con ventana, captura con grim (Hyprland) a los SECS-4 s
  timeout -s INT "$SECS" pcsx2-qt -datapath "$DP" -batch "${BOOT[@]}" >/dev/null 2>&1 &
  for i in $(seq 1 20); do   # esperar la ventana
    A=$(hyprctl clients -j 2>/dev/null | jq -r '.[] | select(.class|test("pcsx2";"i")) | .address' | head -1)
    [ -n "$A" ] && break; sleep 0.5
  done
  if [ -n "$A" ]; then      # flotante y 4:3: apaisada en la tiling, PCSX2 recorta el frame (hyprctl Lua)
    hyprctl dispatch "hl.dsp.window.float({ action = 'on', window = 'address:$A' })" >/dev/null
    hyprctl dispatch "hl.dsp.window.resize({ x = 964, y = 780, window = 'address:$A' })" >/dev/null
  fi
  sleep $((SECS - 6))
  G=$(hyprctl clients -j 2>/dev/null | jq -r '.[] | select(.class|test("pcsx2";"i")) | "\(.at[0]),\(.at[1]) \(.size[0])x\(.size[1])"' | head -1)
  [ -n "$G" ] && grim -g "$G" "$ZNT_SHOT" && echo "captura: $ZNT_SHOT"
  wait
else
  timeout -s INT "$SECS" pcsx2-qt -datapath "$DP" -batch -nogui "${BOOT[@]}" >/dev/null 2>&1
fi
LOG="$DP/PCSX2/logs/emulog.txt"
grep -a "ZNTVN:" "$LOG" | tail -5
grep -aq "ZNTVN: frame OK" "$LOG" && { echo "PCSX2 BOOT OK"; exit 0; }
echo "PCSX2 BOOT FALLÓ (ver $LOG)"; grep -a -iE "vnp|error|exception|invalid" "$LOG" | tail -10; exit 1
