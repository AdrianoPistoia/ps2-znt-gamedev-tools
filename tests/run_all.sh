#!/usr/bin/env bash
# Corre TODA la suite del proyecto: self-checks de Python, tests de integración,
# tests del cliente web (node) y el lector C en host. Uso: tests/run_all.sh
cd "$(dirname "$0")/.." || exit 1
export PYTHONPATH="$PWD"
PASS=0; FAIL=0; SKIP=0
ok(){   printf '  \033[32m✓\033[0m %s\n' "$1"; PASS=$((PASS+1)); }
bad(){  printf '  \033[31m✗\033[0m %s\n' "$1"; FAIL=$((FAIL+1)); }
skip(){ printf '  \033[33m–\033[0m %s (%s)\n' "$1" "$2"; SKIP=$((SKIP+1)); }
run(){  # run <nombre> <cmd...>
  local name="$1"; shift
  if out=$("$@" 2>&1); then ok "$name"; else bad "$name"; echo "$out" | tail -12 | sed 's/^/      /'; fi
}

echo "── self-checks de los módulos (python -m znt demo)"
if out=$(python3 -m znt demo 2>&1); then
  echo "$out" | grep -c "demo OK" | xargs printf '  \033[32m✓\033[0m %s módulos OK\n'; PASS=$((PASS+1))
else bad "znt demo"; echo "$out" | tail -15 | sed 's/^/      /'; fi

echo "── tests de integración (python)"
for t in tests/py/test_*.py; do run "$(basename "$t")" python3 "$t"; done

echo "── tests del cliente web (node)"
if command -v node >/dev/null; then
  for t in tests/js/*.test.js; do run "$(basename "$t")" node "$t"; done
else skip "tests node" "node no instalado"; fi

echo "── lector del blob en C (host)"
if command -v cc >/dev/null; then
  TMP=$(mktemp -d)
  python3 - "$TMP" <<'PY'
import sys
from znt import vn, vniso, psf
m = vn._link_choices(vn.parse(
    'title: T\ncharacter a "Ana" color=#e79ab0\n'
    'scene uno\n  bg grad:#101828,#304060\n  show a right x=40 z=5 zoom=150 opacity=80\n'
    '  a: Hola.\n  choice\n    - Seguir -> dos\n    - Fin -> dos\n'
    'scene dos\n  * chau\n  bgm t.wav\n  end\n'))
open(sys.argv[1] + "/t.wav", "wb").write(b"RIFFxxxxWAVE")
open(sys.argv[1] + "/k.vnp", "wb").write(vniso.compile_blob(m, base=sys.argv[1], font=psf.find_default()))
PY
  if cc -Wall -I ps2 ps2/test_vnp_host.c ps2/vnp.c -o "$TMP/tv" 2>/dev/null; then
    run "vnp.c contra un blob real" "$TMP/tv" "$TMP/k.vnp"
  else bad "compilar el test del lector C"; fi
  rm -rf "$TMP"
else skip "lector C" "cc no instalado"; fi

echo "── DOM del editor web (chromium headless)"
if command -v chromium >/dev/null || command -v google-chrome-stable >/dev/null; then
  run "estructura de la UI ya renderizada" python3 tests/browser/dom_check.py
else skip "DOM" "no hay chromium"; fi

echo "── masterizado de ISO"
if command -v genisoimage >/dev/null; then
  TMP=$(mktemp -d); printf '\x7fELF' > "$TMP/p.elf"
  printf 'title: T\ncharacter a "A"\nscene s\n  a: h\n  end\n' > "$TMP/h.vn"
  if python3 -m znt iso build "$TMP/h.vn" "$TMP/o.iso" --elf "$TMP/p.elf" >/dev/null 2>&1 \
     && isoinfo -l -i "$TMP/o.iso" 2>/dev/null | grep -q "SYSTEM.CNF"; then ok "znt iso build"
  else bad "znt iso build"; fi
  rm -rf "$TMP"
else skip "ISO" "genisoimage no instalado"; fi

echo
printf '\033[1m%d ok, %d fallan, %d omitidos\033[0m\n' "$PASS" "$FAIL" "$SKIP"
[ "$FAIL" -eq 0 ]
