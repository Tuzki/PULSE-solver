# PULSE Netlist v1.1

Read-only legacy source: `circuit.net`; SHA-256 `3d1270b261bd57444313602e961b7da83c95b1e7ebd056947a8057371f9f3907`.
This fixture records a structural migration; simulation acceptance is tracked separately.

## Parameters
```pulse
.PARAM CR002_CJ=1p
.PARAM CR002_COSS=1p
.PARAM LEGACY_D1_VON=0.5
.PARAM LEGACY_D1_RON=1
.PARAM LEGACY_D1_ROFF=1000000
```

## Network
```pulse
.SUBCKT LEGACY_DIODE_D1 A K
SENSOR_V VD V A K
CMP_ON ON VD OP=GE THRESHOLD={LEGACY_D1_VON}
SW_PATH A K ON RON={LEGACY_D1_RON} ROFF={LEGACY_D1_ROFF}
MATH_ZERO ZERO = 0
MATH_BIAS BIAS = {-LEGACY_D1_VON/LEGACY_D1_RON}
SEL_OFFSET OFFSET ON ZERO BIAS
I_OFFSET A K OFFSET
.ENDS LEGACY_DIODE_D1
C1 a 0 C=9.9999999999999995e-07 IC_V=0
L1 a 0 L=9.9999999999999995e-07 IC_I=-1
X_D1 a 0 LEGACY_DIODE_D1
* CR-002 explicit per-device parasitic capacitance (research copy)
C_X_D1_PF a 0 C={CR002_CJ}
```

## Simulation
```pulse
.TRAN T_END=3.0000000000000001e-06 SAVE_DT=1e-08
```

## Layout
```json
{"version":"1.1","components":{},"wires":[]}
```
