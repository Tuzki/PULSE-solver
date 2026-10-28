# Direct Guard Taylor Correct Port Validation

**Date:** 2026-10-20  
**Status:** port correct; D4 local certified; LLC100 COMPLETED.

## 1. Source basis

Used the provided research package:

`/Users/tuzki/Downloads/LLC_D4_Two_Algorithms_Research_20261020.zip`

Copied to `research/llc_d4_port/`. The relevant method-B patch is
`B_research_only_first_root_diff.patch`.

The earlier formal implementation used `state(l)` as the Taylor start. That was
the wrong mathematical path. The successful research code starts from the
mode-entry state `x0` and directly accumulates:

```text
v0 = x0
v_{k+1} = M v_k t/(k+1)
g_N = d + sum C v_k
g = g_N + [-tail,tail]
```

## 2. Formal implementation

`src/first_root/first_root.cpp`:

- `Context::direct_guard_taylor(t,N=52)`
- starts from `Context::initial`, preserving `Input::radius`;
- includes the affine coefficient and homogeneous coordinate;
- includes the initial infinity norm in the remainder:

```text
|c_aug|_1 * |s0|_inf * exp(z) * z^(N+1)/(N+1)!
```

- rejects nonfinite/overflow with `whole()`;
- is called only from `point(t)` when the normal endpoint interval contains zero;
- intersects normal and direct intervals; a disjoint intersection returns
  `whole()` rather than selecting one;
- no guard/device-specific branch.

The old `direct_bounds(l,r)` based on `state(l)` was removed.

## 3. D4 local result

Formal C++ API input from `llc_endpoint_native_bench.cpp`:

```text
A/b/C/d: exact LLC D4 frozen mode
initial x: exact benchmark state
h: 3.313373784554016e-6
search: local D4 guard only
```

Direct guard interval probe:

```text
t = 1.7171796834735824e-6:
  g = [-8.65789e-12, -8.32825e-12]

t = 1.7171796834751441e-6:
  g = [+1.19056e-13, +4.48408e-13]

z = 7.2766
tail = 6.99214e-17
```

The right endpoint is strictly positive. Independent high-precision reference
is approximately `+2.8588734018e-13`, inside both intervals.

Formal `fri::find_first_event` result:

```text
FOUND_CERTIFIED
event = 0
time = 1.717179683475...e-6
bracket = [1.717179683475..., 1.717179683475...]
nodes = 11
```

The original research report measured `UNRESOLVED` / 83 nodes for the original
endpoint path and `FOUND_CERTIFIED` / 7 nodes for method B. The formal macOS
port is 11 nodes; the small difference is due to the formal search/options and
is acceptable. D4 is certified on the target platform.

## 4. LLC100 result

Original netlist unchanged:

`tests/regression/llc_100cycles.md`

```text
status: COMPLETED
transactions: 1994
events: 1993
simulated time: 1.0000000000000000e-3 s
T_END: 1.0e-3 s
switching cycles: 100
projection_count: 0
```

LLC 50 us case:

```text
status: COMPLETED
transactions: 94
events: 93
simulated time: 5.0e-5 s
```

Waveform checks:

```text
samples = 10002
time monotonic = true
all analog samples finite = true
final time = 0.001
66 analog channels
```

Event times are monotonically increasing; no NaN/nonfinite samples. SVD
projection was not triggered in this run.

## 5. Regression

```text
CTest: 8/8 PASS
124 acceptance: 118 PASS / 6 INCONCLUSIVE / 0 FAIL
production regressions: 69 checks PASS
five historical circuits: COMPLETED
CE01/CE02: COMPLETED
LLC: COMPLETED
LLC100: COMPLETED
near-root A/B/C/D/E: unchanged/pass
```

The production registration now asserts LLC/LLC100 COMPLETED and the formal D4
local certificate.

## 6. Performance

macOS ARM64, current build:

```text
llc_100cycles: 19.27 s wall (1994 transactions)
buck_dcm:      0.00 s wall (small)
CTest total:   19.71 s including full LLC100 production test
```

The Direct Guard Taylor fallback is only invoked at endpoints whose normal
interval contains zero. It does not run on clean endpoints. The research
prototype's Linux 32 us single-call timing is not used as a macOS product
benchmark.

## 7. Safety notes

- Initial interval radius is preserved.
- Remainder includes the initial state norm.
- Overflow/nonfinite tail returns `whole()`.
- Normal/direct disjoint intervals return `whole()`, not an arbitrary choice.
- No time/tolerance/LLC parameter changes.
- D4 local and LLC100 completion use the actual formal First Root API.

## 8. Remaining risk

The port is validated on D4 and the LLC/LLC100 regression, plus all historical
tests. The 52-order Tailor fallback is not a universal proof for every possible
mode/time scale; it retains a safe `whole()` fallback. Full GEC/CAP and other
unresolved pF circuits remain outside this round.

## 9. Final status

```text
DIRECT_GUARD_TAYLOR_PORT_CORRECT = YES
DIRECT_GUARD_TAYLOR_ENCLOSURE_VALIDATED = YES (D4/LLC and regression scope)
LLC_D4_LOCAL_CERTIFIED = YES
FIRST_ROOT_CORRECTNESS_REGRESSION = PASS
PERFORMANCE_REGRESSION = PASS
LLC100_COMPLETED = YES
CR002_REGRESSION = PASS
```
