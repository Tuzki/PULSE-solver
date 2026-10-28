# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
V1 N 0 DC=1
L1 N 0 PHII_TABLE=[(0,1),(1,3),(2,6)] IC_PHI=1 RANGE=EXTEND
```
## Simulation
```pulse
.TRAN T_END=3 SAVE_DT=.1

```
## Layout
```json
{}
```
