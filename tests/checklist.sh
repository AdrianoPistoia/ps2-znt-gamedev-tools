#!/usr/bin/env bash
# Runs the items of docs/checklist.md IN ORDER and stops at the first one that fails.
# Usage: tests/checklist.sh [from]   (e.g. `tests/checklist.sh 4` starts at item 4)
cd "$(dirname "$0")/.." || exit 1
export PYTHONPATH="$PWD"
FROM=${1:-1}; T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export T LOG=/tmp/znt-pcsx2-$USER/PCSX2/logs/emulog.txt
PASS=0
item() {   # item <n> <title> <cmd...>
  local n=$1 title=$2; shift 2
  [ "$n" -lt "$FROM" ] && return 0
  printf '%2d. %s … ' "$n" "$title"
  if out=$("$@" 2>&1); then printf '\033[32m✓\033[0m\n'; PASS=$((PASS+1))
  else printf '\033[31m✗\033[0m\n'; echo "$out" | tail -15 | sed 's/^/      /'
       printf '\n\033[1mStopped at item %d (%d ok before). Resume: tests/checklist.sh %d\033[0m\n' "$n" "$PASS" "$n"; exit 1; fi
}
have() { command -v "$1" >/dev/null || { echo "missing $1"; return 1; }; }

item 1 "VN Studio: full suite (core + web + browser QA, includes groups)"   tests/run_all.sh
item 9 "authoring.md documents every op of the .vn"                   python3 tests/py/test_authoring_doc.py
item 14 "Text: word wrap (host test)"                                 bash -c 'cc -Wall -I ps2 ps2/test_text_host.c ps2/text.c -o "$T/tt" && "$T/tt"'
item 15 "8bpp textures: flat art loses nothing, gradients stay RGBA32"  python3 tests/py/test_quant.py
item 16 "Play: step by step (editor) and as the player"               python3 tests/py/test_playmode.py
item 17 "Save format: magic, version and CRC (host test)"             bash -c 'cc -Wall -I ps2 ps2/test_save_host.c ps2/save.c -o "$T/ts" && "$T/ts"'
# Saving touches the real memory card: savetest mode saves, reads back and compares.
item 18 "Save and load on the memory card (real round trip)"          bash -c '
  python3 tests/py/mkchoice.py "$T/sv" >/dev/null &&
  ZNT_SAVETEST=1 ZNT_AUTOPLAY=1 tests/pcsx2_boot.sh 20 >/dev/null &&
  grep -aq "ZNTVN: savetest OK" "$LOG"'
item 19 "Pause menu and history: drawn without breaking anything"     bash -c '
  ZNT_UI=menu tests/pcsx2_boot.sh 12 >/dev/null && ZNT_UI=log tests/pcsx2_boot.sh 12 >/dev/null'

item 2 "ELF: build with ps2dev (docker)"                              bash -c 'have() { command -v "$1" >/dev/null; }; have docker && ps2/build.sh >/dev/null && test -f ps2/ZNTVN.ELF'
item 3 "ELF: boots in PCSX2 with the demo (host fs)"                  bash -c "python3 -m znt iso build _demo.vn ps2/ZNTVN.VNP >/dev/null && tests/pcsx2_boot.sh 12"
item 4 "Blob v5: header alone in RAM, images/audio on demand"         bash -c "python3 tests/py/test_blob_v5.py && python3 tests/py/mkblob.py '$T' && cc -Wall -I ps2 ps2/test_vnp_host.c ps2/vnp.c -o '$T/tv' && '$T/tv' '$T/k.vnp'"
item 5 "Background fade in the blob"                                  python3 tests/py/test_blob_fade_y.py
item 6 "Tween on y in the blob"                                       python3 tests/py/test_blob_fade_y.py
item 7 "Typing, fade, tween, BGM: the features VN boots and draws"    bash -c "python3 tests/py/mkfeature.py '$T/f' >/dev/null && tests/pcsx2_boot.sh 12 | grep -q 'frame OK'"
item 8 "SE via ADPCM: encoder + the ELF fires it on the SPU2"         bash -c "python3 tests/py/test_adpcm.py && grep -aq 'ZNTVN: se .* channel' /tmp/znt-pcsx2-\$USER/PCSX2/logs/emulog.txt"
# The BGM is a separate thread: if the main starves it or both talk to audsrv, it goes
# mute or hangs without anything else failing. The boot log of item 7 is the only proof.
item 11 "BGM: the thread feeds the PCM stream (does not go mute)"     bash -c "grep -aq 'ZNTVN: bgm playing' /tmp/znt-pcsx2-\$USER/PCSX2/logs/emulog.txt"
# The ISO is the only path a player can use. There the blob is read from the CD, and with
# unaligned stdio that gave 166 KB/s: a 1.1 MB background froze the game for 6.7 s.
item 12 "Bootable ISO: starts from the CD and reads at more than 1 MB/s"  bash -c '
  python3 tests/py/mkfeature.py "$T/iso" >/dev/null &&
  python3 -m znt iso build "$T/iso/f.vn" "$T/g.iso" --elf ps2/ZNTVN.ELF --name ZNTVN >/dev/null &&
  ZNT_ISO="$T/g.iso" tests/pcsx2_boot.sh 30 >/dev/null &&
  kbs=$(grep -a "ZNTVN: io" "$LOG" | tail -1 | sed -E "s/.*\(([0-9]+) KB.*/\1/") &&
  echo "throughput: $kbs KB/s" && [ "${kbs:-0}" -ge 1000 ]'
# Without a joystick there was no way to verify branching: the ELF in autoplay mode
# advances and picks the last option, so the path goes through choice, goto and end.
item 13 "Branching: choice, goto between scenes and end (autoplay)"   bash -c '
  python3 tests/py/mkchoice.py "$T/ch" >/dev/null &&
  ZNT_AUTOPLAY=1 tests/pcsx2_boot.sh 20 >/dev/null &&
  grep -aq "ZNTVN: choice with 2 options" "$LOG" &&
  grep -aq "ZNTVN: choose 1 -> scene" "$LOG" &&
  grep -aq "ZNTVN: end" "$LOG" &&
  test "$(grep -ac "ZNTVN: scene" "$LOG")" -ge 3'
printf '\n\033[1mCHECKLIST COMPLETE: %d items ok\033[0m\n' "$PASS"
