#include "pulse/software.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
extern int PULSE_SW_CALL control_step(pulse_software_call *);
int main(void){
 const pulse_software_info *info=pulse_software_describe();
 void *previous=calloc(1,info->state_bytes),*next=calloc(1,info->state_bytes);
 double par[8]={800,0,0,1,0,12000,1e-6,1./24000},input[7]={800,100,-100,0,0,0,0},outputs[6];
 double t=0;int half=0,full=0;
 for(int step=0;step<200;step++){
  if(t>=1./12000-1e-12)input[4]=5;
  memcpy(next,previous,info->state_bytes);
  pulse_software_call call={PULSE_SOFTWARE_ABI,sizeof(call),t,(uint64_t)step,input,7,par,8,previous,next,info->state_bytes,outputs,6,0,PULSE_SW_WAKEUP};
  if(control_step(&call)||!(call.next_delay>0))return 1;
  if(fabs(t-1./24000)<1e-12)half=1;
  if(fabs(t-1./12000)<1e-12){full=1;if(outputs[1]!=0){fputs("PWM sampled stale current error\n",stderr);return 1;}break;}
  memcpy(previous,next,info->state_bytes);t+=call.next_delay;
  if(t>1./12000+1e-12)break;
 }
 free(previous);free(next);
 if(!half||!full){fputs("noncommensurate current deadline was skipped\n",stderr);return 1;}
 puts("PASS independent 41.6667 us current sampling and refreshed error before PWM latch");return 0;
}
