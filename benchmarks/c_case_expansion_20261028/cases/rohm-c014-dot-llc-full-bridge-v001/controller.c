#define DEADTIME 9.9999999999999995e-08
#include "pulse/software.h"
#include <math.h>
#include <string.h>
/* Exact held-error transition of the original cascaded Type-2 compensator.
   Only the voltage acquisition is sampled; switching edges retain event times. */
typedef struct { double t,x,z,error,next_adc,bottom,period; double due[2]; int phase,raw[2],gate[2]; } State;
PULSE_SW_EXPORT const pulse_software_info *PULSE_SW_CALL pulse_software_describe(void) {
    static const pulse_software_info i={PULSE_SOFTWARE_ABI,sizeof(i),sizeof(State),1,2,8};return &i;
}
PULSE_SW_EXPORT int PULSE_SW_CALL control_step(pulse_software_call *c) {
    State *s=c->next_state; const double *p=c->parameters;double t=c->time,h=t-s->t;
    const double eps=2e-15;int j;
    if(c->invocation==0){s->next_adc=0;s->bottom=0;s->phase=0;s->due[0]=s->due[1]=INFINITY;}
    if(h>0){double k=p[2]*s->error,e=exp(-p[3]*h);
        s->z=s->x+k*(h-1/p[3])+(s->z-s->x+k/p[3])*e;s->x+=k*h;}
    s->t=t;
    if(t>=s->next_adc-eps){s->error=p[0]-p[1]*c->inputs[0];s->next_adc=(floor((t+eps)/p[6])+1)*p[6];}
    if(t>=s->bottom-eps){
        double a=p[3]/p[4],out=a*s->x+(1-a)*s->z;
        double scale=fmin(p[7],fmax(.3,1.5-out));
        /* Half-bridge lower limit is supplied through an explicit macro. */
#ifdef HALF_BRIDGE
        scale=fmax(.7,scale);
#endif
        s->period=1/(p[5]*scale);s->bottom=t+s->period;s->phase=0;
        s->raw[0]=1;s->raw[1]=0;
    }else if(s->phase==0 && t>=s->bottom-.75*s->period-eps){s->phase=1;s->raw[0]=0;s->raw[1]=1;}
    else if(s->phase==1 && t>=s->bottom-.25*s->period-eps){s->phase=2;s->raw[0]=1;s->raw[1]=0;}
    for(j=0;j<2;++j){
        if(!s->raw[j]){s->gate[j]=0;s->due[j]=INFINITY;}
        else if(!s->gate[j]&&!isfinite(s->due[j]))s->due[j]=t+DEADTIME;
        if(t>=s->due[j]-eps){s->gate[j]=1;s->due[j]=INFINITY;}
        c->outputs[j]=s->gate[j];
    }
    double next=fmin(s->next_adc,s->bottom);
    if(s->phase==0)next=fmin(next,s->bottom-.75*s->period);
    if(s->phase==1)next=fmin(next,s->bottom-.25*s->period);
    for(j=0;j<2;++j)if(s->due[j]>t+eps)next=fmin(next,s->due[j]);
    c->next_delay=next-t;return c->next_delay>0?0:1;
}
