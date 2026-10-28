# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
V1 IN 0 DC=10
R1 IN OUT R=2
C1 OUT 0 C=.5
SENSOR_V VC V OUT 0
SENSOR_I IR I R1
```
## Simulation
```pulse
.TRAN T_END=1 SAVE_DT=.1

```
## Layout
```json
{}
```
