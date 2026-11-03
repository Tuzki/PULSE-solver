# PULSE Stage D.1 — conservative runtime repair patch

**Input**: `Tuzki/PULSE-solver` at `performance/stage-d-20261104` (`b3906c7713f057a763536629b5d7873cb21d34e9`), or source-unmodified descendant `audit/cd-runtime-repetition-20261104` (`bea2d59d...`). Do **not** apply to `main`, Stage C, or an unrelated branch.

**Scope**: minimal, generic fixes for measured repetition; no new external dependencies, topology rules, numerical algorithms, protocols, events, or parameter changes. The only new cache is **owned by the existing `ScopedModeCache`**, has 512-entry FIFO capacity and holds immutable source + transformed coordinate Bindings; it is neither global nor process-persistent.

| Fix | Target | Method | Remaining work |
|---|---|---|---|
| D.1a | `Flow::compatible` 5,779,584 unnecessary Matrix allocations / 50 ms | Generic const-reference `same` preserves scalar `==` (`+0 == -0`) without Vector→Matrix conversion | Matrix comparisons still happen |
| D.1b | `portfolio_compile` 41,234 binding-coordinate COW deep copies | Reuse full transformed Binding by *identical source COW object*, fixed chart matrix bitwise contents, per-model cache; original physical state-dependent checks always run before lookup | First encounter / post-eviction still performs full copy and multiplication; caching has memory cost |
| D.1c | `bind_observations` 1,331,925 conservatively redundant static A-row norms / 50 ms | Save `lpNorm<1>()` at immutable `ObserverBinding` build; unchanged B and N computations | B-norms, dynamic checks remain |

## Install (Codex performs these in its own local repository)

1. Start from the exact Stage D commit or the audit branch; create a **new** working branch, such as `fix/stage-d1-runtime-repair-20261104`.
2. **Clean working tree required** (`git status --porcelain`). Do not overwrite local changes.
3. Run `python scripts/apply_stage_d1.py --repo <checkout> --dry-run` from this package. The script verifies HEAD is a descendant of Stage D and checks every source anchor before any write.
4. Apply: `python scripts/apply_stage_d1.py --repo <checkout> --manifest <report-dir>/PATCH_MANIFEST.json`. Installer copies the included `tests/stage_d1_regression.cpp` into repository.
5. `git diff --check`. Windows and Linux Release build and **all** CTest, including `stage_d1_regression`; A010 full **50 ms** should finish `COMPLETED`.
6. Rerun strict `stage_c_verify.py` on **baseline Stage D PEVT versus patched result**: simulation sections 2–10 must be identical. Also compare failure/rollback checkpoints from Stage D; all expected physical/transaction state checks must remain.
7. Run `audit/cd-runtime-repetition-20261104` analysis on the new branch with the *same* measurement setup: full allocation-only ELF intercept and instrumented path counters. Record reduction in `flow_same_matrix`-related allocations, portfolio COW deep detaches, Binding A-row norm repetitions. No wall-clock claims from repetition counters.
8. **Fail closed** if any test differs, any PEVT simulation section changes, COW isolation fails, or allocation results show regression. Do not alter tolerance, event ordering, save interval, or numerical representation. Submit one isolated commit with real results. Do not merge without passing evidence.

### Important measurement distinctions

The report from the audit branch records one 50-ms pass each, not statistical CPU performance. The 500-ms Stage D wall time (47.62 s) is a **separate** earlier measurement and is not a predicted D.1 outcome. Some original 50-ms data and PEVT baseline are local only and are not included in this package; Codex must use its authorized machine artifacts and actually run the solver. The installer makes source edits only; it does **not** run or attest to Release builds, CTest, A010, PEVT, or PLECS. Do not claim the patch is validated until they pass.

### File contents

- `scripts/apply_stage_d1.py`: transactional anchor-checked source patch installer.
- `tests/stage_d1_regression.cpp`: new non-assert CTest for source COW, coordinate conversion, chart mutation/eviction behavior, and vector equality with signed zero.
- `codex_prompt.txt`: short copyable instructions.
- `README.md`: scope, guardrails, precise validation contract.
