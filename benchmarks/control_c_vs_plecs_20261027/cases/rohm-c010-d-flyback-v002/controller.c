#include "pulse/software.h"
PULSE_SW_EXPORT const pulse_software_info *PULSE_SW_CALL pulse_software_describe(void) {
    static const pulse_software_info info={PULSE_SOFTWARE_ABI,sizeof(pulse_software_info),0,0,1,1};
    return &info;
}
PULSE_SW_EXPORT int PULSE_SW_CALL control_step(pulse_software_call *c) {
    if(c->trigger_flags & PULSE_SW_EXTERNAL) {
        c->outputs[0]=1;
        c->next_delay=c->parameters[0];
    } else if(c->trigger_flags & PULSE_SW_WAKEUP) {
        c->outputs[0]=0;
    }
    return 0;
}
