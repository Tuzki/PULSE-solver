# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
V1 A 0 DC=1
L1 A B L=20u
LCOUP (B 0) (OUT 0) L_MATRIX=[[64u,31.99968u],[31.99968u,16u]] IC_I=[0,0]
R1 OUT 0 R=1.6
```
## Simulation
```pulse
.TRAN T_END=1u SAVE_DT=.1u

```
## Layout
```json
{}
```
