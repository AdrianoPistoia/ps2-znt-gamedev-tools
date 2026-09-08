#!/usr/bin/env bash
# Compila ZNTVN.ELF con la imagen ps2dev (docker). Uso: ps2/build.sh [make args]
cd "$(dirname "$0")" || exit 1
DOCKER=docker; docker info >/dev/null 2>&1 || DOCKER="sudo docker"
exec $DOCKER run --rm -v "$PWD:/src" -w /src ps2dev/ps2dev sh -c "apk add -q make >/dev/null 2>&1; make $*; chown -R $(id -u):$(id -g) /src"
