# Experimental trajectory output v1

This opt-in format defers dense waveform materialization. The default waveform
mode and the physical event solver remain in place. The experiment is on
`experiment/event-trajectory`; the prior baseline is tagged
`backup/linux-before-trajectory-20261101`.

```bash
./build_linux.sh
python3 scripts/build_software.py /path/to/netlist.md --cc gcc
./build-linux/pulse-solver /path/to/netlist.md --output-format trajectory --out trace-001
./build-linux/pulse-replay trace-001 --out waveform-001
```

Windows uses the same C++ implementation and ABI 2 C controller, built with
MinGW-w64 GCC, CMake, Ninja and Python on PATH:

```powershell
./build_windows_event.ps1
python scripts/build_software.py C:/cases/boost/netlist.md --cc gcc
./build-event-windows/pulse-solver.exe C:/cases/boost/netlist.md --output-format trajectory --out trace-001
./build-event-windows/pulse-replay.exe trace-001 --out waveform-001
```

This build directory is separate from the preserved original `build/`.
Controller DLLs on Windows and shared objects on Linux are built independently
from the same original C sources. No controller logic is duplicated.

Use a fresh output directory for each run. Replay defaults to the original
SAVE_DT. `--save-dt` can select a different display grid without re-running the
electrical or software domain. The original T_atom remains recorded.

## Files and representation

| File | Contents |
|---|---|
| metadata.json | Version, T128 description, dimension, template/record counts, original SAVE_DT/T_END/T_atom, channels, precision fields, SHA256 checksums |
| templates.json | Deduplicated numerical Mode templates: matrices, invariant factors, maps, BOOL values, regions, guard rows and numerical strategy |
| segments.bin | Original initial snapshot followed by old/new snapshot pairs for every committed transaction, including zero-duration transactions |
| event_log.jsonl | Existing event records, unchanged |
| simulation_report.json | Existing solver report plus output format and deferred waveform-validation status |

Each snapshot is explicitly little-endian, with these fields in order:

1. T128 time: signed seconds encoded in 64 bits, uint64 tick, uint64 subtick.
2. uint64 Mode template ID and uint64 Flow template ID (UINT64_MAX means no Flow).
3. `dimension` binary64 internal state values.
4. Exact T128 Flow offset.
5. `dimension` binary64 values of the **original Flow anchor**.

For the three-coordinate C002 state, a snapshot is 112 bytes and a transaction
pair is 224 bytes. Matrices in templates use round-trip binary64 JSON numbers
and column-major data with explicit row/column dimensions. No raw C++ structs,
pointers, Eigen allocation state or platform-specific padding are serialized.

Flow reconstruction calls the existing constructor with its original numerical
Mode and anchor, then restores the exact continuation offset. It does not rebase
on the public physical-state snapshot. Derived eigen/Taylor/observation caches
are rebuilt by the existing code; long-double caches are not rounded to double
and stored. The reader rejects differing long-double significand/exponent
precision. Native tests validate bitwise replay on Linux GCC and Windows
MinGW-w64 GCC. Full-case testing is paused after finding a v1 full-Mode
deduplication defect: A010 produced about 1.05 GB of redundant template JSON,
then failed archive integrity-file size checks. See
[the offline investigation](reports/Trajectory_Template_Bloat_Investigation.md).
The candidate block-sharing representation is not yet integrated or validated
as a native solver format; do not treat it as an A010 validation pass.
This prototype does not certify bitwise replay across arbitrary compiler or
math-library versions.

## Checks and completion meaning

Event discovery, root validation, joint closure, physical residual checks,
strategy retry, MCU execution, scheduling and rollback are unchanged. Archive
accessors are read-only; the only simulation-loop change selects the output
path after acceptance and before publication of each committed transaction.

Trajectory `COMPLETED` means the physical trajectory completed. Its report says
`waveform_validation=DEFERRED_TO_REPLAY`. The replay path invokes the **same**
`stream_commit` and `stream_emit` functions as normal simulation, including
sample timing, endpoint replacement, finite/float32 range checks, output-size
checks and signal observation. A replay failure is a failed waveform export;
it must not be presented as successful waveform validation. The positive marker
`waveform_validation=PASSED` is written only after materialization succeeds.

The v1 prototype has an explicit 64 MiB per-stream limit, using the existing
SHA256 helper. Hash mismatches, truncated/trailing records, invalid dimensions,
noncontiguous times and precision mismatches are errors. The final metadata
file is written after the other files. Always preserve a failed run for diagnosis.
This format reconstructs waveforms; it is not a simulation restart/checkpoint API.

## Timing

Report three separate numbers: trajectory simulation completion, complete
original-grid replay/export, and their sum. A fast trajectory-only result does
not mean all dense waveform work disappeared. The C002 experiment and its
limitations are recorded in [the comparison report](reports/Trajectory_C002_Experiment.md).

The optional Windows-host comparison harness is `scripts/benchmark_trajectory.py`.
It uses WSL2 for both PULSE binaries and replay, and the installed Windows PLECS
simulation API as the reference. NumPy/SciPy are harness dependencies for reading
PLECS MAT output; neither is a dependency of the native C++ solver or replay.
