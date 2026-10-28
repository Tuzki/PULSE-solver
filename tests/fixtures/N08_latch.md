# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
MATH_NEW NEW = .2
EVENT_C CLK MODE=AT AT=0
REG1 TON NEW CLK IC=.1
EVENT_D OFF MODE=DELAY SOURCE=CLK DELAY_INPUT=TON POLICY=TRANSPORT
```
## Simulation
```pulse
.TRAN T_END=.3 SAVE_DT=.01

```
## Layout
```json
{}
```
