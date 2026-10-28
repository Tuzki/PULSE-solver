# PULSE Netlist v1.1
## Parameters
```pulse

```
## Network
```pulse
R1 A 0 IV_TABLE=[(-2,-2m), (0,0), (2,20m)]
C1 A 0 QV_TABLE=[(-1,-2u),(0,0),(1,3u)] IC_Q=0
L1 A 0 PHII_TABLE=[(-1,-2u),(0,0),(1,3u)] IC_PHI=0
LCOUP (P1 P2) (S1 S2) L_MATRIX=[[50u,23.75u],[23.75u,12.5u]]
+ IC_I=[0,0]
SENSOR1 IL I LCOUP PORT=1
```
## Simulation
```pulse
.TRAN T_END=1m SAVE_DT=1u
```
## Layout
```json
{}
```
