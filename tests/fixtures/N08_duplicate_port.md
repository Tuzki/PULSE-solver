# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
MATH_D D = .125
REG1 TON D CLK IC=.25
EVENT_C CLK MODE=PERIODIC START=0 PERIOD=.125
EVENT_D OFF MODE=DELAY SOURCE=CLK DELAY_INPUT=TON POLICY=TRANSPORT
```
## Simulation
```pulse
.TRAN T_END=.3125 SAVE_DT=.015625

```
## Layout
```json
{}
```
