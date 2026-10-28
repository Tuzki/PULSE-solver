#include "pulse/software.h"
#include <math.h>
#include <stdint.h>
typedef struct Controller {
    uint64_t tick;
    double integral_v, voltage_error;
    double voltage_adc, current_adc, denominator_adc;
    double pr0, pr1, forcing, modulation;
    unsigned pwm_on, phase;
} Controller;
enum { IDLE=0, FALLING_CARRIER=1, RISING_CARRIER=2 };
static const double PERIOD=.00002;
/* Exact held-input transition of x0'=x1; x1'=u-w^2*x0. */
PULSE_SW_EXPORT void PULSE_SW_CALL controller_pr_advance(double *x,double u,double h) {
    const double w=sqrt(98696.044010893587);
    double si=sin(w*h),co=cos(w*h),sh=sin(w*h*.5);
    double x0=x[0],x1=x[1];
    x[0]=co*x0+si/w*x1+u*(2*sh*sh)/(w*w);
    x[1]=-w*si*x0+co*x1+u*si/w;
}
PULSE_SW_EXPORT const pulse_software_info *PULSE_SW_CALL pulse_software_describe(void) {
    static const pulse_software_info info={PULSE_SOFTWARE_ABI,sizeof(pulse_software_info),sizeof(Controller),3,1,0};
    return &info;
}
PULSE_SW_EXPORT int PULSE_SW_CALL control_step(pulse_software_call *c) {
    const Controller *old=(const Controller*)c->previous_state;
    Controller *s=(Controller*)c->next_state;
    *s=*old;
    if(c->trigger_flags & PULSE_SW_EXTERNAL) {
        uint64_t k=s->tick;
        if(k) {
            double x[2]={s->pr0,s->pr1};
            controller_pr_advance(x,s->forcing,PERIOD);
            s->pr0=x[0];s->pr1=x[1];
            s->integral_v+=5*s->voltage_error*PERIOD;
        }
        if(k%50==0)s->voltage_adc=c->inputs[0];
        if(k%2==0) {
            s->current_adc=c->inputs[1];
            s->denominator_adc=c->inputs[0];
        }
        s->voltage_error=500-s->voltage_adc;
        double pi=.099999999999999992*s->voltage_error+s->integral_v;
        double normalized=.0070710678118654753*c->inputs[2];
        double error=pi*normalized-s->current_adc;
        s->forcing=25*error;
        double denominator=fmax(200,s->denominator_adc);
        double bias=(k/500)%2?1:-1;
        s->modulation=2*(c->inputs[2]-s->forcing-s->pr1)/denominator+bias;
        s->pwm_on=s->modulation>=1;
        s->phase=IDLE;
        if(s->modulation>-1&&s->modulation<1) {
            s->phase=FALLING_CARRIER;
            c->next_delay=(1-s->modulation)/200000;
        }
        s->tick=k+1;
    } else if(c->trigger_flags & PULSE_SW_WAKEUP) {
        if(s->phase==FALLING_CARRIER) {
            s->pwm_on=1;s->phase=RISING_CARRIER;
            c->next_delay=(1+s->modulation)/100000;
        } else if(s->phase==RISING_CARRIER) {
            s->pwm_on=0;s->phase=IDLE;
        } else return 2;
    }
    c->outputs[0]=c->inputs[2]<0?s->pwm_on:!s->pwm_on;
    return 0;
}
