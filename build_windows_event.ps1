param([int]$Jobs = 2)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
# GCC/MinGW-w64, CMake, Ninja and Python must be on PATH.
# Keep the frozen original build/ separate from the event experiment.
cmake -S . -B build-event-windows -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DCMAKE_C_COMPILER=gcc -DCMAKE_CXX_COMPILER=g++
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
cmake --build build-event-windows --parallel $Jobs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
ctest --test-dir build-event-windows --output-on-failure --output-junit windows-tests.xml
exit $LASTEXITCODE
