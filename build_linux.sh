#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
[[ $(uname -s) == Linux && $(uname -m) == x86_64 ]] || {
  echo 'Linux x86-64 is required' >&2; exit 1;
}
cmake -S . -B build-linux -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON "$@"
cmake --build build-linux --parallel "${CMAKE_BUILD_PARALLEL_LEVEL:-2}"
./build-linux/platform_probe_tests | tee build-linux/platform.json
ctest --test-dir build-linux --output-on-failure --output-junit tests.xml
