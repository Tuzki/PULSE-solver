# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
MATH_D DX = 1
INT1 X DX
EVENT_C CLK MODE=AT AT=.5
REG1 Q X CLK
EVENT_D OFF MODE=DELAY SOURCE=CLK DELAY=.1
```
## Simulation
```pulse
.TRAN T_END=1 SAVE_DT=.1

```
## Layout
```json
{}
```
