# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
EVENT_S SET MODE=AT AT=0
EVENT_R RESET MODE=AT AT=0
REG1 Q MODE=SR SET=SET RESET=RESET PRIORITY=SET
```
## Simulation
```pulse
.TRAN T_END=1 SAVE_DT=.1

```
## Layout
```json
{}
```
