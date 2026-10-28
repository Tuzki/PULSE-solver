# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
MATH_D D = 6
INT_A A D IC=-3
INT_B B A IC=.75
INT_C X B IC=-.125
CMP1 G X OP=GE THRESHOLD=0
EVENT_E E MODE=EDGE SOURCE=G EDGE=RISE
```
## Simulation
```pulse
.TRAN T_END=1 SAVE_DT=.1

```
## Layout
```json
{}
```
