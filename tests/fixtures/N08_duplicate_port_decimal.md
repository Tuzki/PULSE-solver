# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
MATH_D D = .1
REG1 TON D CLK IC=.2
EVENT_C CLK MODE=PERIODIC START=0 PERIOD=.1
EVENT_D OFF MODE=DELAY SOURCE=CLK DELAY_INPUT=TON POLICY=TRANSPORT
```
## Simulation
```pulse
.TRAN T_END=.25 SAVE_DT=.01

```
## Layout
```json
{}
```
