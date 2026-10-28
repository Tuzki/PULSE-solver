# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
EVENT_C CLK MODE=AT AT=.25
EVENT_A A MODE=DELAY SOURCE=CLK DELAY=.1
EVENT_B B MODE=DELAY SOURCE=CLK DELAY=.100000000000000001
```
## Simulation
```pulse
.TRAN T_END=1 SAVE_DT=.1

```
## Layout
```json
{}
```
