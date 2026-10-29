# PULSE V1.2pre engineering contract

This independent preview implements the user's five-zone netlist and a minimal
C software domain alongside a constitutive-breakpoint event kernel. The V1.15
contract is retained as provenance in V1_15_Engineering_Contract.md. Original
source files, releases, models and earlier acceptance evidence remain read-only.

1. All electrical nonlinear constitutive laws remain continuous piecewise
   affine laws with the currently supported strictly positive finite slopes.
   There is no smooth nonlinear integration option or ideal-diode primitive.
2. Physical q/phi/INT state evolves under one locally compiled affine system.
   Control bits and constitutive region indices have different meanings.
3. Predict each current-region boundary's first directed root. A boundary
   records device, knot, current segment, target direction and physical
   coordinate (R voltage, C charge, L flux).
4. Predict all candidate roots with the same numerical strategy and old electrical
   equations. Anchor the atomic group at the earliest root; include roots no later
   than first+T_atom, without chained expansion. Advance to the latest member.
5. Check each nonlinear boundary at its own predicted time, then update the
   selected group jointly. Earlier members may already have crossed at the group
   execution point. A physical arrival mismatch retries the complete attempt.
6. Left temporal derivative proposes the successor region; the full successor
   circuit must satisfy direction, constitutive region and physical residual
   checks. Located zero/unresolved derivatives remain unsupported diagnostics.
7. Gate/REG changes and constitutive events can invalidate algebraic R regions.
   Close these dependencies in the same bounded joint solve. Do not reset,
   project, or invent storage state to obtain an admissible successor.
8. Numerical comparators retain control-threshold semantics and use the same
   first-root atomic grouping policy. Finite, resolved incoming direction and
   physical residual checks remain mandatory. The policy does not use a global
   root-time error veto or claim exact physical simultaneity.
9. Exact scheduled deadlines retain order. T_atom and SAVE_DT are separate;
   ADC capture, code execution and output changes must have explicit causality.
10. Every C task is an instance with explicit copyable state. Inputs are frozen
    at invocation; state, held outputs and event requests are staged and commit
    together. Failed transactions roll back all of them. Root probes never call
    C code. Multiple tasks in a microstep read one immutable snapshot.
11. Software outputs are known held values within an electrical flow. Values
    affecting equations enter the complete template cache key. Hidden algorithm
    state is not cached as an accepted result.
12. Native software ABI 2 is independent of host ABI 2. Module metadata and
    actual source/header/DLL hashes are checked before execution. One task per
    MCU, at most 64 KiB of copyable instance state, REAL/BOOL held outputs and
    TRIG activation are the supported initial scope.
13. C execution time on the host is not electrical simulation time. Tasks
    may request a strictly positive next_delay; the shared event agenda owns the
    resulting deadline. General ADC/DAC/PWM peripheral models and preemption are
    future work; C gate-state-machine examples do not imply these are complete.
14. Total transaction count is unlimited by default (Options.max_transactions=0).
    A positive caller limit produces TRANSACTION_BUDGET with a committed prefix.
    Same-time microstep, root search, joint-iteration, repeated-configuration and
    output-size checks remain independent protections.
15. Validation includes analytical/discrete recurrence checks, native regression,
    all six user-selected full-duration power cases, prior same-model results
    and saved independent PLECS references. Preserve original thresholds and
    failure evidence. Reused PLECS captures are identified as reused, not live.
16. These are numerical point trajectories. Completion, local roundoff checks
    and regression acceptance are not global mathematical certification.

17. Region-classification candidates cannot be propagated or committed. Candidate
    reconstruction is checked at the current point, including cache hits; final
    constitutive consistency, original entry residuals and preserved-state
    constraints are required before acceptance. Exact algebraic gauge zeros are
    retained without changing charge, flux or integrator state. Local guard and
    state evaluation use the same affine increment near a constitutive knot.

18. Event transactions retry registered numerical strategies from the same
    immutable committed checkpoint. Internal numerical coordinates preserve
    small current differences; public q/phi/INT views retain their semantics.
    See Event_Checkpoint_Retry_20261028.md for implementation scope and limits.

19. Scalar affine observations retain ill-scaled forced terms using phi, with no
    near-zero-pole clamping. Value, derivative and local evaluation estimates use
    the same representation. See Phi_Affine_Repair_20261029.md and
    C012_Event_Integration_20261029.md for evidence and limits.
