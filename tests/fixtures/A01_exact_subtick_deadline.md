# PULSE Netlist v1.1

## Parameters
```pulse
.PARAM TINY=8.470329472543003390683225006796419620513916015625e-22
```
## Network
```pulse
MATH_D D = 1
INT1 X D
CMP1 G X OP=GE THRESHOLD={TINY}
EVENT_C CLK MODE=AT AT={TINY}
```
## Simulation
```pulse
.TRAN T_END={TINY} SAVE_DT=.1u

```
## Layout
```json
{}
```
