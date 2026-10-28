# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
I1 0 N DC=1
C1 N 0 QV_TABLE=[(0,1),(1,3),(2,6)] IC_Q=1 RANGE=EXTEND
```
## Simulation
```pulse
.TRAN T_END=3 SAVE_DT=.1

```
## Layout
```json
{}
```
