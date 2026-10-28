# PULSE Netlist v1.1
## Parameters
```pulse
.PARAM B={A}
.PARAM A=1
```
## Network
```pulse
R1 A 0 R={B}
```
## Simulation
```pulse
.TRAN T_END=1m SAVE_DT=1u
```
## Layout
```json
{}
```
