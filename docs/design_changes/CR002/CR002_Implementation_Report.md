# CR-002 Derivative Joint Mode Implementation Report

**Status:** `CR002_CURRENT_BUG_FIXED = YES`; `DERIVATIVE_JOINT_MODE_COMPLETED = NO`; `CR002_IMPLEMENTATION_COMPLETED = NO`.

## Actual changes

- `src/descriptor.cpp` / `include/pulse/core.hpp`:
  `compile_specified()` compiles exactly one complete specified bits/segments
  mode and attaches CMP/PWA guards, with no combination enumeration.
- `src/runtime.cpp`:
  `derivative_joint()` copies the old complete mode, toggles the certified seed
  CMPs, compiles through `compile_specified()`, evaluates all candidate right
  slopes in that same new mode, updates only inconsistent candidate bits, and
  recompiles for at most 8 iterations.
  `closure()` accepts the precompiled mode and skips `settle()` on the joint path.
  Accepted time is the first root `a`; the window `[a,a+T_atom]` is only for
  candidate discovery.
- `tests/production_regression.cpp`:
  near joint, coupled joint, root time and final-state checks.

## Positive evidence

`near_rc_diode_pf`:

```text
COMPLETED
transactions=2
ROOT events=1
accepted a=6.941476808935867e-7 s
policy=ENGINEERING_CLUSTER_ACCEPTED
candidate_members=D1,D2
actual_changed_members=D1,D2
joint_iterations=2
mode_compilations=6
root_queries=2
root_failures=0
final V(a)=0.50005
oracle vss=0.5000499950005
```

D2 engineering approximation:

```text
residual=+9.999711059194283e-10
right slope=-4.995104892220325e5
old-mode delta=+2.0039461001509624e-15 s
time-to-legal=+2.0039461001509624e-15 s
T_atom=1e-14 s
```

`near_coupled_diode_pf` COMPLETED at a, two actual changes, final
`V(a)=0.500025` vs oracle `0.5000249992500374`.

## Not completed

- three-candidate partial-switch physical fixture;
- 20/100-element scaling matrix;
- PWA multi-segment candidate derivative path;
- full adversarial matrix;
- eight pF power circuits;
- LLC100;
- first-class First Root candidate handoff.

## Regression

CTest 8/8; 124 118/6/0; five historical COMPLETED; CE01/CE02 COMPLETED;
production 47 checks. LLC/LLC100 unchanged ROOT_ORDER.
