# CR-002 Mode Selection Audit

## Current source audit

- `src/runtime.cpp`:
  - `engineering_candidates()` scans every PWA/CMP guard at `a`;
  - `derivative_joint()` is the normal joint path;
  - `compile_specified()` is called directly;
  - `settle()` is no longer called inside the joint path;
  - no `base_legal`, no candidate subset map, no “prefer complete candidate
    set”, no `2^k` candidate enumeration.
- `src/descriptor.cpp`:
  - `settle()` remains for initialization and non-joint closure;
  - `compile_specified()` compiles exactly one given `bits/segments` vector.

## Selection rule

For each candidate CMP at the SAME new mode:

```text
value = C_i x + d_i
slope = C_i (A_sigma x + b_sigma)
```

- current segment legal and no boundary crossing -> keep;
- off segment, slope reaches threshold inside `T_atom` -> ON;
- on segment, positive residual with negative slope resolving inside `T_atom`
  -> keep ON as engineering approximation;
- on segment that cannot resolve inside `T_atom` -> OFF;
- non-candidate guards must be strictly legal.

`ENGINEERING_CLUSTER_ACCEPTED` requires at least two actual changed members.

## What was removed

```text
if (base_legal.size() > 1) { prefer all candidates ... }
```

The current source contains no such rule. The candidate set only seeds the
derivative iteration; it does not preselect the final bits.

## Remaining rule gap

PWA multi-segment future selection is not implemented. CMP candidates are
supported; PWA candidates currently cause a conservative unresolved result.
The existing `settle()` remains available for initialization/fallback outside
the normal joint path.
