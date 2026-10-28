# CR-002 Bidirectional Derivative Validation

**Date:** 2026-10-20  
**Scope:** `derivative_joint()` CMP ON/OFF symmetry; no architecture change.

## 1. Source audit

Current CMP branch in `src/runtime.cpp`:

```cpp
if (bits[part]) {                 // ON
    if (value > tol) {
        if (slope < 0 && (value - tol) / (-slope) <= T_atom)
            desired = true;
        else
            desired = false;
    } else if (slope > 0 && (-value) / slope <= T_atom) {
        desired = false;          // FIX: early ON -> OFF
    }
} else {                          // OFF
    if (value > tol)
        desired = true;
    else if (slope > 0 && (-value) / slope <= T_atom)
        desired = true;           // early OFF -> ON
}
```

Guard convention: the stored CMP guard is oriented so `value <= 0` is legal
for the current bit.

Before the fix, the ON branch only checked the **illegal** case `value > tol`.
If the ON guard was still legal (`value <= 0`) but had `slope > 0` and reached
zero inside `T_atom`, it remained ON. That was the asymmetry: OFF->ON early
switching was handled, ON->OFF early switching was not.

The fix adds the symmetric ON->OFF condition. No topology or device-name branch
was added.

## 2. Test A: two OFF->ON

`tests/cr002/fixtures/near_rc_diode_pf.md`:

```text
COMPLETED
transactions = 2
ROOT events = 1
accepted a = 6.941476808935867e-7 s
policy = ENGINEERING_CLUSTER_ACCEPTED
candidate_members = D1,D2
actual_changed_members = D1,D2
joint_iterations = 2
```

The new ON->OFF branch does not affect this case. Independent corrected diode
roots and final state remain as documented.

## 3. Test B: two ON->OFF

New fixture:

`tests/cr002/fixtures/near_rc_diode_off_pf.md`

Two charged branches, explicit 1 pF Cj, both diodes initially ON, turning OFF
near 0.5 V.

Actual result:

```text
STOPPED_UNRESOLVED
EVENT_ROOT_UNRESOLVED
ROOT_ORDER_UNRESOLVED_NOT_PROVEN_SIMULTANEOUS
source = X_D1/CMP_ON
transactions = 0
```

First Root fails before `derivative_joint()` is reached:

```text
local bracket lower = 1.0318363205174209e-9
local bracket upper = 3.814697265625e-9
failed guard = X_D1/CMP_ON
guard value = [-1.0222400704e-10, +9.9269426013e-11]
guard slope = [4.9949951e5, 4.9950152e5]
state width = 2.1120919568e-19
```

This is a First Root ordering failure for two ON->OFF roots, not a derivative
joint refusal. The two-root ON->OFF joint cannot be tested until First Root
candidate handoff is implemented (explicitly out of this round's scope).

Single ON->OFF branch reference:

```text
analytical t_off = 1.0318363234752089e-9 s
runtime t_off     = 1.0318363235237507e-9 s
error             ≈ 4.85e-20 s
```

The single branch confirms the ON->OFF physics and root time.

## 4. Test C: mixed ON->OFF + OFF->ON

Not completed. It is blocked by the same First Root unresolved ordering issue
before derivative_joint can run. No PASS is claimed.

## 5. Bug classification

```text
ON->OFF EARLY-SWITCH ASYMMETRY = BUG_FOUND_AND_FIXED (code)
TWO-ON->OFF JOINT TEST          = BLOCKED_BY_FIRST_ROOT_ORDER
MIXED JOINT TEST                = BLOCKED_BY_FIRST_ROOT_ORDER
BIDIRECTIONAL_DERIVATIVE_COMPLETED = NO
```

The code asymmetry was real and was fixed. The requested two-element ON->OFF
and mixed joint tests cannot be completed without the excluded First Root
candidate handoff.

## 6. Regression

```text
CTest: 8/8 PASS
124 acceptance: 118 PASS / 6 INCONCLUSIVE / 0 FAIL
production regressions: 47 checks
near_rc_diode_pf: COMPLETED joint
near_coupled_diode_pf: COMPLETED joint
```

No new FAIL. LLC remains unchanged and is out of scope.

## 7. Source and artifacts

- Source change: [runtime.cpp](src/runtime.cpp)
- Evidence: [near_rc_diode_off_pf.md](tests/cr002/fixtures/near_rc_diode_off_pf.md)
- ON->OFF oracle: `research/cr002/prototype/on_to_off_oracle.py`
- Source diff: `reports/cr002/CR002_Bidirectional_Diff.patch`
- Full patch: `reports/cr002/CR002_Source_Diff.patch`
