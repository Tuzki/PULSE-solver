# CR-002 Math Validation

## Correct diode model

```text
OFF: iD = vD/Roff
ON : iD = (vD - VON)/RON
```

`MATH_BIAS=-VON/RON` and `I_OFFSET` are included; `Roff=1 MΩ` is included.

## near_rc_diode_pf

```text
D1 root = 6.941476808935289e-7 s
D2 root = 6.941476828975329e-7 s
gap = 2.004e-15 s
T_atom = 1e-14 s
```

The Runtime accepts at `a = first accepted root`, not `a+T_atom`. D2 is still
before its strict threshold at `a`, so it is an **engineering approximation**
member. The new full mode's right slope at D2's guard is negative and the
predicted time to legal is:

```text
D2 guard value = +9.999711e-10
right slope     = -4.995105e5
time to legal   = 2.003946e-15 s <= T_atom
old-mode delta  = 2.003946e-15 s
```

The full successor is legal after allowing this one candidate-specific
approximation. No state jump is applied.

Final:

```text
runtime a = 6.941476808935867e-7 s
oracle D1 = 6.941476808935289e-7 s
final V(a) = 0.50005 V
oracle vss = 0.5000499950005 V
```

## Coupled near_coupled_diode_pf

D1 and D2 share the same node, so the new mode's A matrix changes D2's right
slope. Independent reference:

```text
D1 = 6.951491832306183e-7 s
D2 = 6.951491852366443e-7 s
gap = 2.006e-15 s
both-on steady = 0.5000249992500374 V
```

Runtime accepts at `a` with D1/D2 actual changes; final V(a)=0.500025. This
demonstrates that candidate reclassification uses the full new mode rather than
old-mode independent predictions.

## Engineering boundary

Candidate-specific approximation requires:

- candidate membership within `T_atom`;
- a legal full-mode successor;
- guard violation moving toward the legal side;
- residual resolution within `T_atom`;
- no state jump;
- explicit log of value, slope, delay and old-mode delta.

Candidates that do not meet this remain strict or unresolved.
