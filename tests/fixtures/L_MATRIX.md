# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
V1 A 0 DC=1
V2 B 0 DC=0
LCOUP (A 0) (B 0) L_MATRIX=[[2,1],[1,2]] IC_I=[0,0]
SENSOR_I IL I LCOUP PORT=2
```
## Simulation
```pulse
.TRAN T_END=1 SAVE_DT=.1

```
## Layout
```json
{}
```
