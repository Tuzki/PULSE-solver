# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
INT_Z Z VS
C1 N 0 C=1
I1 0 N U
R1 N 0 R=1
MATH_U U = 1-2*VS-Z
SENSOR_V VS V N 0

```
## Simulation
```pulse
.TRAN T_END=1 SAVE_DT=.1

```
## Layout
```json
{}
```
