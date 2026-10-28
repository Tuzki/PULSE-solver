# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
EVENT_C CLK MODE=AT AT=.25
EVENT_A A MODE=DELAY SOURCE=CLK DELAY=0
EVENT_B B MODE=DELAY SOURCE=A DELAY=0
MATH_ONE ONE = 1
REG1 Q ONE B IC=0
```
## Simulation
```pulse
.TRAN T_END=1 SAVE_DT=.1

```
## Layout
```json
{}
```
