# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
EVENT_C CLK MODE=PERIODIC START=0 PERIOD=.1
EVENT_D OFF MODE=DELAY SOURCE=CLK DELAY=.1 POLICY=REPLACE
```
## Simulation
```pulse
.TRAN T_END=.21 SAVE_DT=.01

```
## Layout
```json
{}
```
