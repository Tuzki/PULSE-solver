# PULSE Netlist v1.1

Read-only legacy source: `linear_rc.net`; SHA-256 `5b76171e003e011aedc3600f7bf09090e2f4c64ba27f3c1a074edcd9a9e1b4e7`.
This fixture records a structural migration; simulation acceptance is tracked separately.

## Parameters
```pulse

```

## Network
```pulse
V1 a 0 DC=10
R1 a b R=100
C1 b 0 C=1u IC_V=2
```

## Simulation
```pulse
.TRAN T_END=0.001 SAVE_DT=9.9999999999999995e-07
```

## Layout
```json
{"version":"1.1","components":{},"wires":[]}
```
