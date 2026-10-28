# CR-002 Compiler Interface: Specified Complete Mode

## API

```cpp
Mode compile_specified(const Model &m,
                       const Vector &x,
                       const std::map<std::string, double> &regs,
                       Stats &stats,
                       const std::map<int, bool> &bits,
                       const std::map<int, int> &segments);
```

Defined in `src/descriptor.cpp`, declared in `include/pulse/core.hpp`.

It constructs one `Assembler` with the supplied complete `bits`/`segments` and
returns the solved `Mode` with all CMP/PWA guards attached. It does not iterate
other CMP/PWA combinations.

## Fixed non-event segments

`derivative_joint()` copies `old.mode.segments` and `old.mode.bools`, modifies
only the seed/candidate bits, and passes the complete map to
`compile_specified()`. Non-event parts therefore keep their segment while still
participating in the MNA solve.

## Derivative computation

The Runtime uses the returned `Mode`:

```text
dg/dt = guard.row.dot(mode.M * x)
```

for every candidate guard in the same full mode. No old-mode-per-candidate
stitching is used.

## Enumeration boundary

`compile_specified()` does not enumerate. `settle()` still exists and is used for
initialization and for non-joint closure. The normal derivative joint path does
not call `settle()`.
