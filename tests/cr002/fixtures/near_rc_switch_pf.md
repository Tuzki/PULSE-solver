# PULSE Netlist v1.1

CR-002 synthetic two-branch RC MOS-switch PWA fixture. Two real, different near
thresholds, each with an explicit 1 pF drain-source capacitor. This is a new
physical model, not a legacy fixture.

## Parameters
```pulse
.PARAM NR_S1_VON=.5
.PARAM NR_S1_RON=.1
.PARAM NR_S1_ROFF=1Meg
.PARAM NR_S2_VON=.500000001
.PARAM NR_S2_RON=.1
.PARAM NR_S2_ROFF=1Meg
.PARAM CR002_COSS=1p
```

## Network
```pulse
.SUBCKT NR_S1 A K
SENSOR_V VD V A K
CMP_ON ON VD OP=GE THRESHOLD={NR_S1_VON}
SW_PATH A K ON RON={NR_S1_RON} ROFF={NR_S1_ROFF}
.ENDS NR_S1
.SUBCKT NR_S2 A K
SENSOR_V VD V A K
CMP_ON ON VD OP=GE THRESHOLD={NR_S2_VON}
SW_PATH A K ON RON={NR_S2_RON} ROFF={NR_S2_ROFF}
.ENDS NR_S2
VDC1 in 0 DC=1
R1 in a R=1k
C1 a 0 C=1n IC_V=0
C_NEAR_S1 a 0 C={CR002_COSS}
X_S1 a 0 NR_S1
R2 in b R=1k
C2 b 0 C=1n IC_V=0
C_NEAR_S2 b 0 C={CR002_COSS}
X_S2 b 0 NR_S2
```

## Simulation
```pulse
.TRAN T_END=2.0000000000000002e-03 SAVE_DT=1.0000000000000000e-05
```

## Layout
```json
{"version":"1.1","components":{},"wires":[]}
```
