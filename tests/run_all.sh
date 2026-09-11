#!/usr/bin/env bash
# Runs the WHOLE project suite: Python self-checks, integration tests,
# web client tests (node) and the C reader on the host. Usage: tests/run_all.sh
cd "$(dirname "$0")/.." || exit 1
export PYTHONPATH="$PWD"
PASS=0; FAIL=0; SKIP=0
ok(){   printf '  \033[32m✓\033[0m %s\n' "$1"; PASS=$((PASS+1)); }
bad(){  printf '  \033[31m✗\033[0m %s\n' "$1"; FAIL=$((FAIL+1)); }
skip(){ printf '  \033[33m–\033[0m %s (%s)\n' "$1" "$2"; SKIP=$((SKIP+1)); }
run(){  # run <name> <cmd...>
  local name="$1"; shift
  if out=$("$@" 2>&1); then ok "$name"; else bad "$name"; echo "$out" | tail -12 | sed 's/^/      /'; fi
}

echo "── module self-checks (python -m znt demo)"
if out=$(python3 -m znt demo 2>&1); then
  echo "$out" | grep -c "demo OK" | xargs printf '  \033[32m✓\033[0m %s modules OK\n'; PASS=$((PASS+1))
else bad "znt demo"; echo "$out" | tail -15 | sed 's/^/      /'; fi

echo "── integration tests (python)"
for t in tests/py/test_*.py; do run "$(basename "$t")" python3 "$t"; done

echo "── web client tests (node)"
if command -v node >/dev/null; then
  for t in tests/js/*.test.js; do run "$(basename "$t")" node "$t"; done
else skip "node tests" "node not installed"; fi

echo "── C blob reader (host)"
if command -v cc >/dev/null; then
  TMP=$(mktemp -d)
  PYTHONPATH="$PWD" python3 tests/py/mkblob.py "$TMP"
  if cc -Wall -I ps2 ps2/test_vnp_host.c ps2/vnp.c -o "$TMP/tv" 2>/dev/null; then
    run "vnp.c against a real blob" "$TMP/tv" "$TMP/k.vnp"
  else bad "compile the C reader test"; fi
  if cc -Wall -I ps2 ps2/test_text_host.c ps2/text.c -o "$TMP/tt" 2>/dev/null; then
    run "word wrap (text.c)" "$TMP/tt"
  else bad "compile the text test"; fi
  rm -rf "$TMP"
else skip "C reader" "cc not installed"; fi

echo "── web editor DOM (headless chromium)"
if command -v chromium >/dev/null || command -v google-chrome-stable >/dev/null; then
  run "structure of the rendered UI" python3 tests/browser/dom_check.py
else skip "DOM" "no chromium"; fi

echo "── QA with a real browser (CDP: clicks, keyboard, drag)"
if command -v node >/dev/null && (command -v chromium >/dev/null || command -v google-chrome-stable >/dev/null); then
  run "user flows in VN Studio" node tests/browser/qa.js
else skip "browser QA" "node or chromium missing"; fi

echo "── ISO mastering"
if command -v genisoimage >/dev/null; then
  TMP=$(mktemp -d); printf '\x7fELF' > "$TMP/p.elf"
  printf 'title: T\ncharacter a "A"\nscene s\n  a: h\n  end\n' > "$TMP/h.vn"
  if python3 -m znt iso build "$TMP/h.vn" "$TMP/o.iso" --elf "$TMP/p.elf" >/dev/null 2>&1 \
     && isoinfo -l -i "$TMP/o.iso" 2>/dev/null | grep -q "SYSTEM.CNF"; then ok "znt iso build"
  else bad "znt iso build"; fi
  rm -rf "$TMP"
else skip "ISO" "genisoimage not installed"; fi

echo
printf '\033[1m%d ok, %d failed, %d skipped\033[0m\n' "$PASS" "$FAIL" "$SKIP"
[ "$FAIL" -eq 0 ]
