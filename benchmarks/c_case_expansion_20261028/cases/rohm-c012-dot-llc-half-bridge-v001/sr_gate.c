#include "pulse/software.h"
#include <math.h>
typedef struct { double due;int armed; } State;
PULSE_SW_EXPORT const pulse_software_info *PULSE_SW_CALL pulse_software_describe(void) {
    static const pulse_software_info i={PULSE_SOFTWARE_ABI,sizeof(i),sizeof(State),1,1,1};return &i;
}
PULSE_SW_EXPORT int PULSE_SW_CALL gate_init(pulse_software_call *c) {
    State *s=c->next_state;s->due=INFINITY;s->armed=0;c->outputs[0]=0;return 0;
}
PULSE_SW_EXPORT int PULSE_SW_CALL gate_step(pulse_software_call *c) {
    State *s=c->next_state;
    if(!c->inputs[0]){c->outputs[0]=0;s->armed=0;s->due=INFINITY;}
    else if(c->trigger_flags&PULSE_SW_EXTERNAL){s->armed=1;s->due=c->time+c->parameters[0];c->next_delay=c->parameters[0];}
    if(s->armed&&c->inputs[0]&&c->time>=s->due-2e-15){c->outputs[0]=1;s->armed=0;s->due=INFINITY;}
    return 0;
}
