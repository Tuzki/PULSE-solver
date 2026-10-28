#!/bin/sh
set -eu
PULSE_BUILD_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PULSE_CMAKE_BIN=${PULSE_CMAKE:-$(command -v cmake || true)}
PULSE_NINJA_BIN=${PULSE_NINJA:-$(command -v ninja || true)}
if [ -z "$PULSE_CMAKE_BIN" ]; then
 PULSE_CMAKE_BIN=/Users/tuzki/Documents/Codex/pulse-solver-v1/.build_tools/cmake/data/bin/cmake
fi
if [ -z "$PULSE_NINJA_BIN" ]; then
 PULSE_NINJA_BIN=/Users/tuzki/Documents/Codex/pulse-solver-v1/.build_tools/bin/ninja
fi
"$PULSE_CMAKE_BIN" -S "$PULSE_BUILD_ROOT" -B "$PULSE_BUILD_ROOT/build" -G Ninja \
 -DCMAKE_BUILD_TYPE=Release -DCMAKE_MAKE_PROGRAM="$PULSE_NINJA_BIN"
"$PULSE_CMAKE_BIN" --build "$PULSE_BUILD_ROOT/build" --parallel 3
