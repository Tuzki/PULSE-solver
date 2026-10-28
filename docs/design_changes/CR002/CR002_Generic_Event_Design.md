# CR-002 Generic Event Design

**Status:** design draft for review; no production default change.  
**Scope:** generic PWA autonomous events, not LLC-specific.

## 1. Normal path

The existing single-event path remains the fast path:

```text
compiled immutable mode
  -> per-guard certified first root
  -> exact deadline comparison
  -> single accepted event
  -> atomic commit
```

No candidate-cluster scan is entered unless the root engine can certify a
plausible earliest cluster and its outside prefix.

## 2. Evidence objects

```text
EventWitness:
  mode_id, entry_version, agenda_version
  guard_id, direction, first_root_bracket
  earliest_and_direction proof scope

ExactEventClass:
  members + compiler-bound equivalence certificate

EngineeringCandidateCluster:
  earliest_anchor
  fixed window end = anchor + effective T_atom
  witness candidates
  excluded_guards (proven vs unknown)
  agenda_conflict evidence
  candidate_completeness scope
```

`ExactEventClass` is a strict relation. It cannot be created from merely close
roots. `EngineeringCandidateCluster` is a bounded candidate set; membership does
not force switching.

## 3. Candidate handoff

`RootFinder` must provide:

1. at least one certified first root in the cluster;
2. an outside-prefix exclusion claim for all other autonomous guards and all
   deadlines before the window;
3. mode/entry/schedule version binding;
4. fixed `T_atom` window, no chaining;
5. an explicit `PROVEN_EXCLUDED`, `CANDIDATE` or `UNKNOWN` status per guard.

`ROOT_ORDER_UNRESOLVED` alone is insufficient. If outside-prefix exclusion is
unknown, the result remains `STOPPED_UNRESOLVED`.

## 4. Candidate discovery

For every autonomous PWA guard:

- compute current value and a conservative reach bound;
- use first-order/derivative information only as a screening heuristic;
- any `UNKNOWN` or interval uncertainty is retained as a candidate;
- `PROVEN_EXCLUDED` requires a bound that covers the fixed window, not a point;
- tangency/zero derivative goes to second-order/short-interval refinement.

The current first-order screen is not a completeness proof.

## 5. Joint mode reclassification

For a bounded candidate assignment:

1. apply only真实 due forced control changes;
2. build one full network model per distinct candidate assignment;
3. check algebraic solve, constitutive/predicate, right-side derivative,
   q/phi/eta mapping, constraints, forward propagation and agenda causality;
4. candidate membership is not switching permission;
5. normal path must avoid `2^all-switches`; use constraint propagation/local
   affected subgraph and bounded local ambiguity search;
6. compile success != mode consistent != forward admissible != physical map
   verified != accepted.

The current CR-001 forced-mode prototype is research-only and is not part of
this rollback baseline.

## 6. Exact vs engineering acceptance

| Path | Evidence | Level |
|---|---|---|
| single/exact | certified first root, local successor, transaction | `LOCAL_CERTIFIED` |
| engineering cluster | outside exclusion, fixed window, approved approximation, local error/causality | `ENGINEERING_APPROXIMATION` |
| insufficient | any missing obligation | `STOPPED_UNRESOLVED` |

Preferred research candidate is `CLUSTER_DELAYED_APPROX`: accept at the earliest
common representable `Ta >= upper(root)` within `T_atom`; old mode is an explicit
approximate model during the delay. `CLUSTER_EARLY_APPROX` remains a comparison.

## 7. Physical and parasitic requirements

- diode: explicit positive `Cj` across A–K;
- MOS: explicit positive `Cds/Coss` across D–S;
- no Solver implicit C;
- no double counting if `Coss/Cj` already exists;
- adding pF changes q states and the physical model; new oracle and model hash
  are required;
- `ATOMIC_SEMANTICS_ONLY` fixtures cannot be positive physical acceptance.

## 8. Error and log fields

`model_id`, `work_model_id`, `policy_id`, `root_brackets`, `anchor`, `Ta`,
`T_atom_effective`, `exact_members`, `candidate_members`, `actual_switched`,
`numeric_scope`, `physical_map`, `constitutive_relaxation`, `time_error`,
`state_error_scope`, `energy_error_scope`, `agenda_conflicts`,
`acceptance_status`.

`T_atom` alone is never a state/energy error certificate.

## 9. Actual implementation (2026-10-20)

The Runtime now performs:

1. certified First Root query;
2. candidate scan at the accepted target, `delta_t=-g/gdot`, `0<=delta_t<=T_atom`;
3. bounded candidate subset selection through the existing `settle()`;
4. full successor-guard legality check;
5. joint acceptance at the first accepted root time `a`; `[a,a+T_atom]` is used
   only for candidate discovery, never as an unconditional wait;
6. candidate-specific engineering legality using the full new mode's right
   slope and residual resolution within `T_atom`;
7. derivative-driven full-mode iteration via `compile_specified()`; no
   candidate-count preference and no `2^k` candidate enumeration;
8. `actual_changed_members` comparison and `ENGINEERING_CLUSTER_ACCEPTED` only
   when at least two autonomous members actually change;
8. continuation with the new mode; no event replay.

Candidate membership is never treated as forced switching. The First Root
candidate evidence object is still Runtime-side rather than a first-class `fri`
return value; this is recorded as a remaining interface gap.

## 10. Gate status

- G0: complete.
- G1: implemented at Runtime level; first-class First Root candidate handoff
  remains partial.
- G2: positive `near_rc_diode_pf` and `near_diode_pf` pass; full GEC matrix
  remains incomplete.
- G3: candidate-subset joint mode implemented; full adversarial matrix pending.
- G4: `near_rc_diode_pf` COMPLETED with one joint transaction and two actual
  changes; oracle final state verified.
- G5: CTest/124/five/CE pass; pF power and LLC100 remain unresolved.
