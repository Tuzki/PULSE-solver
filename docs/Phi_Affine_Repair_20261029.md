# Stable affine scalar observations

A true zero pole can acquire a tiny nonzero value during spectral decomposition. Forming forcing/pole and subtracting huge residues can then destroy a small observation even when state propagation is correct. The scalar evaluator now retains ill-scaled forced terms as (pole*amplitude+forcing)*phi(pole,t). Well-scaled decaying residues retain their original expression so that tiny post-transient crossings are not lost. No pole is removed or clamped.

Value, derivatives, interval evaluation and engineering scale follow the chosen expression. Existing centered expressions remain available when well scaled; singular systems and integrators retain their supported paths. Physical storage is neither reset nor projected.

Local roundoff estimates cover arithmetic evaluation in this representation; they do not prove bounds on equation elimination, spectral decomposition or every physical trajectory. We do not use a global root-time accuracy veto. Incoming derivative resolution and physical arrival/residual checks remain mandatory. High precision is used only by regression oracles.

The fixed-operator regression includes a near-zero pole and compares scalar observations, state reconstructions, derivatives and local evaluation ranges against saved independent values. Final case and regression evidence is recorded in C012_Event_Integration_20261029.md.

Nonmodal guards evaluated via reconstructed state include a componentwise arithmetic scale in local bounds. Their incoming direction is also checked across the local value-roundoff neighborhood, to reject false transverse roots near flat polynomial crossings. Scalar modal guards use the finite positive derivative evaluation check directly; their broad coefficient envelope is not converted into a root-time veto. These are representation-specific engineering checks, not a proof that every degenerate crossing is classified. Regression covers both (t-0.5)^3 safe rejection and an exactly anchored transverse oscillator root that must remain admissible.
