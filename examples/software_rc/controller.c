#include "pulse/software.h"
#include <stdint.h>
#include <string.h>
typedef struct ControllerState { uint64_t calls; } ControllerState;
extern double feedback_command(double measured, double reference);
PULSE_SW_EXPORT const pulse_software_info *PULSE_SW_CALL pulse_software_describe(void) {
    static const pulse_software_info info={PULSE_SOFTWARE_ABI,sizeof(pulse_software_info),sizeof(ControllerState),1,2,1};
    return &info;
}
PULSE_SW_EXPORT int PULSE_SW_CALL controller_init(pulse_software_call *call) {
    memset(call->next_state,0,sizeof(ControllerState));
    call->outputs[0]=0;call->outputs[1]=0;return 0;
}
PULSE_SW_EXPORT int PULSE_SW_CALL controller_step(pulse_software_call *call) {
    const ControllerState *old=(const ControllerState*)call->previous_state;
    ControllerState *next=(ControllerState*)call->next_state;
    next->calls=old->calls+1;
    call->outputs[0]=feedback_command(call->inputs[0],call->parameters[0]);
    call->outputs[1]=(double)next->calls;return 0;
}
