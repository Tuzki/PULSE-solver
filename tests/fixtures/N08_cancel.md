# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
EVENT_C CLK MODE=AT AT=0
EVENT_X CANCEL MODE=AT AT=.05
EVENT_D OFF MODE=DELAY SOURCE=CLK DELAY=.1 CANCEL=CANCEL
```
## Simulation
```pulse
.TRAN T_END=.2 SAVE_DT=.01

```
## Layout
```json
{}
```
