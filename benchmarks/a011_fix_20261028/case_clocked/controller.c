#include "pulse/software.h"
#include <math.h>
#include <stdint.h>
typedef struct {double last,next_adc,vi,ve,held_i,held_v,pr0,pr1,pe,mod,top,due[4];int raw[4],gate[4];uint64_t adc_tick,carrier_tick;} State;
PULSE_SW_EXPORT const pulse_software_info *PULSE_SW_CALL pulse_software_describe(void) {
    static const pulse_software_info i={PULSE_SOFTWARE_ABI,sizeof(i),sizeof(State),3,4,13};return &i;
}
PULSE_SW_EXPORT int PULSE_SW_CALL control_step(pulse_software_call *c) {
    State *s=c->next_state;const double *p=c->parameters;double t=c->time,h=t-s->last,T=1/p[5],w=2*3.14159265358979323846*p[6],eps=2e-15;int j;
    if(c->invocation==0)for(j=0;j<4;j++)s->due[j]=INFINITY;
    if(h>0){double co=cos(w*h),si=sin(w*h),a=s->pr0,b=s->pr1;
        s->pr0=co*a+si/w*b+(1-co)/(w*w)*p[4]*s->pe;
        s->pr1=-w*si*a+co*b+si/w*p[4]*s->pe;s->vi+=p[2]*s->ve*h;}
    s->last=t;
    if(t>=s->next_adc-eps){
        if(s->adc_tick%(uint64_t)llround(p[8]/p[10])==0)s->ve=p[0]-c->inputs[0];
        if(s->adc_tick%(uint64_t)llround(p[7]/p[10])==0){s->held_i=c->inputs[1];s->held_v=c->inputs[0];}
        s->pe=(p[1]*s->ve+s->vi)*c->inputs[2]/p[9]-s->held_i;
        s->next_adc=(++s->adc_tick)*p[10];
    }
    if(c->invocation==0||t>=s->top-eps){
        double line=(s->carrier_tick/(uint64_t)llround(p[5]/(2*p[6])))%2?1:-1;
        s->mod=fmin(1,fmax(-1,2*(c->inputs[2]-(p[3]*s->pe+s->pr1))/fmax(200,s->held_v)+line));s->top=(++s->carrier_tick)*T;
    }
    double start=(s->carrier_tick-1)*T;
    double phase=(t-start)/T,a=(1-s->mod)*.25,b=(3+s->mod)*.25;
    int positive=(s->mod>=1)||(phase>=a-1e-10&&phase<b-1e-10);
    s->raw[0]=positive;s->raw[1]=!positive;s->raw[2]=c->inputs[2]<0;s->raw[3]=c->inputs[2]>0;
    for(j=0;j<4;j++){
        if(!s->raw[j]){s->gate[j]=0;s->due[j]=INFINITY;}
        else if(!s->gate[j]&&!isfinite(s->due[j]))s->due[j]=t+(j<2?p[11]:p[12]);
        if(t>=s->due[j]-eps){s->gate[j]=1;s->due[j]=INFINITY;}
        c->outputs[j]=s->gate[j];
    }
    double next=fmin(s->next_adc,s->top),ta=start+a*T,tb=start+b*T;
    if(ta>t+eps)next=fmin(next,ta);if(tb>t+eps)next=fmin(next,tb);
    for(j=0;j<4;j++)if(s->due[j]>t+eps)next=fmin(next,s->due[j]);
    c->next_delay=next-t;return c->next_delay>0?0:1;
}
