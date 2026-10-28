# CR-002 Baseline Review (G0)

**Date:** 2026-10-20  
**Base:** CR-001 rollback completed, Stage 1 + Runtime Root-Coordinate Scaling Fix.  
**Production source was not modified for CR-002 during G0.**

## Evidence

- rollback report: `reports/rollback_cr001/CR001_Rollback_Report.md`
- target snapshot: `reports/production_fix/scaling_fix/final_source_snapshot.tar.gz`
- source hashes: `reports/rollback_cr001/source_hashes_after.txt`
- clean build: `build-rollback-cr001/`
- binary hashes: `reports/rollback_cr001/binary_hashes_after.txt`

## Actual results

| Check | Result |
|---|---|
| Source matches pre-CR target | 30/30, 0 mismatch |
| CTest | 8/8 PASS |
| Product acceptance | 124 tests, 118 PASS / 6 INCONCLUSIVE / 0 FAIL |
| Buck_DCM | COMPLETED |
| Boost_DCM | COMPLETED |
| BuckLong | COMPLETED |
| Stack_Buck | COMPLETED |
| Stack_Boost | COMPLETED |
| CE01 | COMPLETED |
| CE02 | COMPLETED |
| LLC | STOPPED_UNRESOLVED / ROOT_ORDER / prefix 0 |
| LLC100 | STOPPED_UNRESOLVED / ROOT_ORDER / prefix 0 |
| Historical legacy | 2 PASS / 7 INCONCLUSIVE / 0 FAIL |
| Historical extra | 2 PASS / 1 INCONCLUSIVE / 0 FAIL |

Baseline binary:

```text
4303df5acc5f591b7d84c96db57126e0b8068d8bad29dce9760f6269c5d338d2  build-rollback-cr001/pulse-solver
```

## Gate

```text
CR001_ROLLBACK_CONFIRMED = YES
G0_BASELINE_ACCEPTED = YES
```
