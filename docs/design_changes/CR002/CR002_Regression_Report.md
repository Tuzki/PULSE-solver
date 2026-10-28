# CR-002 Regression Report

## Historical baseline

| Check | Result |
|---|---|
| CTest | 8/8 PASS |
| 124 acceptance | 118 PASS / 6 INCONCLUSIVE / 0 FAIL |
| Buck_DCM, Boost_DCM | COMPLETED |
| BuckLong, Stack_Buck, Stack_Boost | COMPLETED |
| CE01/CE02 | COMPLETED |
| LLC/LLC100 | STOPPED_UNRESOLVED / ROOT_ORDER |

## CR-002 positive

| Fixture | Result |
|---|---|
| near_rc_diode_pf | COMPLETED; derivative joint at a; 2 actual changes |
| near_coupled_diode_pf | COMPLETED; coupled node; 2 actual changes |
| near_diode_pf | COMPLETED; joint |
| near_rc_switch_pf | STOPPED_UNRESOLVED / JOINT_DERIVATIVE_UNRESOLVED |

## pF stress

CE01_pf/CE02_pf COMPLETED; eight power pF copies remain NONMONOTONE. No PASS is
claimed and no reference was changed.

## Production checks

```text
PASS production regressions 47 checks
```

## No new FAIL

The 124 ledger remains `118/6/0`; no new failure was introduced in this round.
