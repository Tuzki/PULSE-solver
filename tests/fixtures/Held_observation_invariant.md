# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
V1 IN 0 DC=1
R1 IN OUT R=1
C1 OUT 0 C=1
EVENT_C CLK MODE=AT AT=.5
MATH_A A = .1
REG_R R A CLK IC=.2
MATH_Y Y = 3*R+1
```
## Simulation
```pulse
.TRAN T_END=1 SAVE_DT=.1

```
## Layout
```json
{}
```
