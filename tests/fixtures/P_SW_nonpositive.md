# PULSE Netlist v1.1

## Parameters
```pulse

```
## Network
```pulse
SW1 N 0 G RON=0 ROFF=1
REG1 G MODE=SR SET=C RESET=C PRIORITY=RESET
EVENT_C C MODE=AT AT=0
```
## Simulation
```pulse
.TRAN T_END=1 SAVE_DT=.1

```
## Layout
```json
{}
```
