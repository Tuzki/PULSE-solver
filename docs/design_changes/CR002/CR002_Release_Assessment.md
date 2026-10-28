# CR-002 Release Assessment

## Implemented

- joint acceptance at first-root time `a`;
- fixed window `[a, a+T_atom]` used only for candidate discovery;
- full successor mode compiled with existing `settle()`;
- candidate-specific engineering legality based on new-mode right slope and
  residual resolution within `T_atom`;
- candidate vs actual changed set;
- actual changes only; `ENGINEERING_CLUSTER_ACCEPTED` requires >=2;
- coupled physical positive case;
- continuation to T_END.

## Verified

```text
GATE_B = YES
GATE_C = YES
GATE_D = YES
GATE_A = PARTIAL (First Root candidate evidence still Runtime-side)
GATE_E = PARTIAL
```

`near_rc_diode_pf` and `near_coupled_diode_pf` both COMPLETED at `a` with two
actual switches in one transaction.

## Not complete

- First-class First Root candidate evidence object.
- Full adversarial matrix (partial switching with a third candidate, PWM inside
  window, zero derivative/tangency, two clusters, nonzero start, ATOM_ORDER
  variants, multi-solution/no-solution cases).
- Eight pF power circuits unresolved.
- Full GEC/CAP and LLC100.

```text
CR002_IMPLEMENTATION_COMPLETED = NO
```
