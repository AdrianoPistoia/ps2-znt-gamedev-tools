#!/usr/bin/env bash
# Boots ps2/ZNTVN.ELF in PCSX2 (host fs) with ps2/ZNTVN.VNP next to it and checks in the
# EE log that the player opened the blob and drew a frame. Usage: tests/pcsx2_boot.sh [seconds]
# Does not touch the user's config: uses its own datapath with the BIOS symlinked.
cd "$(dirname "$0")/.." || exit 1
SECS=${1:-20}
DP=${ZNT_PCSX2_DATA:-/tmp/znt-pcsx2-$USER}
SRC=~/.config/PCSX2
[ -f ps2/ZNTVN.ELF ] || { echo "missing ps2/ZNTVN.ELF (ps2/build.sh)"; exit 1; }
[ -f ps2/ZNTVN.VNP ] || { echo "missing ps2/ZNTVN.VNP (python3 -m znt iso build x.vn ps2/ZNTVN.VNP)"; exit 1; }
# ZNT_ISO=x.iso boots that ISO (reads the blob from the CD, not the host: the real path)
if [ -n "$ZNT_ISO" ]; then BOOT=(-fastboot "$ZNT_ISO"); else BOOT=(-elf "$PWD/ps2/ZNTVN.ELF"); fi
# ZNT_AUTOPLAY=1: the player advances and chooses on its own, to verify choice/goto/end without a joystick
ARGS=""
[ -n "$ZNT_AUTOPLAY" ] && ARGS="$ARGS autoplay"
[ -n "$ZNT_SAVETEST" ] && ARGS="$ARGS savetest"     # saves to the memory card, reads it back and verifies
[ -n "$ZNT_UI" ] && ARGS="$ARGS $ZNT_UI"            # menu | log: opens that screen to photograph it
[ -n "$ARGS" ] && BOOT+=(-gameargs "${ARGS# }")
command -v pcsx2-qt >/dev/null || { echo "missing pcsx2-qt"; exit 1; }
rm -rf "$DP"; mkdir -p "$DP/PCSX2/inis" "$DP/PCSX2/logs"      # -datapath X uses X/PCSX2
ln -s "$SRC/bios" "$DP/PCSX2/bios"
sed -e 's/^EnableEEConsole *=.*/EnableEEConsole = true/' -e 's/^EnableFileLogging *=.*/EnableFileLogging = true/' -e 's/^EnableIOPConsole *=.*/EnableIOPConsole = true/' \
    -e 's/^HostFs *=.*/HostFs = true/' -e 's/^ConfirmShutdown *=.*/ConfirmShutdown = false/' \
    "$SRC/inis/PCSX2.ini" > "$DP/PCSX2/inis/PCSX2.ini"
if [ -n "$ZNT_SHOT" ]; then     # ZNT_SHOT=out.png: with a window, capture with grim (Hyprland) at SECS-4 s
  timeout -s INT "$SECS" pcsx2-qt -datapath "$DP" -batch "${BOOT[@]}" >/dev/null 2>&1 &
  for i in $(seq 1 20); do   # wait for the window
    A=$(hyprctl clients -j 2>/dev/null | jq -r '.[] | select(.class|test("pcsx2";"i")) | .address' | head -1)
    [ -n "$A" ] && break; sleep 0.5
  done
  if [ -n "$A" ]; then      # floating and 4:3: landscape in the tiling layout, PCSX2 crops the frame (hyprctl Lua)
    hyprctl dispatch "hl.dsp.window.float({ action = 'on', window = 'address:$A' })" >/dev/null
    hyprctl dispatch "hl.dsp.window.resize({ x = 964, y = 780, window = 'address:$A' })" >/dev/null
  fi
  sleep $((SECS - 6))
  G=$(hyprctl clients -j 2>/dev/null | jq -r '.[] | select(.class|test("pcsx2";"i")) | "\(.at[0]),\(.at[1]) \(.size[0])x\(.size[1])"' | head -1)
  [ -n "$G" ] && grim -g "$G" "$ZNT_SHOT" && echo "screenshot: $ZNT_SHOT"
  wait
else
  timeout -s INT "$SECS" pcsx2-qt -datapath "$DP" -batch -nogui "${BOOT[@]}" >/dev/null 2>&1
fi
LOG="$DP/PCSX2/logs/emulog.txt"
grep -a "ZNTVN:" "$LOG" | tail -5
grep -aq "ZNTVN: frame OK" "$LOG" && { echo "PCSX2 BOOT OK"; exit 0; }
echo "PCSX2 BOOT FAILED (see $LOG)"; grep -a -iE "vnp|error|exception|invalid" "$LOG" | tail -10; exit 1
