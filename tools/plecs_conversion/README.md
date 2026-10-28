# PLECS control primitive mappings

Independent extension of the frozen comparison-library converter. No solver
changes are required or performed by this tool. Emitting a candidate Markdown
netlist does not guarantee the solver accepts its expression phase or timing.

See ../../reports/primitive_translation_20261027/REPORT.md for scope, validation,
the retained PWM boundary discrepancy and the independent-clock limitation.
Current A002/Vienna PFC candidates fail CONTINUOUS_NONAFFINE; they are not PASS.
Continuous products are never silently replaced by sampled products. Nonzero
transfer-function initial states, reset/saturated PI and unverified feedback
sample loops are rejected. Keep original model parameters and schedules.

The fixed-parameter scalar mappings tested here include SignalSwitch, ZOH,
continuous PI, proper transfer functions, Abs, MinMax and symmetrical PWM.
Future mappings must be independently compared against native PLECS first.
