# CR-002 TEST-C Mixed Propagation Root Cause

**Status:** TEST-C now COMPLETED; TEST-F direct safety test PASS.

## 1. Reproduction before fix

Fixture:

`tests/cr002/fixtures/near_rc_mixed_joint_pf.md`

Joint event:

```text
a = 1.0318363235237507e-9 s
policy = ENGINEERING_CLUSTER_ACCEPTED
candidate_members = D1,D2
actual_changed_members = D1,D2
joint_iterations = 2
after_mode = D1 OFF, D2 ON
```

Propagation to T_END failed:

```text
PHYSICAL_CONSTRAINT_VIOLATION
propagated algebraic residual exceeds budget
```

## 2. Exact failure evidence

Instrumented `propagate()` reported:

```text
mode = D1=0; D2=1
h = 0.002 s
residual norm = 5.00333e-7
budget        = 7.17636e-8
out = [0, 2.4401e-13, -3.91568e-23, 5.0005e-13, 1]
```

Worst residual row:

```text
residual row 4:
  [0, -2.04931e12, 0, 1e12, 0]
reference row 4:
  [0,  2.04931e12, 0, 0, 0]
```

This row is the parallel-capacitor voltage equality for the D2 branch
(`C2` and `C_NEAR_D2`):

```text
-q2/C2 + q4/Cj = 0
C2 = .48797 pF, Cj = 1 pF
```

At a+:

```text
q2 = 2.4401e-13
q4 = 5.0005e-13
```

The residual corresponds to an absolute charge/voltage inconsistency of about
`5e-19 C`, or a relative drift around `7e-8` of the scaled row. The physical
state is correct to binary64; the failure is **algebraic constraint drift over
the long propagation**, not a circuit model inconsistency and not a gross matrix
exponential error.

## 3. Independent reference

`research/cr002/prototype/mixed_joint_oracle.py`:

```text
D1 ON->OFF = 1.031836323475e-9 s
D2 OFF->ON = 1.031839088632e-9 s
gap = 2.765e-15 s < T_atom
D2 final ON steady = 0.500049996 V
D1 final decayed to 0
```

Runtime after fix:

```text
COMPLETED
transactions = 2
final V(a) = -3.9e-17
final V(b) = 0.500049829
```

## 4. Minimal fix

`src/propagate.cpp` now permits **one** algebraic projection of the residual-map
state when the drift is provably small:

```text
if residual_map rows:
  r = R out
  if ||r|| > 1e-8 * scale:
     if ||r|| > 1e-4 * scale: reject
     solve least-squares projection with SVD
     out -= R^T (R R^T)^+ r
     recheck
```

Key properties:

- projection applies only to `residual_map`, not descriptor constraints;
- a genuine violation larger than `1e-4 * scale` is still rejected;
- no tolerance constant was relaxed;
- the valid BUG-005 constraint-only state is untouched;
- it is generic and not diode/LLC-specific.

A first attempt with `FullPivLU(R R^T)` failed because dependent rows made the
system singular; SVD correctly handles rank deficiency.

## 5. TEST-C result

```text
status = COMPLETED
transactions = 2
ROOT events = 1
a = 1.0318363235237507e-9
first_root_evidence = STRICT_FIRST_ROOT
policy = ENGINEERING_CLUSTER_ACCEPTED
candidate_members = D1,D2
actual_changed_members = D1,D2
joint_iterations = 2
final V(a) ≈ 0
final V(b) ≈ 0.50005
```

D2 is an engineering early ON member; its recorded residual/slope/delta remain in
the event log.

## 6. TEST-F

Added a deterministic First Root API test:

- two overlapping certified roots;
- `engineering_window = 0`;
- result must be `UNRESOLVED`;
- no arbitrary representative is returned.

Actual reason:

```text
EARLIER_UNRESOLVED_PREFIX: NONMONOTONE_OR_BOUNDARY_AMBIGUITY
```

This is a genuine root-order/interval deficiency, not an invalid netlist.

Also retained:

- strict root `FOUND_CERTIFIED`;
- engineering overlap `FOUND_ENGINEERING`;
- no earlier unresolved prefix accepted.

## 7. Regression and performance

```text
CTest: 8/8
124 acceptance: 118 PASS / 6 INCONCLUSIVE / 0 FAIL
production regressions: 53 checks
five historical circuits: COMPLETED
CE01/CE02: COMPLETED
near files A/B/C/D/E: COMPLETED/expected
LLC/LLC100: unchanged STOPPED_UNRESOLVED
```

Projection is a conditional path only for residual-map drift; the normal
single-event path is unchanged. CTest total is approximately 4.7 s.

## 8. Status

```text
TEST_C_MIXED_JOINT = PASS
TEST_F_FORCED_UNRESOLVED = PASS
FIRST_ROOT_INTERFACE_COMPLETED = YES
CR002_IMPLEMENTATION_COMPLETED = NO (full CR-002 gates remain)
```
