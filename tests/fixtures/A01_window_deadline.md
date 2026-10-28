# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
SEL1 DX G 3 1
INT1 X DX
CMP1 G X OP=GE THRESHOLD=1
EVENT_C CLK MODE=AT AT=.3333333333333333
```
## Simulation
```pulse
.TRAN T_END=.4 SAVE_DT=.1

```
## Layout
```json
{}
```
