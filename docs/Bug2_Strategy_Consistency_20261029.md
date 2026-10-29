# Unified event-attempt strategy and trajectory

Every attempt uses one explicit strategy for equation construction, all guard predictions, propagation, every closure microstep and accepted-mode construction. Every strategy returns maps and operators in the authoritative internal coordinate chart. Mode provenance is checked at closure and commit.

A failure restores the whole immutable checkpoint, including continuous trajectory, internal state, C state, held outputs and agenda; the next strategy recomputes every candidate. Each new committed event starts with LU, then retries QR and persistent-difference LU as needed. No strategy memoization is introduced. Compatible electrical trajectories retain their original anchor across software/observation events; real equation or algebraic-map changes build an independent right-hand trajectory.

Tests cover all three strategies, storage-coordinate transforms, complementary comparators, unchanged and changed electrical equations, warm caches and failed closure rollback. See C012_Event_Integration_20261029.md for final validation, rather than historical intermediate experiments.
