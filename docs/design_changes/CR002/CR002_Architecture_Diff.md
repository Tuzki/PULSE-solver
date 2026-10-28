# CR-002 Architecture Diff

| Layer | 2026-10-18 design | 2026-10-19 contract | CR-001 rollback (current) | CR-002 target |
|---|---|---|---|---|
| First event | root isolation + candidate near set | strict root order before accept | strict root order; safe stop | certified earliest cluster handoff |
| Near events | engineering candidate cluster | single candidate + delayed switch only | no cluster | exact class vs engineering cluster |
| Joint reclass | all PWA threshold scan + joint model | limited formal contract | not implemented | bounded joint model |
| Acceptance | exact or engineering approximation | single/delayed only | safe stop | approved exact/engineering policy |
| Parasitic C | diode/MOS nonideal | no universal requirement | mixed; no explicit Cj/Cds in fixtures | explicit pF audit + new fixtures |
| LLC | stress case | not universal | ROOT_ORDER, prefix 0 | remains separate stress regression |

Current production is at the verified pre-CR baseline. CR-002 has not changed
production code or default acceptance semantics.
