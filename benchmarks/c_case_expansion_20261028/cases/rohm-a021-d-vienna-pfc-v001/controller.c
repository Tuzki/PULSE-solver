#include "pulse/software.h"
#include <math.h>
typedef struct {double last,next_adc,vi,ve,ii[3],ie[3],held_i[3],mod[3],vac[3],bottom; } State;
PULSE_SW_EXPORT const pulse_software_info *PULSE_SW_CALL pulse_software_describe(void) {
    static const pulse_software_info i={PULSE_SOFTWARE_ABI,sizeof(i),sizeof(State),7,6,8};return &i;
}
PULSE_SW_EXPORT int PULSE_SW_CALL control_step(pulse_software_call *c) {
    State *s=c->next_state;const double *p=c->parameters;double t=c->time,h=t-s->last,T=1/p[5],eps=2e-15;int k;
    s->vi+=p[2]*s->ve*h;for(k=0;k<3;k++)s->ii[k]+=p[4]*s->ie[k]*h;s->last=t;
    if(t>=s->next_adc-eps){
        s->ve=p[0]-c->inputs[0];double vctrl=p[1]*s->ve+s->vi;
        if(fabs(t/p[7]-nearbyint(t/p[7]))<1e-7)for(k=0;k<3;k++)s->held_i[k]=c->inputs[4+k];
        for(k=0;k<3;k++){s->vac[k]=c->inputs[1+k];s->ie[k]=fabs(vctrl*s->vac[k])-fabs(s->held_i[k]);}
        s->next_adc=(floor((t+eps)/p[6])+1)*p[6];
    }
    if(c->invocation==0||t>=s->bottom-eps){
        for(k=0;k<3;k++)s->mod[k]=fmin(1,fmax(-1,p[3]*s->ie[k]+s->ii[k]));
        s->bottom=t+T;
    }
    double phase=(t-(s->bottom-T))/T,carrier=phase<.5?-1+4*phase:3-4*phase;
    double next=fmin(s->next_adc,s->bottom);
    for(k=0;k<3;k++){
        /* Include the right-limit sign at an exact comparator crossing. */
        double crossing_up=(s->mod[k]+1)*.25,crossing_down=(3-s->mod[k])*.25;
        int positive=(phase<crossing_up-1e-10)||(phase>=crossing_down-1e-10);
        c->outputs[2*k]=(s->vac[k]>0)||positive;
        c->outputs[2*k+1]=(s->vac[k]<0)||positive;
        double a=s->bottom-T+crossing_up*T,b=s->bottom-T+crossing_down*T;
        if(a>t+eps)next=fmin(next,a);if(b>t+eps)next=fmin(next,b);
    }
    c->next_delay=next-t;return c->next_delay>0?0:1;
}
