# CR-002 Scaling Benchmark

## Status

**NOT COMPLETED** for the requested 20/100-element explicit matrix.

## Available measurements

Representative 5-repeat wall times on the current build:

```text
buck_dcm   0.06 s
boost_dcm  0.05 s
BuckLong   0.34 s
Stack_Buck 0.20 s
Stack_Boost 0.21 s
near joint 0.04 s
```

Near joint counters:

```text
mode_compilations = 6
root_queries = 2
root_failures = 0
joint_iterations = 2
candidate_members = 2
actual_changed = 2
```

## What is established

- The joint path calls `compile_specified()` once per derivative iteration;
- it does not call `settle()` and does not enumerate `2^k` candidate modes;
- no global all-switch enumeration occurs in the derivative path.

## What is not established

Actual 20-element and 100-element fixtures with only 2/3 candidates were not
constructed, so the requested A/B/C/D scaling table is not available. No
theoretical complexity claim is substituted for the missing measurements.
