# Six-core replacement integration

Baseline: `10582101b794f0a15789883d630e986f064814a4`. Branch: `experiment/six-core-replacement-20261102`.

This commit integrates all six complete source files generated from the supplied package: `descriptor.cpp`, `engineering_flow.cpp`, `runtime.cpp`, `pevt.cpp`, `solver_strategy.cpp`, and `semantics.cpp`. The generator verified every pinned baseline Git blob and refused any dirty replacement target. Originals and package-generated files are retained under ignored `reports/six-core-package-20261102/`.

The changes add structurally certified original-equation cache rebinding, exact hash lookup for Flow bases, a discrete candidate prefilter before exact archive comparison, and opt-in phase/section counters. The numerical strategies and semantic dependency classification remain unchanged.

Three integration corrections were required:

1. Restrict the generator include anchor to namespace declarations; its original text also matched closing namespace comments and refused generation.
2. Split two differently typed iterators into separate `auto` declarations to make the generated C++ valid.
3. Rebind the current observer values into a copy of `B`, then evaluate the original matrix-vector expression. The package's `reference + (current-reference)` update can lose a small current value through cancellation; it is not used.

Package SHA256, generated and integrated file hashes, and build status are in [MANIFEST.json](MANIFEST.json). No binary, build cache or simulation output is committed.

This integration does not claim CTest, simulation, accuracy or performance success. Those activities remain stopped under the user's instructions. Build-only verification is recorded separately from runtime verification; prior 27/27 results apply to baseline 1058210, not automatically to this commit.

Build-only result: Windows GCC 16.2 Release and Linux GCC 13.3 Release both built `pulse-solver` and `pulse-replay` successfully. CTest and simulations were not run.
