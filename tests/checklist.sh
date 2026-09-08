#!/usr/bin/env bash
# Corre los ítems de docs/checklist.md EN ORDEN y se frena en el primero que falla.
# Uso: tests/checklist.sh [desde]   (p.ej. `tests/checklist.sh 4` arranca en el ítem 4)
cd "$(dirname "$0")/.." || exit 1
export PYTHONPATH="$PWD"
FROM=${1:-1}; T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
PASS=0
item() {   # item <n> <título> <cmd...>
  local n=$1 title=$2; shift 2
  [ "$n" -lt "$FROM" ] && return 0
  printf '%2d. %s … ' "$n" "$title"
  if out=$("$@" 2>&1); then printf '\033[32m✓\033[0m\n'; PASS=$((PASS+1))
  else printf '\033[31m✗\033[0m\n'; echo "$out" | tail -15 | sed 's/^/      /'
       printf '\n\033[1mSe frenó en el ítem %d (%d ok antes). Reanudar: tests/checklist.sh %d\033[0m\n' "$n" "$PASS" "$n"; exit 1; fi
}
have() { command -v "$1" >/dev/null || { echo "falta $1"; return 1; }; }

item 1 "VN Studio: suite completa (core + web + QA de browser, incluye grupos)" tests/run_all.sh
item 9 "authoring.md documenta todas las ops del .vn"                 python3 tests/py/test_authoring_doc.py
item 2 "ELF: build con ps2dev (docker)"                                bash -c 'have() { command -v "$1" >/dev/null; }; have docker && ps2/build.sh >/dev/null && test -f ps2/ZNTVN.ELF'
item 3 "ELF: bootea en PCSX2 con la demo (host fs)"                    bash -c "python3 -m znt iso build _demo.vn ps2/ZNTVN.VNP >/dev/null && tests/pcsx2_boot.sh 12"
item 4 "Blob v5: cabecera sola en RAM, imágenes/audio por demanda"     bash -c "python3 tests/py/test_blob_v5.py && python3 tests/py/mkblob.py '$T' && cc -Wall -I ps2 ps2/test_vnp_host.c ps2/vnp.c -o '$T/tv' && '$T/tv' '$T/k.vnp'"
item 5 "Fade de fondo en el blob"                                      python3 tests/py/test_blob_fade_y.py
item 6 "Tween en y en el blob"                                         python3 tests/py/test_blob_fade_y.py
item 7 "Tipeo, fade, tween, BGM: la VN de features bootea y dibuja"    bash -c "python3 tests/py/mkfeature.py '$T/f' >/dev/null && tests/pcsx2_boot.sh 12 | grep -q 'frame OK'"
item 8 "SE por ADPCM: encoder + el ELF lo dispara en la SPU2"          bash -c "python3 tests/py/test_adpcm.py && grep -aq 'ZNTVN: se .* canal' /tmp/znt-pcsx2-\$USER/PCSX2/logs/emulog.txt"
# El BGM es un thread aparte: si el main lo starvea o los dos hablan con audsrv, queda
# mudo o cuelga sin que nada más falle. El log del boot del ítem 7 es la única prueba.
item 11 "BGM: el thread alimenta el stream PCM (no queda mudo)"        bash -c "grep -aq 'ZNTVN: bgm suena' /tmp/znt-pcsx2-\$USER/PCSX2/logs/emulog.txt"
printf '\n\033[1mCHECKLIST COMPLETO: %d ítems ok\033[0m\n' "$PASS"
