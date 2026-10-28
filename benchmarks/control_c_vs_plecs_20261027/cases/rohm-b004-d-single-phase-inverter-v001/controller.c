#include "pulse/software.h"
#include <math.h>
#include <stdint.h>
/* Same continuous sinusoidal comparator law as the PLECS controller.
   Only actual gate changes are delivered to the electrical model. */
typedef struct Controller {
    uint64_t half_count;
    unsigned half, phase;
    double root_offset, half_start;
} Controller;
enum { BOOT=1, CROSSING=2, DELAYED_ON=3, IDLE=4 };
static const double HALF=0.000025;
static const double DEAD=0.0000008;
static double root_offset(double start,unsigned half) {
    double lo=0,hi=HALF;
    for(unsigned k=0;k<70;k++) {
        double t=(lo+hi)*.5;
        if(t==lo||t==hi)break;
        double triangle=half?1-80000*t:-1+80000*t;
        double g=.80000000000000004*sin(314.15926535897933*(start+t))-triangle;
        if((g>0)==(half==0))lo=t;else hi=t;
    }
    return (lo+hi)*.5;
}
PULSE_SW_EXPORT const pulse_software_info *PULSE_SW_CALL pulse_software_describe(void) {
    static const pulse_software_info info={PULSE_SOFTWARE_ABI,sizeof(pulse_software_info),sizeof(Controller),0,2,0};
    return &info;
}
PULSE_SW_EXPORT int PULSE_SW_CALL control_step(pulse_software_call *c) {
    const Controller *old=(const Controller*)c->previous_state;
    Controller *s=(Controller*)c->next_state;
    *s=*old;
    if(c->trigger_flags & PULSE_SW_EXTERNAL) {
        s->half=(unsigned)(s->half_count%2);
        s->half_start=c->time;
        s->root_offset=root_offset(c->time,s->half);
        if(s->half_count==0) {
            c->outputs[0]=0;c->outputs[1]=0;
            s->phase=BOOT;c->next_delay=DEAD;
        } else {
            s->phase=CROSSING;c->next_delay=s->root_offset;
        }
        s->half_count++;
    } else if(c->trigger_flags & PULSE_SW_WAKEUP) {
        if(s->phase==BOOT) {
            c->outputs[0]=1;c->outputs[1]=0;
            s->phase=CROSSING;c->next_delay=s->root_offset-DEAD;
        } else if(s->phase==CROSSING) {
            c->outputs[0]=0;c->outputs[1]=0;
            s->phase=DELAYED_ON;c->next_delay=DEAD;
        } else if(s->phase==DELAYED_ON) {
            c->outputs[0]=s->half?1:0;
            c->outputs[1]=s->half?0:1;
            s->phase=IDLE;
        } else return 2;
    }
    return 0;
}
