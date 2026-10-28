# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
MATH_D DX = 1
INT1 X DX
EVENT_C CLK MODE=AT AT=0
```
## Simulation
```pulse
.TRAN T_END=1 SAVE_DT=.1
.SAVE X CLK
```
## Layout
```json
{}
```
