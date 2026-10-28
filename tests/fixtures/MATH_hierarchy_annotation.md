# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
.SUBCKT DIV IN OUT
MATH_A INNER = IN/2
MATH_B OUT = REAL::INNER/2
.ENDS DIV
MATH_X X = 4
X_D X Y DIV
```
## Simulation
```pulse
.TRAN T_END=1 SAVE_DT=.1

```
## Layout
```json
{}
```
