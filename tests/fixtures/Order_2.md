# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
MATH_U U = 1-2*VS-Z
C1 N 0 C=1
SENSOR_V VS V N 0
I1 0 N U
INT_Z Z VS
R1 N 0 R=1

```
## Simulation
```pulse
.TRAN T_END=1 SAVE_DT=.1

```
## Layout
```json
{}
```
