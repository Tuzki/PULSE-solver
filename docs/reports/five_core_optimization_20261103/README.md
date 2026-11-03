# Five-core optimization integration — 2026-11-03

Branch: `experiment/a010-five-core-20261103`.
Integration base: `052aab8bd78d3eace130f0b2fc3c9282a3cf12af`.
Solver baseline: `5881b86396c8bba86f435ef32e4719e8751becec`.

The supplied `PULSE_A010_five_file_optimization_patch_bundle.zip` contains source-anchored edits and a generator. Its five baseline sources match the latest checkout. All five generated files were integrated byte for byte, without additional source changes. Package and file SHA256 values are recorded in [MANIFEST.json](MANIFEST.json).

| Source | Change |
| --- | --- |
| `src/descriptor.cpp` | Move the rebound Mode; reuse the thread-local original-equation RHS matrix while rebinding certified observer values. |
| `src/engineering_flow.cpp` | Compare the four Flow key matrices directly by shape and bytes; use generic-lambda recursion with the existing root search order and checks. |
| `src/pevt.cpp` | Replace duplicate map lookups with one `find` for value and state IDs. |
| `src/runtime.cpp` | Reuse checkpoint and candidate endpoint states for the original-equation checks; retain the midpoint check. |
| `src/first_root/first_root.cpp` | Reserve root capacity and maintain the running minimum bracket upper bound. |

The patch preserves all three original-equation check locations, residual checks, root search limits, numerical tolerances, physical models, and event archive layout. It introduces no new numerical strategy or model parameter.

Original files, extracted package, generated files, build logs and CTest XML/logs are retained locally under ignored `reports/five-core-package-20261103/`. Binaries and simulation output are excluded from this commit. Existing unrelated untracked files are preserved.

## Validation scope

| Platform | Release build | CTest | Failed / skipped | Test wall time |
| --- | --- | --- | --- | --- |
| Windows x86-64, GCC 16.2 | PASS | 27/27 | 0 / 0 | 22.18 s |
| Linux x86-64, WSL Ubuntu 24.04, GCC 13.3 | PASS | 27/27 | 0 / 0 | 11.64 s |

Both native Release builds include the solver, replay utility, shared library and all test targets. The manifest records actual CTest results for this revision, including every test name, status and duration.

At the original integration commit, full Boost 0.3 s and A010 0.5 s PLECS comparisons and performance measurements had not been rerun. Subsequent single-case results are linked below. Historical power-case campaigns and full accuracy acceptance remain incomplete.

Previous-version issues remain open: Boost CH003 peak fails its statistics tolerance; A010 CH006 and CH007 each have 18 pointwise discrepancies, with CH006 reaching about 528.30 V absolute error. See the prior [Boost](../six_core_replacement_20261102/BOOST_VALIDATION.md) and [A010](../six_core_replacement_20261102/A010_VALIDATION.md) reports for their original evidence. Those results are not validation of this new revision.

Subsequent verification: full original Boost 0.3 s completed on both platforms; statistics 20/21 with CH003 peak and pointwise discrepancies retained. See [Boost validation](BOOST_VALIDATION.md).

Subsequent A010 verification: both platforms completed full 0.5 s; see [A010 validation](A010_VALIDATION.md) for timings, file sizes, statistics and unresolved pointwise/cross-platform differences.
