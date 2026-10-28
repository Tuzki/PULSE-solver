# CR-002 Derivative-Driven Joint Mode Reclassification

**Date:** 2026-10-20  
**Status:** partial implementation; positive two-candidate and coupled cases pass.

## Actual flow

```text
First Root at a
  -> Runtime candidate scan on [a, a+T_atom]
  -> seed event = certified first root
  -> derivative_joint():
       copy old bits/segments
       toggle required seed CMP parts
       compile_specified(full circuit, bits, segments)
       compute all candidate guard values and right slopes from the SAME new Mode
       decide each candidate future segment
       if changed: update bits, recompile
       repeat (max 8)
       final mode_engineering_legal + non-candidate strict check
  -> closure() with the precompiled Mode (no settle() enumeration)
  -> commit at a
```

## C++ structures

- `finite` new `compile_specified()` in `src/descriptor.cpp`, declared in
  `include/pulse/core.hpp`.
- `derivative_joint()` in `src/runtime.cpp`.
- `closure(..., const Mode *forced_mode)` skips the first `settle()` when a
  derivative joint mode is supplied.

## Positive results

`near_rc_diode_pf`:

```text
COMPLETED
transactions = 2
ROOT events = 1
accepted time = 6.941476808935867e-7 s (a)
policy = ENGINEERING_CLUSTER_ACCEPTED
candidate_members = D1,D2
actual_changed_members = D1,D2
joint_iterations = 2
mode_compilations = 6
root_queries = 2
root_failures = 0
```

D2 is switched early by about 2 fs; the new mode right slope is
`-4.995104892220325e5`, old-mode delta `2.0039461001509624e-15 s`, both inside
`T_atom=1e-14`.

`near_coupled_diode_pf` (shared node, D1 ON changes D2's right-hand side):

```text
COMPLETED
transactions = 2
accepted a = 6.951491832306485e-7 s
policy = ENGINEERING_CLUSTER_ACCEPTED
actual changed = D1,D2
final V(a) = 0.500025 V
oracle both-on steady = 0.5000249992500374 V
```

## Removed rule

The previous “prefer the complete candidate set” branch has been deleted.
There is no candidate-count or switch-count preference in the current source.

## Not implemented

- PWA segment derivative reclassification for arbitrary multi-segment tables
  (CMP candidate path implemented; PWA candidate returns unresolved).
- Three-candidate partial-switch positive fixture.
- 20/100-element scaling benchmark.
- Full adversarial matrix.
- First-class First Root candidate handoff.
