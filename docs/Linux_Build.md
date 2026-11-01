# Linux x86-64 native build

PULSE uses the same C++20 kernel on Windows and Linux. Linux executes ELF64
solver binaries and ELF shared C controllers; no Windows backend is involved.

## Ubuntu / WSL2

Install Ubuntu under WSL2 separately if it is absent. From an administrator
PowerShell, `wsl --install -d Ubuntu` may enable Windows features and require a
reboot. This port does not perform those system changes. After Ubuntu is usable:

```bash
sudo apt-get update
sudo apt-get install -y build-essential cmake ninja-build python3 libssl-dev python3-numpy
git clone https://github.com/Tuzki/PULSE-solver.git
cd PULSE-solver
git switch feature/linux-support
./build_linux.sh
```

CMake >= 3.24, GCC with C++20 support and Python 3 are required. Eigen 3.4.0
and JSON headers are bundled. OpenSSL libcrypto supplies SHA256 on Linux;
`${CMAKE_DL_LIBS}` supplies POSIX loading. Windows retains BCrypt and the
LoadLibraryExW/GetProcAddress/FreeLibrary implementation. `BUILD_TESTING=ON`
requires Python so software tests cannot silently disappear.

`build-linux/` is separate from Windows `build/`. Set
`CMAKE_BUILD_PARALLEL_LEVEL=2` (default) to control build memory. Extra script
arguments go to CMake, e.g. `./build_linux.sh -DCMAKE_CXX_COMPILER=g++`.
The script fails if configure, build, precision probe or any CTest fails.
Test details are in `build-linux/tests.xml` and `Testing/Temporary/LastTest.log`.

## Native C modules

```bash
python3 scripts/build_software.py /path/to/model/netlist.md --cc gcc
./build-linux/pulse-solver /path/to/model/netlist.md --out reports/my-run
```

The compiler target selects `.dll` for MinGW and `.so` for Linux.
`CC` or `--cc` selects the compiler; the default is `gcc` on PATH. Linux
adds `-fPIC -Wl,-z,defs`; Windows retains `-static-libgcc`. Both retain
`-ffp-contract=off -fno-fast-math`, software ABI 2, dependency hashes,
descriptor checks, scheduling and instance state. Build manifests contain
absolute dependency paths: moving a model or changing hosts requires rebuilding.
Native modules must match the host ABI and architecture. Never copy Windows
DLLs into a Linux run or reuse an existing manifest across platforms.

Linux paths are case-sensitive; use the exact source/header spelling. Netlist
contents are UTF-8 (optional BOM supported); paths use native filesystem
encoding. CMake and build scripts quote paths. No path separators are rewritten
inside user netlists. `software.h`, `software.hpp`, CLI and Eigen require no ABI,
scheduling or numerical changes for this port.

## Floating point

The original strict floating-point flags are unchanged. Run
`./build-linux/platform_probe_tests` to record actual precision. The test
requires x86-64 Linux long double to have 64 significand bits and exponent limit
16384 and checks a representable increment smaller than binary64 epsilon.
It prints size, epsilon, endian and pointer width. A 16-byte storage size alone
does not establish precision. Windows GCC and MSVC must be measured separately;
no bitwise trajectory equivalence is assumed. Solver tolerances, matrix methods,
events, state coordinates and all physical models are unchanged.

## Full original C002

```bash
git clone https://github.com/Tuzki/PULSE-case-set.git ../PULSE-case-set
git -C ../PULSE-case-set checkout 13660577132de41c37c1c47576c02941d21c532a
python3 scripts/run_c002_linux.py --case-set ../PULSE-case-set --out reports/c002-linux-001
python3 scripts/compare_c002.py --case-set ../PULSE-case-set --run reports/c002-linux-001 --out reports/c002-linux-001/comparison.json
```

The runner verifies committed input bytes and provenance SHA256, copies original
inputs without edits, compiles CTRL.so, and runs the ELF solver with no time,
sampling, budget or tolerance overrides. Original T_END=0.3 s and SAVE_DT=0.2 us
are preserved. Existing run directories are refused. `benchmark.json` records
wall time, environment, identities, final time, status and transaction count.
On solver failure its report, committed state, NPZ and event log are retained.
Abrupt process/host termination may prevent the solver writing its final prefix;
stdout/stderr and the runner's RUNNING ledger still identify that incomplete run.

The comparison checks reference hashes and full interval coverage. It reports
full-grid mean/rms/max with provenance channel atol plus 1% and pointwise RMSE /
maximum errors, without time alignment shifts. These full-grid statistics are
distinct from historical windowed acceptance. The 1 us PLECS export cannot
resolve all switching edges; completion alone is not precision acceptance.

The Linux workflow runs all CTests on each branch push and PR. A manual
`workflow_dispatch` with `c002=true` also runs the complete C002 and uploads
evidence. Its wall time is a CI measurement, never a local benchmark.
