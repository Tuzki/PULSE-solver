# CR-002 Parasitic Capacitor Audit

**Status:** audit and research fixture generation only. Production netlists were not overwritten. No Solver implicit capacitance was added.

## Summary

- power netlists inspected: 24
- diode instances checked: 53
- MOS/switch instances checked: 32
- devices missing explicit pF Cj/Cds: 85
- explicit 1 pF research copies generated: 10

Existing `C1` bus/filter capacitors are **not** counted as semiconductor parasitic capacitance. A pF filter is counted only when directly across the relevant A–K or D–S ports and within the pF range.

## Per-netlist audit

| netlist | diode instances (missing Cj) | MOS/switch instances (missing Cds) |
|---|---|---|
| `reports/historical_comparison/cases/Boost_CCM/model.md` | X_D1 sw/out MISSING | SW_S1 sw/0 MISSING |
| `reports/historical_comparison/cases/Boost_DCM/model.md` | X_D1 sw/out MISSING | SW_S1 sw/0 MISSING |
| `reports/historical_comparison/cases/BuckLong/model.md` | X_D1 0/sw MISSING | SW_S1 vin/sw MISSING |
| `reports/historical_comparison/cases/Buck_CCM/model.md` | X_D1 0/sw MISSING | SW_S1 vin/sw MISSING |
| `reports/historical_comparison/cases/Buck_DCM/model.md` | X_D1 0/sw MISSING | SW_S1 vin/sw MISSING |
| `reports/historical_comparison/cases/CE01/model.md` | X_D1 a/0 MISSING | - |
| `reports/historical_comparison/cases/CE02/model.md` | X_D1 a/0 MISSING | - |
| `reports/historical_comparison/cases/LLC/model.md` | X_D1 N3/N8 MISSING, X_D2 N4/N8 MISSING, X_D3 0/N3 MISSING, X_D4 0/N4 MISSING, X_D5 N6/N5 MISSING, X_D6 0/N6 MISSING | SW_S1 N5/N6 MISSING, SW_S2 N6/0 MISSING |
| `reports/historical_comparison/cases/LLC100/model.md` | X_D1 N3/N8 MISSING, X_D2 N4/N8 MISSING, X_D3 0/N3 MISSING, X_D4 0/N4 MISSING, X_D5 N6/N5 MISSING, X_D6 0/N6 MISSING | SW_S1 N5/N6 MISSING, SW_S2 N6/0 MISSING |
| `reports/historical_comparison/cases/Rectifier/model.md` | X_D1 a/out MISSING, X_D2 b/out MISSING, X_D3 0/a MISSING, X_D4 0/b MISSING | SW_S1 vin/a MISSING, SW_S2 a/0 MISSING, SW_S3 vin/b MISSING, SW_S4 b/0 MISSING |
| `reports/historical_comparison/cases/Research_RC/model.md` | X_D1 b/0 MISSING | - |
| `reports/historical_comparison/cases/Stack_Boost/model.md` | X_D1 SW/OUT MISSING | SW_S1 SW/0 MISSING |
| `reports/historical_comparison/cases/Stack_Buck/model.md` | X_D1 0/SW MISSING | SW_S1 VIN/SW MISSING |
| `reports/historical_comparison/cases/Stack_Rectifier/model.md` | X_D1 AC/OUT MISSING, X_D2 B/OUT MISSING, X_D3 RET/AC MISSING, X_D4 RET/B MISSING | SW_S1 VIN/A MISSING, SW_S2 B/0 MISSING, SW_S3 VIN/B MISSING, SW_S4 A/0 MISSING |
| `tests/regression/BuckLong.md` | X_D1 0/sw MISSING | SW_S1 vin/sw MISSING |
| `tests/regression/CE01.md` | X_D1 a/0 MISSING | - |
| `tests/regression/CE02.md` | X_D1 a/0 MISSING | - |
| `tests/regression/boost_ccm.md` | X_D1 sw/out MISSING | SW_S1 sw/0 MISSING |
| `tests/regression/boost_dcm.md` | X_D1 sw/out MISSING | SW_S1 sw/0 MISSING |
| `tests/regression/buck_ccm.md` | X_D1 0/sw MISSING | SW_S1 vin/sw MISSING |
| `tests/regression/buck_dcm.md` | X_D1 0/sw MISSING | SW_S1 vin/sw MISSING |
| `tests/regression/llc.md` | X_D1 N3/N8 MISSING, X_D2 N4/N8 MISSING, X_D3 0/N3 MISSING, X_D4 0/N4 MISSING, X_D5 N6/N5 MISSING, X_D6 0/N6 MISSING | SW_S1 N5/N6 MISSING, SW_S2 N6/0 MISSING |
| `tests/regression/llc_100cycles.md` | X_D1 N3/N8 MISSING, X_D2 N4/N8 MISSING, X_D3 0/N3 MISSING, X_D4 0/N4 MISSING, X_D5 N6/N5 MISSING, X_D6 0/N6 MISSING | SW_S1 N5/N6 MISSING, SW_S2 N6/0 MISSING |
| `tests/regression/rectifier.md` | X_D1 a/out MISSING, X_D2 b/out MISSING, X_D3 0/a MISSING, X_D4 0/b MISSING | SW_S1 vin/a MISSING, SW_S2 a/0 MISSING, SW_S3 vin/b MISSING, SW_S4 b/0 MISSING |

## Explicit 1 pF research copies

| source | copy | devices with added 1 pF |
|---|---|---|
| `tests/regression/BuckLong.md` | `research/cr002/fixtures/BuckLong_pf.md` | SW_S1 C_SW_S1_PF=1pF, X_D1 C_X_D1_PF=1pF |
| `tests/regression/CE01.md` | `research/cr002/fixtures/CE01_pf.md` | X_D1 C_X_D1_PF=1pF |
| `tests/regression/CE02.md` | `research/cr002/fixtures/CE02_pf.md` | X_D1 C_X_D1_PF=1pF |
| `tests/regression/boost_ccm.md` | `research/cr002/fixtures/boost_ccm_pf.md` | SW_S1 C_SW_S1_PF=1pF, X_D1 C_X_D1_PF=1pF |
| `tests/regression/boost_dcm.md` | `research/cr002/fixtures/boost_dcm_pf.md` | SW_S1 C_SW_S1_PF=1pF, X_D1 C_X_D1_PF=1pF |
| `tests/regression/buck_ccm.md` | `research/cr002/fixtures/buck_ccm_pf.md` | SW_S1 C_SW_S1_PF=1pF, X_D1 C_X_D1_PF=1pF |
| `tests/regression/buck_dcm.md` | `research/cr002/fixtures/buck_dcm_pf.md` | SW_S1 C_SW_S1_PF=1pF, X_D1 C_X_D1_PF=1pF |
| `tests/regression/llc.md` | `research/cr002/fixtures/llc_pf.md` | SW_S1 C_SW_S1_PF=1pF, SW_S2 C_SW_S2_PF=1pF, X_D1 C_X_D1_PF=1pF, X_D2 C_X_D2_PF=1pF, X_D3 C_X_D3_PF=1pF, X_D4 C_X_D4_PF=1pF, X_D5 C_X_D5_PF=1pF, X_D6 C_X_D6_PF=1pF |
| `tests/regression/llc_100cycles.md` | `research/cr002/fixtures/llc_100cycles_pf.md` | SW_S1 C_SW_S1_PF=1pF, SW_S2 C_SW_S2_PF=1pF, X_D1 C_X_D1_PF=1pF, X_D2 C_X_D2_PF=1pF, X_D3 C_X_D3_PF=1pF, X_D4 C_X_D4_PF=1pF, X_D5 C_X_D5_PF=1pF, X_D6 C_X_D6_PF=1pF |
| `tests/regression/rectifier.md` | `research/cr002/fixtures/rectifier_pf.md` | SW_S1 C_SW_S1_PF=1pF, SW_S2 C_SW_S2_PF=1pF, SW_S3 C_SW_S3_PF=1pF, SW_S4 C_SW_S4_PF=1pF, X_D1 C_X_D1_PF=1pF, X_D2 C_X_D2_PF=1pF, X_D3 C_X_D3_PF=1pF, X_D4 C_X_D4_PF=1pF |

## Formal CR-002 fixture copies

Thirteen pF models are now also present under `tests/cr002/fixtures/` (10 audited power copies + 3 synthetic near-root models). Original fixtures and their references were not changed.

## CAP status

| ID | status | evidence |
|---|---|---|
| CAP-01 | PASS_AUDIT | 53 diode instances missing Cj identified; copies add explicit Cj |
| CAP-02 | PASS_AUDIT | 32 MOS/switch instances missing Cds/Coss identified; copies add explicit C |
| CAP-03 | PASS_STATIC | no existing pF Cj/Cds found; no double addition in copies |
| CAP-04 | PASS_FIXTURE_GENERATION | one C per top-level instance in generated copies |
| CAP-05 | NOT_TESTED | no q continuity test on pF model yet |
| CAP-06 | NOT_TESTED | no 1 pF/10 pF independent reference yet |
| CAP-07 | PARTIAL | atomic-only fixture classification not completed |
| CAP-08 | PASS_STATIC | no Solver source change, no implicit capacitance |

Full machine-readable audit: `research/cr002/parasitic_audit.json`; fixture manifest: `research/cr002/pf_fixture_manifest.json`.
