# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
MATH_TWO TWO = 2
INT_V V TWO IC=-2
INT_X X V IC=1
CMP1 G X OP=GE THRESHOLD=0
```
## Simulation
```pulse
.TRAN T_END=2 SAVE_DT=.1

```
## Layout
```json
{}
```
