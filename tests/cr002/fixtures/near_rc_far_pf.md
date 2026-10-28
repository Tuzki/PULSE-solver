# PULSE Netlist v1.1

CR-002 TEST-D: two independent events separated by much more than T_atom.
Explicit 1 pF Cj per diode; no solver implicit capacitance.

## Parameters
```pulse
.PARAM D1_VON=.5
.PARAM D1_RON=.1
.PARAM D1_ROFF=1Meg
.PARAM D2_VON=.8
.PARAM D2_RON=.1
.PARAM D2_ROFF=1Meg
.PARAM CJ=1p
```

## Network
```pulse
.SUBCKT D1 A K
SENSOR_V VD V A K
CMP_ON ON VD OP=GE THRESHOLD={D1_VON}
SW_PATH A K ON RON={D1_RON} ROFF={D1_ROFF}
MATH_ZERO ZERO = 0
MATH_BIAS BIAS = {-D1_VON/D1_RON}
SEL_OFFSET OFFSET ON ZERO BIAS
I_OFFSET A K OFFSET
.ENDS D1
.SUBCKT D2 A K
SENSOR_V VD V A K
CMP_ON ON VD OP=GE THRESHOLD={D2_VON}
SW_PATH A K ON RON={D2_RON} ROFF={D2_ROFF}
MATH_ZERO ZERO = 0
MATH_BIAS BIAS = {-D2_VON/D2_RON}
SEL_OFFSET OFFSET ON ZERO BIAS
I_OFFSET A K OFFSET
.ENDS D2
VDC1 in 0 DC=1
R1 in a R=1k
C1 a 0 C=1n IC_V=0
CJ1 a 0 C={CJ} IC_V=0
X_D1 a 0 D1
VDC2 in2 0 DC=1
R2 in2 b R=1k
C2 b 0 C=1n IC_V=0
CJ2 b 0 C={CJ} IC_V=0
X_D2 b 0 D2
```

## Simulation
```pulse
.TRAN T_END=2.0000000000000002e-03 SAVE_DT=1.0000000000000000e-05
```

## Layout
```json
{"version":"1.1","components":{},"wires":[]}
```
