# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
.SUBCKT DIV IN OUT
MATH_I INNER = IN/2
MATH_B OUT = INNER/2
.ENDS DIV
MATH_A A = 4
X_DIV A B DIV
MATH_C C = B/2
```
## Simulation
```pulse
.TRAN T_END=1 SAVE_DT=.1

```
## Layout
```json
{}
```
