# PULSE Netlist v1.1
## Parameters
```pulse

```
## Network
```pulse
.SUBCKT LOW IN OUT
MATH_D DX = 1000*(IN-OUT)
INT_F OUT DX IC=0
.ENDS LOW
.SUBCKT HALL IN OUT
Xfilter IN OUT LOW
.ENDS HALL
Xone A B HALL
Xtwo C D HALL
```
## Simulation
```pulse
.TRAN T_END=1m SAVE_DT=1u
```
## Layout
```json
{}
```
