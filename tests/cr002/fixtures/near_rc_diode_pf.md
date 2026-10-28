# PULSE Netlist v1.1

CR-002 synthetic two-branch RC diode PWA fixture. Two real, different near
thresholds, each with an explicit 1 pF junction capacitor. This is a new
physical model, not a legacy fixture.

## Parameters
```pulse
.PARAM NR_D1_VON=.5
.PARAM NR_D1_RON=.1
.PARAM NR_D1_ROFF=1Meg
.PARAM NR_D2_VON=.500000001
.PARAM NR_D2_RON=.1
.PARAM NR_D2_ROFF=1Meg
.PARAM CR002_CJ=1p
```

## Network
```pulse
.SUBCKT NR_D1 A K
SENSOR_V VD V A K
CMP_ON ON VD OP=GE THRESHOLD={NR_D1_VON}
SW_PATH A K ON RON={NR_D1_RON} ROFF={NR_D1_ROFF}
MATH_ZERO ZERO = 0
MATH_BIAS BIAS = {-NR_D1_VON/NR_D1_RON}
SEL_OFFSET OFFSET ON ZERO BIAS
I_OFFSET A K OFFSET
.ENDS NR_D1
.SUBCKT NR_D2 A K
SENSOR_V VD V A K
CMP_ON ON VD OP=GE THRESHOLD={NR_D2_VON}
SW_PATH A K ON RON={NR_D2_RON} ROFF={NR_D2_ROFF}
MATH_ZERO ZERO = 0
MATH_BIAS BIAS = {-NR_D2_VON/NR_D2_RON}
SEL_OFFSET OFFSET ON ZERO BIAS
I_OFFSET A K OFFSET
.ENDS NR_D2
VDC1 in 0 DC=1
R1 in a R=1k
C1 a 0 C=1n IC_V=0
C_NEAR_D1 a 0 C={CR002_CJ}
X_D1 a 0 NR_D1
R2 in b R=1k
C2 b 0 C=1n IC_V=0
C_NEAR_D2 b 0 C={CR002_CJ}
X_D2 b 0 NR_D2
```

## Simulation
```pulse
.TRAN T_END=2.0000000000000002e-03 SAVE_DT=1.0000000000000000e-05
```

## Layout
```json
{"version":"1.1","components":{},"wires":[]}
```
