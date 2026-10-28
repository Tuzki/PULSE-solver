# V1.1 → V1.15 migration

Source snapshot: reports/migration_baseline.json. V1.1 itself remains read-only.

| Interface/module | V1.15 handling |
|---|---|
| netlist.cpp / netlist.hpp | Retained Markdown, parameters, SUBCKT and source maps |
| semantics.cpp | Retained thirteen primitives, typing, PWA tables and state construction |
| descriptor.cpp | Retained joint compiler and compile_specified; runtime no longer calls global settle |
| core.hpp | Retained Model/Mode/RunState/Result; added fixed atomic_time, explicit legacy exponent sentinel |
| time_origin.cpp / Time | Retained canonical T128 deadlines and external-time bookkeeping |
| engineering_flow.cpp | New point flow, per-guard event prediction and bounded search |
| engineering_mode.cpp | New local joint derivative update, initialization and discrete jump handling |
| runtime.cpp | Replaced coordinator; retained snapshot, transport/replace/cancel and rollback semantics |
| propagate.cpp | Retained mathematical helper; product engineering flow checks physical state without projection |
| CLI / C ABI | Version updated; ABI1/2 layout/symbols and return codes retained; CLI adds --atomic-time |
| output.cpp / npz.cpp | PEWave signal arrays and event/report filenames retained; evidence wording updated |
| certified_flow.cpp / cegs.cpp | Archived under validation/v1_1, not product runtime dependencies |
| V1.1 strict acceptance tests | Archived for reference; old certificate assertions are not relabeled V1.15 PASS |
| V1.1 circuit fixtures | Copied unchanged; original SHA values recorded in execution ledgers |

ABI2 callers explicitly supplying atom_exponent retain SAVE_DT-relative timing.
Null ABI2 run options use the new 10fs default. New CLI atomic-time does not alter
the existing binary ABI structure. Equivalent options are recorded in the report.
