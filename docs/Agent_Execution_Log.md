# V1.15 execution and ownership

- Main agent: architecture, new C++ point flow, event search, local derivative
  mode update, transaction integration, source migration, builds and native runs.
- Existing authorized medium agent: independent compatibility audit and 15 short
  tests. It wrote only /private/tmp/pulse-v115-agent; main agent reviewed and copied
  contributions into tests/engineering_events.cpp and engineering_additional.cpp.
- The medium agent did not edit V1.1 or the main agent's source files. No two agents
  modified one file concurrently.
- Independent audit found REG-driven mixed CMP/PWA algebraic jump omissions and
  overwritten first-delta derivative evidence. Main fixed and reran the tests.
- Actual first core test run: 8/9; zero-derivative floating false trigger fixed.
  Added jump validation initially over-rejected later delta steps; scoped it to
  actual algebraic-map changes, then 15/15 tests passed.
- First 20-case native run: 19 completed, rectifier pF stopped on root-search budget.
  Near-repeated exponential cancellation handling was repaired; rerun completed
  all 20 cases and passed all seven CTest targets.
- Precise native build/source IDs, ICs, raw outputs and times are recorded in
  reports/validation; superseded failure ledger retained as iteration01_ledger.json.
