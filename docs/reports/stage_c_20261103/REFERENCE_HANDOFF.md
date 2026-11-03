# Codex: merge and validate complete Stage C source bundle

**Base** `performance/stage-b-cow-20261103` at `44207f2e863db73b234a1e778f72838ffe1b5e13`.

1. Create new branch `performance/stage-c-20261103`, apply `python <unzip>/scripts/apply_stage_c.py . --in-place`. Inspect generated `src/runtime.cpp`, `src/engineering_flow.cpp`, `src/pevt.cpp`, `src/software.cpp`, `include/pulse/software.hpp`, `CMakeLists.txt`, plus the 3 new C++ files. Fix genuine compiler bugs; do not remove intended C1+C2+C3 changes.
2. Windows and Linux Release, strict floating point flags, all CTest including new `stage_c_event_kernel`; all preexisting rollback/strategy/PEVT/C ABI tests must pass.
3. Run the *original* ROHM A010 500 ms, SAVE_DT=0.1 us with the same controller, inputs and all 13 analog/4 digital channels. Baseline B+COW pinned one-run wall **61.601002s**. Prefer ≥3 alternating paired A/B runs; report median wall, CPU, RSS, full command/environment and binary SHA256. No simplified model or shortcut to 5 ms for the final result.
4. Compare PEVT **sections 2–10** payload counts and SHA256; the entire file will have different section 1 metadata. Replay both actual files, compare 5,000,001 time samples and all 17 channels by raw array SHA256, and compare original-equation validation count **477,111**, transactions **159,037**, roots **159,036**. Use `scripts/stage_c_verify.py` with both PEVT paths, reports and replay NPZ files. Investigate any difference, do not waive a section.
5. Re-test all six rollback injection points (`after_queue`, `after_reg`, `after_mode`, `after_propagation`, `before_output`, `retry_after_closure`), with full MCU state, queued events, event logs and committed states. Check timed delayed events and canceled deadlines. Record original-equation checks and retries.
6. Re-profile actual Stage C 500 ms CPU. Report phase times, especially event closure, Flow basis cache, `same_archive_definition`, memory allocation and PEVT. Do not infer a 3× improvement from architecture alone.
7. Push source changes, tests, full report and evidence JSON. Do not commit 100MB+ native artifacts; retain hashed path manifest. If compilation or differential regression fails, diagnose and report it, do not claim Stage C passed.

Scope excludes the known inherited PLECS CH006/CH007 pointwise outliers. They must not be concealed, filtered, time-shifted or used to justify changing numerical tolerance.
