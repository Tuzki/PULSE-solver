# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
C1 N 0 C=1
R1 N 0 R=1
I1 0 N U
SENSOR_V VS V N 0
INT_Z Z VS
MATH_U U = 1-2*VS-Z
```
## Simulation
```pulse
.TRAN T_END=1 SAVE_DT=.1

```
## Layout
```json
{}
```
