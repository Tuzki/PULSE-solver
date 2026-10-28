# Event checkpoint retry integration, 2026-10-28

Each event transaction starts from one immutable committed checkpoint. The
portfolio tries raw q/phi elimination with LU, raw elimination with QR, then
persistent difference-coordinate elimination with LU. Only an accepted
propagation and joint closure commits time, circuit state, MCU instance memory,
held outputs, invocation counters and scheduled requests. Numerical rejection
restarts from the same checkpoint; exhausting the portfolio stops with the
committed prefix. Reports retain strategy counts and bounded failure examples.

The numerical chart scales linear storage to voltage/current and preserves a
difference between opposing scalar inductor currents selected from graph
connectivity. It is not a general chart for every topology: nonlinear or
coupled-matrix storage uses the existing physical chart. Public RunState physical
state and low-level compile APIs retain q/phi/INT semantics. Simulation-owned
internal state is authoritative; state_signal and saved observations evaluate
its numerical maps directly, avoiding decode/re-encode cancellation. C++ history
is retained by default; the CLI and C ABI stream samples without retaining all
prior Mode objects. They produce the same saved waveform.

The C014-D reconstruction fix refines finite eigenpairs in balanced coordinates
using bounded bordered corrections and accepts only a non-worsening scaled
residual. It retains all finite fast modes. An independent 80-digit frozen-flow
fixture checks the small current difference and event direction.

The 249 us timing fix applies the existing arrival test to continuous CMP
thresholds as well as constitutive knots. Membership in T_atom does not mean
that a threshold has been reached. Resolvably later roots are deferred and
re-predicted after the earliest event changes the equations. A regression
puts a constitutive knot and a later comparator root inside one atomic window.

No SPICE integration, implicit time stepping, fixed 1 ns event placement,
storage projection, dropped fast pole, or relaxed residual budget is included.
T_atom remains independent of SAVE_DT. A successful finite startup comparison
does not establish completion of the original 0.2 s case, nor mathematical
global error certification. The benchmark must state its requested horizon,
held C-control sampling interval, PLECS reference setup and timing scope.
