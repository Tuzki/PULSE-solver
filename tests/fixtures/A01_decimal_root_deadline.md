# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
MATH_D D = 1
INT1 X D
CMP1 G X OP=GE THRESHOLD=1u
EVENT_C CLK MODE=AT AT=1u
```
## Simulation
```pulse
.TRAN T_END=1u SAVE_DT=.1u

```
## Layout
```json
{}
```
