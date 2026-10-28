# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
MATH_DX DX = 1e16
MATH_DY DY = 1
MATH_DZ DZ = -1e16
INT_X X DX
INT_Y Y DY
INT_Z Z DZ
MATH_S SUM = X+Y+Z
CMP1 G SUM OP=GE THRESHOLD=.5
```
## Simulation
```pulse
.TRAN T_END=1 SAVE_DT=.1

```
## Layout
```json
{}
```
