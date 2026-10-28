# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
MATH_NEG NEG = -1
EVENT_C CLK MODE=AT AT=.5
REG1 Q NEG CLK IC=1
MATH_LOG Z Q OP=LOG
```
## Simulation
```pulse
.TRAN T_END=1 SAVE_DT=.1

```
## Layout
```json
{}
```
