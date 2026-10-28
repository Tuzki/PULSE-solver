# CR-002 Pending Decisions

**No default engineering approximation policy is approved.**

| ID | Decision | Suggested for experiment | Status |
|---|---|---|---|
| DEC-01 | Common acceptance time/path | validate `CLUSTER_DELAYED_APPROX` first; exact bridge as reference | PENDING |
| DEC-02 | Guard/constitutive relaxation domain | explicit delayed approximate model, limited to cluster | PENDING |
| DEC-03 | q/phi/eta, energy, time error budget | dimensionally meaningful local bound; not T_atom alone | PENDING |
| DEC-04 | Retreat on unverified successor/complex event | exact path or safe stop | PENDING |
| DEC-05 | pF baseline for missing parasitics | 1 pF public test default; device data wins | PENDING |

## Minimum counterexamples before approval

1. Early switch before threshold with high-conductance segment; show whether the
   old constitutive relation is violated.
2. Two roots within `T_atom` but with large q/phi/energy difference.
3. Zero first derivative/tangency with a later root.
4. A PWM/deadline inside the candidate window.
5. Candidate set with multiple legal successors.
6. Nonzero absolute start and immediate second cluster.

## Required evidence

- same-model high-precision or analytic oracle;
- same-root/window evidence;
- actual event log and state mapping;
- before/after error numbers;
- regression impact;
- explicit `ENGINEERING_APPROXIMATION` label.

## Gate

```text
DEFAULT_APPROX_POLICY_APPROVED = NO
```
