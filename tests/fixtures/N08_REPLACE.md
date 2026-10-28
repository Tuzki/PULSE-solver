# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
EVENT_C CLK MODE=PERIODIC START=0 PERIOD=.1
EVENT_D OFF MODE=DELAY SOURCE=CLK DELAY=.15 POLICY=REPLACE
```
## Simulation
```pulse
.TRAN T_END=.39 SAVE_DT=.01

```
## Layout
```json
{}
```
