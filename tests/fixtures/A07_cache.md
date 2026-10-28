# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
MATH_ONE ONE = 1
EVENT_C CLK MODE=AT AT=.5
REG1 U ONE CLK IC=0
I1 0 N U
R1 N 0 R=1
C1 N 0 C=1
SENSOR_V VS V N 0
CMP1 G VS OP=GE THRESHOLD=.25
```
## Simulation
```pulse
.TRAN T_END=1 SAVE_DT=.1

```
## Layout
```json
{}
```
