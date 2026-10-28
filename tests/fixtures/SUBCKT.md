# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
.SUBCKT LP IN OUT
MATH_D DX = IN-OUT
INT1 OUT DX
.ENDS LP
MATH_ONE ONE = 1
X_A ONE YA LP
X_B ONE YB LP
```
## Simulation
```pulse
.TRAN T_END=1 SAVE_DT=.1

```
## Layout
```json
{}
```
