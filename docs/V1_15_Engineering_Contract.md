# PULSE V1.15 engineering runtime contract

This document supersedes V1.1's runtime acceptance rules for this independent
project. The V1.1 input language, thirteen primitives, physical state, C ABI 2,
and PEWave output are retained. Archived V1.1 documents describe provenance;
they do not override the user's V1.15 engineering decisions.

1. Current mode and physical charge/flux/integrator state define one affine flow.
2. Locate the earliest directed threshold crossing for each active device.
3. Anchor one candidate window [t1,t1+T_atom]; do not chain-expand it.
4. T_atom defaults to 10 fs and is independent of SAVE_DT. Explicit legacy
   atom-exponent configuration remains available for existing ABI2 callers.
5. Advance the old flow to t1. Recompute only candidate discrete modes using
   their derivatives in the complete proposed successor. Non-candidates retain
   their modes. Boolean comparator outputs are event-held; their combinational
   REAL/BOOL dependents settle in the same transaction after a comparator or
   REG change, without adding a physical sampling delay.
6. Old-mode candidates may disappear under successor derivatives. The first
   crossing must retain its direction. Actual changed members are logged.
7. A located event with zero/unresolved derivative stops; ordinary stationary
   non-triggering devices do not stop the run. Repeated zero-time configurations
   and exhausted budgets stop with the last committed prefix intact.
8. REG, dynamic delays and TRIG use immutable snapshots, delta microsteps and
   transactional commit/rollback. Independent scheduled deadlines retain order.
9. State propagation uses matrix exponential/modal affine flow. It is a
   numerical point trajectory, not an inherited all-history enclosure. Reports
   make no global mathematical certification claim.
10. Models must explicitly include required switching transition/commutation
    dynamics using the existing PWA primitives and SUBCKT. Adding a capacitor
    does not automatically impose a channel-current fall-time or dwell limit.
    The primitive SW remains finite Ron/Roff; its limitations are documented.
11. Physical state cannot be reset, silently projected, or changed to force a
    mode transition. Inconsistent descriptor constraints stop safely.
12. Validation uses analytic solutions, independent numerical references,
    historical same-model runs and eventually same-model PLECS calibration.
    V1.0 is comparison evidence, not a correctness oracle.
13. A bounded, per-simulation cache reuses complete compiled mode templates.
    Keys include all candidate comparator bits, PWA segments and exact binary64
    REG values; the frozen Model is isolated by cache scope. Every hit repeats
    the original physical entry constraints, coordinate reconstruction and
    algebraic residual checks. State, time, agenda and transaction acceptance
    are never cached. CLI --no-mode-cache enables exact cached/uncached checks.

14. Windows isolation-reference fix (2026-10-27): each physical port-connected
    floating component uses an independent local voltage coordinate. Magnetic
    coupling and numeric signals do not join electrical nodes. One redundant
    KCL row is replaced by its local reference equation only after exact gauge
    and KCL checks. All original physical equations remain in residual checks;
    q/phi/INT state is unchanged. Cross-component voltage sensors are rejected
    as undefined. V(node) means voltage relative to that component's reference.
    The lexicographically first node is the deterministic local reference;
    literal node 0 retains its existing global-reference behavior. No primitive
    syntax, C ABI structure, or numerical tolerance is changed.

15. Comparator-driven SW topology changes close invalid algebraic R IV
    segments in the same bounded transaction, using the existing guard error
    scale. q/phi/INT state, directed C/L root rules, cycle rejection and all
    final residual/guard checks are retained. This does not insert commutation
    dynamics or declare arbitrary algebraic switching models supported.

16. Ill-conditioned but full-rank algebraic systems (estimated reciprocal
    condition below 1e-7) use extended-precision scaling and LU solution before
    rounding maps to binary64. Rank decisions, entry residual limits, physical
    storage and event guard tolerances remain unchanged. The supported Windows
    GCC build provides extended long-double precision. This reduces spurious
    cross-coupling in nearly floating finite-leakage off-state networks.
