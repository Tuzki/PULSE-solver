# CR-002 Joint Mode Math Validation

## Definitions

For the complete candidate mode `sigma`:

```text
dx/dt = A_sigma x + b_sigma
g_i(x) = C_i x + d_i
dg_i/dt|a+ = C_i (A_sigma x(a) + b_sigma)
```

The new mode is compiled before any candidate derivative is evaluated. The same
`A_sigma,b_sigma` is used for every candidate.

## Self-consistency

A candidate CMP bit is self-consistent when either:

1. its oriented guard is already on the legal side and no boundary crossing is
   required; or
2. its guard is off-boundary but the new right slope reaches the boundary
   within `T_atom`; or
3. it is already ON with a small positive residual whose negative right slope
   resolves the residual within `T_atom` (engineering approximation).

Otherwise the candidate bit is changed and the full mode is recompiled. A
bounded loop of at most 8 iterations is used.

## Engineering approximation

For `near_rc_diode_pf`:

```text
D2 residual at a      = +9.999711059194283e-10
D2 right slope        = -4.995104892220325e5
D2 old-mode delta     = +2.0039461001509624e-15 s
D2 time-to-legal      = +2.0039461001509624e-15 s
T_atom                = 1e-14 s
```

The residual is not hidden and the state is not changed. The log records the
values and the acceptance kind as `approx`.

## Coupled validation

`near_coupled_diode_pf` shares node `a`; D1 ON changes the full A matrix seen by
D2. Independent reference:

```text
D1 = 6.951491832306183e-7 s
D2 = 6.951491852366443e-7 s
gap = 2.006e-15 s
final V(a) both-on = 0.5000249992500374 V
```

Runtime accepts at D1 and reaches final V(a)=0.500025.

## Limits

- CMP candidates supported; PWA multi-segment candidate selection is unresolved.
- No proof for arbitrary nonlinear high-order guard motion; the existing interval
  First Root remains the protection for non-joint events.
- No three-candidate partial-switch positive fixture yet.
