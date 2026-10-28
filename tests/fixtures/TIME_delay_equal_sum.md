# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
EVENT_C CLK MODE=AT AT=.1
EVENT_A A MODE=DELAY SOURCE=CLK DELAY=.2
EVENT_B B MODE=AT AT=.3
```
## Simulation
```pulse
.TRAN T_END=1 SAVE_DT=.1

```
## Layout
```json
{}
```
