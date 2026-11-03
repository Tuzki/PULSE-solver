# Verification status (2026-11-04)

## Completed here

1. Read the actual Stage D and audit branch source through the connected GitHub repository. Confirmed that each of the six modified existing source files contains the relevant unique original code anchors.
2. `python scripts/selftest_patch.py` **PASS**. Synthetic original anchors are checked for uniqueness; dry-run writes no files; application changes all intended files; repeat apply refuses; mismatched source refuses without partial source modification.
3. `python scripts/smoke_cpp_helper.py` **PASS**. Extracted C++20 coordinate-cache implementation compiled with GCC 14.2, strict floating-point options, Eigen headers, and ran a functional smoke test for source isolation, reuse, and changed chart.
4. The archive contents were enumerated and hashed after creation.

## Not completed here

**This artifact is an integration candidate, not a prevalidated solver binary.** A complete checkout of `Tuzki/PULSE-solver` and its A010 files was not available to the local compiler. Therefore I did **not** run the real solver Release build, Windows/Linux CTest, A010 50-ms simulation, runtime allocation audit, or bitwise PEVT comparisons. Do not report Stage D.1 as validated until Codex completes these real repository checks. No claim is made that the proposed cache yields a particular speedup.

## Non-negotiable acceptance

- Stage D.1a must preserve numerical equality including +0/-0, not replace it with bytewise equality.
- Stage D.1b must never cache an accepted **state**, only an immutable coordinate Binding tied to original COW storage and exact chart. Original state-dependent original-equation verification and `accept_mode_entry()` remain on each request.
- Stage D.1c must reuse only the proven immutable A rows; B and N remain state-dependent.
- All 35 existing Stage D CTests plus the new test, rollback checkpoints, and A010 50-ms PEVT simulation sections 2–10 must pass without relaxing tolerances. If any fails, do not merge.
