# CR-002 Regression and Performance Report

## Baseline

| Check | Result |
|---|---|
| CTest | 8/8 PASS |
| 124 acceptance | 118 PASS / 6 INCONCLUSIVE / 0 FAIL |
| Five historical circuits | COMPLETED |
| CE01/CE02 | COMPLETED |
| LLC/LLC100 | STOPPED_UNRESOLVED / ROOT_ORDER |

## Positive joint cases

| Fixture | Result |
|---|---|
| near_rc_diode_pf | COMPLETED; 1 joint ROOT at a; 2 actual changes |
| near_coupled_diode_pf | COMPLETED; coupled node; 1 joint ROOT at a; 2 actual changes |
| near_diode_pf | COMPLETED; joint ROOT; 2 actual changes |
| near_rc_switch_pf | STOPPED_UNRESOLVED / NO_LEGAL_ENGINEERING_SUCCESSOR |

## pF power

CE01_pf/CE02_pf COMPLETED. Eight power pF copies remain NONMONOTONE; no PASS is
claimed; no expectation was changed.

## Performance (5 repeats, current build)

```text
buck_dcm   0.06 s
boost_dcm  0.05 s
BuckLong   0.34 s
Stack_Buck 0.20 s
Stack_Boost 0.21 s
near joint 0.04 s
```

Production regression now reports 47 checks; CTest remains 8/8.

## Joint path

- candidate subset compilation only;
- fixed window `[a, a+T_atom]`;
- no wait to `a+T_atom`;
- no global 2^all-switches path;
- candidate cap 8;
- scalar guard flow retained for the following First Root query.
