# PULSE Netlist v1.2pre

## Parameters
```pulse
```
## Simulation
```pulse
.TRAN T_END=.5 SAVE_DT=.00390625 ATOMIC_TIME=10f
```
## Electrical
```pulse
V_BUS VIN 0 DC=1
SW_H VIN OUT GH RON=.1 ROFF=1G
SW_L OUT 0 GL RON=.1 ROFF=1G
R_LOAD OUT 0 R=10
C_LOAD OUT 0 C=.01 IC_V=0
```
## MCU
```pulse
MCU MCU0 PROGRAM=GATES
TASK GATE_TASK MCU=MCU0 TRIGGER=SELF START=0 ENTRY=gate_step INPUTS=[] OUTPUTS=[BOOL::GH,BOOL::GL,FREQ] INIT_OUTPUTS=[0,0,4]
```
## Code
```pulse
PROGRAM GATES SOURCE=INLINE
```
```c
#include "pulse/software.h"
typedef struct GateState { unsigned phase, cycles; double period; } GateState;
PULSE_SW_EXPORT const pulse_software_info *PULSE_SW_CALL pulse_software_describe(void) {
    static const pulse_software_info info={PULSE_SOFTWARE_ABI,sizeof(pulse_software_info),sizeof(GateState),0,3,0};
    return &info;
}
PULSE_SW_EXPORT int PULSE_SW_CALL gate_step(pulse_software_call *call) {
    const GateState *old=(const GateState*)call->previous_state;
    GateState *next=(GateState*)call->next_state;
    const double deadtime=.015625;
    *next=*old;
    call->outputs[0]=0;call->outputs[1]=0;
    switch(old->phase) {
    case 0:
        next->period=(old->cycles%2==0)?.25:.125;
        next->cycles=old->cycles+1;next->phase=1;
        call->next_delay=deadtime;break;
    case 1:
        call->outputs[0]=1;next->phase=2;
        call->next_delay=next->period*.5-deadtime;break;
    case 2:
        next->phase=3;call->next_delay=deadtime;break;
    default:
        call->outputs[1]=1;next->phase=0;
        call->next_delay=next->period*.5-deadtime;break;
    }
    call->outputs[2]=1.0/next->period;return 0;
}
```
