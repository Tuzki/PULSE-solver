# CR-002 Event Trace: Joint Reclassification at the First Root

## near_rc_diode_pf

```text
status = COMPLETED
transactions = 2
ROOT events = 1

first-root accepted time a = 6.941476808935867e-7 s
policy = ENGINEERING_CLUSTER_ACCEPTED
accepted_state_kind = approx

candidate_members:
  X_D1/CMP_ON
  X_D2/CMP_ON
actual_changed_members:
  X_D1/CMP_ON
  X_D2/CMP_ON
members:
  X_D1/CMP_ON

candidate window: [a, a + T_atom]
T_atom = 1e-14 s
held_old_mode = false

engineering approximation:
  D2 guard value at a = +9.999711059194283e-10
  D2 new-mode right slope = -4.995104892220325e5
  D2 time-to-legal = 2.0039461001509624e-15 s
  D2 old-mode delta = 2.0039461001509624e-15 s
```

Strict roots:

```text
D1 = 6.941476808935289e-7 s
D2 = 6.941476828975329e-7 s
gap = 2.004e-15 s
```

The joint event is accepted at `a` (first root), not at `a+T_atom`. D2 is
switched early by about 2 fs as an engineering candidate; this is explicitly
recorded as an approximation.

Final state:

```text
V(a) = 0.50005 V
oracle vss = 0.5000499950005 V
```

## near_coupled_diode_pf

Two diodes share node `a`; D1's ON changes the right-hand side seen by D2.

```text
status = COMPLETED
transactions = 2
ROOT events = 1
a = 6.951491832306485e-7 s
policy = ENGINEERING_CLUSTER_ACCEPTED
candidate_members = D1,D2
actual_changed_members = D1,D2
D2 old-mode delta = 2.00798610204214e-15 s
D2 right slope = -4.990119757497524e5
final V(a) = 0.500025 V
oracle both-on steady = 0.5000249992500374 V
```

This is a coupled-state-space positive case, not two independent RC branches.

## near_diode_pf

COMPLETED with one joint ROOT event and two actual changes.

## near_rc_switch_pf

STOPPED_UNRESOLVED / NO_LEGAL_ENGINEERING_SUCCESSOR. Not counted as a joint
acceptance.
