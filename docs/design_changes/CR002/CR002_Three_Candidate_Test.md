# CR-002 Three-Candidate Partial-Switch Test

## Status

**NOT COMPLETED.**

No physical three-candidate fixture currently produces:

```text
candidate set = {D1,D2,D3}
actual changed = {D1,D2}
D3 remains off by full-new-mode derivative
```

with an independent oracle.

## Why this matters

This is required to prove that the derivative iteration, not candidate count,
selects the actual switched set. The current `near_rc_diode_pf` and
`near_coupled_diode_pf` have two candidates and both switch, so they do not
cover partial switching.

## Existing evidence

The current source has no “all candidates” preference branch. The derivative
loop can keep a candidate in its old bit when its new-mode slope does not imply
a boundary crossing; however, a physical three-candidate fixture exercising
that path has not yet been built.

## Required next step

Construct a three-branch coupled PWA circuit where:

- all three guards are near `a` in the old mode;
- after D1/D2 switch, D3's full-mode right slope moves away from its boundary;
- D3 remains off;
- independent oracle confirms the D1/D2 trajectory and D3 non-event.

This file is intentionally marked incomplete; no PASS is claimed.
