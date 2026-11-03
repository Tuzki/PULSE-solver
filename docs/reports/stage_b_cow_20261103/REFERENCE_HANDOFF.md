# Codex integration instructions: implement the remaining B1+B2 source migration

Base: **`performance/stage-b-20261103`**, **`0cb30419575f9254901882c14aa88d6e01e78f3f`**. This package implements the ModeDefinition/ModeBinding split and COW RunState semantics through an actual C++ header and a reproducible full-source transformation script.

**Run `scripts/apply_remaining_b.py` on a new branch.** The script changes `core.hpp`, all matching C++ uses of the old Mode/RunState fields, and adds a linked CTest. Treat compile failures as unfinished integration, not as a reason to omit the intended COW abstraction. Correct all remaining const/lvalue/range iteration sites. Do not remove checks, relax tolerances, change root solvers, alter event archives, or implement Stage C.

## COW architecture contract

- `Mode.definition.read()` is immutable; `Mode.definition.edit()` clones only when shared. It holds `M`, `constraints`, `invariant_lift/generator/reduce`.
- `Mode.binding.read()` is immutable; `.edit()` detaches. It holds `observations`, `residual_map/reference`, `maps`, and `guards`.
- `RunState` now contains COW owners of `regs`, `software`, `agenda`, and `generations`, so `RunState snap=candidate` does not duplicate those containers or the Mode matrices.
- Checkpoint is read-only, candidates may mutate only through `.edit()`, failed candidates are discarded. No shared mutable state may survive a rollback. NEVER mutate a value through `.read()` by const_cast or saved non-const pointers.
- Ensure `software::Session` C ABI uses unique mutable buffers for the candidate and preserves the frozen old byte array and separate invocation count.
- Archive, waveform, Flow continuation, and native replay must receive logically identical concrete values and preserve their original floating point order.

## Build/verification

Windows and Linux Release compile, full CTest, 5 ms early signature, 500 ms A010 signature including PEVT 2–10 hashes, all 17 waveforms, six rollback injection points. Compare with old-B 68.084811s. For regenerated PEVT section 1, source fingerprint/compile metadata differences are allowed.

The migration is currently an **uncompiled implementation candidate**; I did not run the full repository. If the automated codemod misses an Eigen mutation or a `CowValue` access, repair the generated C++ in place and add focused regression tests. Do not claim completed B without independent tests and a measurement report.
