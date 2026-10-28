param([int]$Jobs = 3)
$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$taskTools = 'D:\codex\tool\pulse-win'
$env:PATH = "$taskTools\w64devkit\bin;$taskTools\python\cmake\data\bin;" + $env:PATH
$taskCmake = "$taskTools\python\cmake\data\bin\cmake.exe"
& $taskCmake -S $taskRoot -B "$taskRoot\build" -G Ninja -DCMAKE_BUILD_TYPE=Release "-DPython3_EXECUTABLE=C:/Users/49605/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe" "-DCMAKE_MAKE_PROGRAM=$taskTools/w64devkit/bin/ninja.exe" "-DCMAKE_C_COMPILER=$taskTools/w64devkit/bin/gcc.exe" "-DCMAKE_CXX_COMPILER=$taskTools/w64devkit/bin/g++.exe"
if ($LASTEXITCODE -ne 0) { throw 'Configure failed' }
& $taskCmake --build "$taskRoot\build" --parallel $Jobs
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
& "$taskTools\python\cmake\data\bin\ctest.exe" --test-dir "$taskRoot\build" --output-on-failure
if ($LASTEXITCODE -ne 0) { throw 'Native tests failed' }
