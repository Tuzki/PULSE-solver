#include "pulse/software.h"
PULSE_SW_EXPORT const pulse_software_info *PULSE_SW_CALL pulse_software_describe(void){
static const pulse_software_info i={PULSE_SOFTWARE_ABI,sizeof(i),0,3,4,13};return &i;}
PULSE_SW_EXPORT int PULSE_SW_CALL control_step(pulse_software_call *c){
double t=c->time;c->outputs[0]=0;c->outputs[1]=t>=1.999999999999999e-7;c->outputs[2]=0;c->outputs[3]=t>=3.999999999999999e-7;
double times[]={2e-7,4e-7,8.333333333333334e-6,16.666666666666668e-6,.0021};
for(int i=0;i<5;i++)if(times[i]>t+1e-18){c->next_delay=times[i]-t;break;}return 0;}
