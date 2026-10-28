#include "pulse/software.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
extern int PULSE_SW_CALL control_step(pulse_software_call *);
int main(void){
 const pulse_software_info *info=pulse_software_describe();
 double in[7]={800,100,-100,0,0,0,0},par[8]={800,0,0,0,0,20000,1e-6,25e-6},out[6];
 const double times[4]={0,13e-6,26e-6,40e-6};
 const int expected[4][6]={{1,1,1,1,1,1},{1,0,0,1,0,0},{1,0,0,1,0,0},{1,1,1,1,1,1}};
 void *previous=calloc(1,info->state_bytes),*next=calloc(1,info->state_bytes);
 for(int i=0;i<4;i++){
  memcpy(next,previous,info->state_bytes);
  pulse_software_call call={PULSE_SOFTWARE_ABI,sizeof(call),times[i],i,in,7,par,8,previous,next,info->state_bytes,out,6,0,PULSE_SW_WAKEUP};
  if(control_step(&call)!=0||!(call.next_delay>0))return 1;
  for(int k=0;k<6;k++)if(out[k]!=expected[i][k]){fprintf(stderr,"wrong gate %d at %.9g: %.0f expected %d\n",k+1,times[i],out[k],expected[i][k]);return 1;}
  memcpy(previous,next,info->state_bytes);
 }
 free(previous);free(next);puts("PASS actual C controller: OR truth, both PWM phases, zero voltage and all-ON startup");return 0;
}
