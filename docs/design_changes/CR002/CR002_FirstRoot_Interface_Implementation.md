# CR-002 First Root Interface Implementation

**Date:** 2026-10-20  
**Status:** `FIRST_ROOT_INTERFACE_COMPLETED = YES` (A/B/C/D/E/F validated; full CR-002 remains incomplete).

## 1. Why strict root ordering stopped

`fri::Context::run()` collects one certified root per guard, then:

```cpp
if (roots[i].bracket.lo <= best.bracket.hi)
    return unresolved(best.bracket.lo,
        "ROOT_ORDER_UNRESOLVED_NOT_PROVEN_SIMULTANEOUS");
```

When two certified root intervals overlap, this returned UNRESOLVED even though
the earliest root neighborhood was already localized. Runtime therefore never
reached `derivative_joint()`.

## 2. New evidence status

Added:

```text
fri::Status::FOUND_ENGINEERING
fri::Result::engineering_representative
fri::Result::time_uncertainty
fri::Options::engineering_window
```

The strict path is unchanged. If `engineering_window > 0`:

1. all overlapping roots must already have `FOUND_CERTIFIED` evidence;
2. no earlier unresolved prefix (`frontier`) may exist below the representative
   lower bound;
3. the complete overlapping interval must fit inside
   `[best.bracket.lo, best.bracket.lo + engineering_window]`;
4. the result becomes `FOUND_ENGINEERING`; the representative is explicitly
   not claimed to be strictly earliest.

Runtime sets:

```cpp
options.engineering_window = out.t_atom;
```

and records:

```text
first_root_evidence = STRICT_FIRST_ROOT | ENGINEERING_FIRST_ROOT
first_root_time_uncertainty
```

The representative acceptance time is the first root lower bound for an
engineering result; strict roots retain their existing acceptance rule.

## 3. Runtime handoff

First Root still returns only the representative event, its guard/part through
the existing indices, the root bracket, and the evidence status. It does not
return the overlapping candidate list. Runtime continues to run
`engineering_candidates()` and `derivative_joint()`.

## 4. TEST-A: strict single root

`near_rc_diode_pf` and `near_coupled_diode_pf` remain:

```text
COMPLETED
ENGINEERING_CLUSTER_ACCEPTED at strict a
```

No strict-root behavior changed.

## 5. TEST-B: two ON -> OFF

Fixture:

[tests/cr002/fixtures/near_rc_diode_off_pf.md](tests/cr002/fixtures/near_rc_diode_off_pf.md)

Result:

```text
COMPLETED
transactions = 2
ROOT events = 1
accepted a = 1.0318363205174209e-9 s
first_root_evidence = ENGINEERING_FIRST_ROOT
first_root_time_uncertainty = 2.960011228100581e-18 s
policy = ENGINEERING_CLUSTER_ACCEPTED
candidate_members = D1,D2
actual_changed_members = D1,D2
joint_iterations = 2
final V(a) = 0.0
final V(b) = 0.0
```

Joint approximations:

```text
D1: old delta 2.95748e-18, right slope -500000, residual 1.47726e-12
D2: old delta 2.69076e-18, right slope -500000, residual 1.34404e-12
T_atom 1e-14
```

This is a real ON->OFF joint acceptance at a, not strict mathematical
simultaneous proof.

## 6. TEST-C: mixed ON/OFF

Original `near_rc_mixed_pf` remains as historical evidence. Its roots are
separated by about `8.35e-12 s`, larger than `T_atom`, so it is not a valid joint
test.

Corrected fixture:

`tests/cr002/fixtures/near_rc_mixed_joint_pf.md` (`C2=.48797 pF`)

Independent roots:

```text
D1 ON->OFF ≈ 1.031836323475e-9 s
D2 OFF->ON ≈ 1.031839088632e-9 s
gap ≈ 2.77e-15 s < T_atom=1e-14
```

Runtime:

```text
first_root_evidence = STRICT_FIRST_ROOT
a = 1.0318363235237507e-9 s
policy = ENGINEERING_CLUSTER_ACCEPTED
candidate_members = D1,D2
actual_changed_members = D1,D2
joint_iterations = 2
```

After the residual-map SVD projection described in
`CR002_Mixed_Propagation_Root_Cause.md`, TEST-C now:

```text
COMPLETED
transactions = 2
final V(a) ≈ 0
final V(b) ≈ 0.50005
```

This is a genuine numerical constraint-drift fix, not a tolerance increase.

## 7. TEST-D/E/F

### TEST-D: events outside T_atom

`tests/cr002/fixtures/near_rc_far_pf.md`:

```text
COMPLETED
ROOT 6.941476808935867e-7 s: D1 only
ROOT 1.613445933832476e-6 s: D2 only
```

The events are not merged. PASS.

### TEST-E: earlier independent event protection

`tests/cr002/fixtures/near_rc_triple_pf.md`:

```text
COMPLETED
ROOT 6.941476808935867e-7 s: D1 only
ROOT 1.613445933832476e-6 s:
  candidate D2,D3
  actual D2,D3
  policy ENGINEERING_CLUSTER_ACCEPTED
```

D1 is processed first; the later D2/D3 pair is not allowed to hide it. PASS.

### TEST-F: forced unresolved first root

A deterministic API test was added in `tests/production_regression.cpp`:
two overlapping certified roots, `engineering_window=0`, must return
`UNRESOLVED`; no representative may be selected. Actual diagnostic:

```text
EARLIER_UNRESOLVED_PREFIX: NONMONOTONE_OR_BOUNDARY_AMBIGUITY
```

PASS.

## 8. Safety condition

For engineering first root, the implementation rejects:

- an unresolved frontier at or before the representative lower bound;
- an overlapping interval extending outside `T_atom`;
- zero `engineering_window` (strict behavior).

It does not change `T_atom`, tolerances, or the physical netlist.

## 9. Regression

```text
CTest: 8/8
124 acceptance: 118 PASS / 6 INCONCLUSIVE / 0 FAIL
production regressions: 65 checks
five historical circuits: COMPLETED
CE01/CE02: COMPLETED
near_rc_diode_pf: COMPLETED
near_coupled_diode_pf: COMPLETED
near_diode_pf: COMPLETED
LLC/LLC100: unchanged ROOT_ORDER
```

No new FAIL.

## 10. Status

```text
ENGINEERING_FIRST_ROOT_INTERFACE = IMPLEMENTED
TEST_B_ON_TO_OFF_JOINT = PASS
TEST_C_MIXED_JOINT = PASS
TEST_D_OUTSIDE_WINDOW = PASS
TEST_E_EARLIER_INDEPENDENT_PROTECTION = PASS
TEST_F1_EARLIER_UNRESOLVED = PASS
TEST_F2_CERTIFIED_OVERLAP = PASS
FIRST_ROOT_INTERFACE_COMPLETED = YES
```
