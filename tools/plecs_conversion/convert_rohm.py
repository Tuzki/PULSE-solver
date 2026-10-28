"""Conservative PLECS-to-PULSE electrical converter; unsupported live controls stop conversion."""
import argparse
import json
import math
from pathlib import Path
import re
from decimal import Decimal
from plecs_text import inventory,subs,scalar
from rohm_model import Model,Union,number


def f(x):
    if not math.isfinite(x):raise ValueError('Nonfinite generated parameter')
    return format(x,'.17g')

def time_literal(x):
    # Preserve the same binary64 value while avoiding unrelated 17-digit
    # decimal origins for clocks that are exact decimal multiples.
    return str(x) if not isinstance(x,Decimal) else format(x,'f')


class Converter:
    physical={'DCVoltageSource','ACVoltageSource','Resistor','Capacitor','Inductor','MosfetWithDiode','Diode','Transformer','Ammeter','Voltmeter'}
    passthrough={'Subsystem','Input','Output','Port','From','Goto'}
    def __init__(self,root):
        self.m=Model(root);self.lines=[];self.emitted=set();self.visiting=set();self.domains={};self.sig_names={};self.sample_depth={}
        self.approximations=['无限关断电阻用 1 GΩ；热域、热 XML 损耗与效率核算不进入电气网表。']
        self.ids={p:f'D{i:03d}' for i,p in enumerate(self.m.components,1)};self.branches={};self.channels=[]
        self.devices={p:c for p,c in self.m.components.items() if c['Type'] in self.physical}
        self.producers={}
        for path,term in self.m.signal_sources:
            c=self.m.components.get(path)
            if c and c['Type'] not in self.passthrough:
                r=self.m.pin(path,term);self.producers.setdefault(r,[])
                if (path,term) not in self.producers[r]:self.producers[r].append((path,term))
        self.electrical={};islands=Union();pairs=[]
        for path,c in self.devices.items():
            if c['Type']=='Transformer':
                n=self.vector(c['params']['n'],c['env']);terms=list(range(1,len(n)*2+1))
                groups=[(terms[i],terms[i+1]) for i in range(0,len(terms),2)]
            else:groups=[(1,2)]
            for a,b in groups:
                ra,rb=self.m.pin(path,a),self.m.pin(path,b)
                if c['Type']!='Voltmeter':islands.join(ra,rb)
                pairs.extend([ra,rb])
        grounds={}
        for p,c in self.m.components.items():
            if c['Type']=='Ground':grounds[islands.find(self.m.pin(p,1))]=self.m.pin(p,1)
        for p,c in self.devices.items():
            if c['Type'] in ('DCVoltageSource','ACVoltageSource'):
                r=self.m.pin(p,2);grounds.setdefault(islands.find(r),r)
        for r in pairs:grounds.setdefault(islands.find(r),r)
        plane_names={key:f'REF{i+1}' for i,key in enumerate(grounds)}
        self.reference_planes=[dict(reference=plane_names[key],plecs_reference_pin=pin) for key,pin in grounds.items()]
        for r in pairs:
            if r not in self.electrical:
                plane=plane_names[islands.find(r)]
                self.electrical[r]=plane if r==grounds[islands.find(r)] else f'{plane}_N{len(self.electrical):03d}'

    @staticmethod
    def vector(expr,env):
        return [number(s,env) for s in re.split(r'[,;\s]+',expr.strip('[] ')) if s]
    def node(self,p,t):return self.electrical[self.m.pin(p,t)]
    def signal(self,p,t):
        r=self.m.pin(p,t)
        if r not in self.sig_names:self.sig_names[r]=f'S{len(self.sig_names)+1:03d}'
        return self.sig_names[r]
    def add(self,*lines):self.lines.extend(lines)

    def frozen_input(self,path,term,seen=None):
        seen=set() if seen is None else set(seen);root=self.m.pin(path,term)
        if root in seen:return None
        seen.add(root);sources=self.producers.get(root,[])
        if len(sources)!=1:return None
        p,out=sources[0];c=self.m.components[p]
        if c['Type']=='Constant':return self.m.num(c,'Value')
        inputs=sorted(self.m.input_terms.get(p,set()))
        if c['Type']=='Gain' and len(inputs)==1:
            value=self.frozen_input(p,inputs[0],seen)
            return None if value is None else value*self.m.num(c,'K')
        return None

    def as_bool(self,signal,domain,tag):
        if domain=='BOOL':return signal
        if domain!='REAL':raise ValueError('Expected scalar signal '+tag)
        self.add(f'CMP_{tag}_P {tag}_P {signal} OP=GT THRESHOLD=0',
                 f'CMP_{tag}_N {tag}_N {signal} OP=LT THRESHOLD=0',
                 f'SEL_{tag}_B BOOL::{tag}_B {tag}_P {tag}_N 1')
        return tag+'_B'

    def delay_bool(self,source,tag,delay,initial,turn_on):
        if delay==0:return source
        if delay<0:raise ValueError('Negative control delay')
        self.add(f'EVENT_{tag}_BOOT {tag}_BOOT MODE=AT AT=0',
                 f'REG_{tag}_ARM {tag}_ARM MODE=SR SET={tag}_BOOT RESET={tag}_BOOT PRIORITY=SET IC=0',
                 f'SEL_{tag}_ARMED BOOL::{tag}_ARMED {tag}_ARM {initial} {source}',
                 f'EVENT_{tag}_RISE {tag}_RISE MODE=EDGE SOURCE={tag}_ARMED EDGE=RISE',
                 f'EVENT_{tag}_FALL {tag}_FALL MODE=EDGE SOURCE={tag}_ARMED EDGE=FALL')
        self.add(f'EVENT_{tag}_ON {tag}_ON MODE=DELAY SOURCE={tag}_RISE DELAY={f(delay)} POLICY='+
                 (f'REPLACE CANCEL={tag}_FALL' if turn_on else 'TRANSPORT'))
        reset=tag+'_FALL'
        if not turn_on:
            reset=tag+'_OFF';self.add(f'EVENT_{tag}_OFF {reset} MODE=DELAY SOURCE={tag}_FALL DELAY={f(delay)} POLICY=TRANSPORT')
        self.add(f'REG_{tag}_OUT {tag}_OUT MODE=SR SET={tag}_ON RESET={reset} PRIORITY=RESET IC={initial}')
        return tag+'_OUT'

    def emit(self,path,term):
        r=self.m.pin(path,term);s=self.signal(path,term)
        if r in self.emitted:
            if r in self.visiting and any(self.m.components[q]['Type']=='ZeroOrderHold' for q,t in self.producers.get(r,[])):
                raise ValueError('ZeroOrderHold feedback loop needs explicit simultaneous-sample validation '+path)
            return s,self.domains[r]
        if r in self.visiting:raise ValueError(f'Control algebraic recursion: {path}:{term}')
        sources=self.producers.get(r,[])
        if len(sources)!=1:raise ValueError(f'Unresolved/ambiguous control signal {path}:{term}: {sources}')
        p,out=sources[0];c=self.m.components[p];kind=c['Type'];k=self.ids[p];params=c['params'];self.visiting.add(r)
        inputs=sorted(self.m.input_terms.get(p,set()))
        def real(i):
            ss,dom=self.emit(p,i)
            if dom=='BOOL':self.add(f'SEL_{k}_REAL{i} {ss}_REAL {ss} 0 1');return ss+'_REAL'
            if dom!='REAL':raise ValueError('Expected scalar REAL input '+p)
            return ss
        def boolean(i):
            ss,dom=self.emit(p,i)
            return self.as_bool(ss,dom,k+'_BOOL'+str(i))
        def channels(i):
            ss,domain=self.emit(p,i)
            return ss if domain=='VECTOR' else [(ss,domain)]
        dom='REAL'
        if kind=='SignalSwitch':
            if inputs!=[2,3,4]:raise ValueError('SignalSwitch needs its three scalar inputs '+p)
            data1,d1=self.emit(p,2);control,dc=self.emit(p,4);data0,d0=self.emit(p,3)
            if d0!=d1 or d0 not in ('REAL','BOOL'):raise ValueError('SignalSwitch data domain mismatch '+p)
            criterion=int(params['Criteria']);threshold=self.m.num(c,'Threshold')
            if dc=='BOOL':
                predicates={1:lambda x:x>=threshold,2:lambda x:x>threshold,3:lambda x:x!=threshold}
                if criterion not in predicates:raise ValueError('Unknown SignalSwitch criterion '+p)
                low,high=map(int,[predicates[criterion](0),predicates[criterion](1)])
                if (low,high)==(0,1):gate=control
                else:
                    gate=k+'_SELECT';self.add(f'SEL_{k}_CONTROL BOOL::{gate} {control} {low} {high}')
            elif dc=='REAL' and criterion in (1,2):
                gate=k+'_SELECT';self.add(f'CMP_{k}_SELECT {gate} {control} OP='+('GE' if criterion==1 else 'GT')+f' THRESHOLD={f(threshold)}')
            else:raise ValueError('SignalSwitch real != threshold requires separate event semantics verification '+p)
            self.add(f'SEL_{k}_SWITCH '+('BOOL::' if d0=='BOOL' else '')+f'{s} {gate} {data0} {data1}')
            dom=d0
        elif kind=='ZeroOrderHold':
            ts=self.vector(params['Ts'],c['env'])
            if len(ts) not in (1,2) or ts[0]<=0:raise ValueError('Unsupported inherited or vector ZOH sample time '+p)
            offset=ts[1] if len(ts)==2 else 0
            if not 0<=offset<ts[0]:raise ValueError('Unsupported ZOH offset '+p)
            self.emitted.add(r);self.domains[r]='REAL'
            data,dom=self.emit(p,inputs[0])
            if dom not in ('REAL','BOOL'):raise ValueError('Only scalar ZeroOrderHold is verified '+p)
            self.domains[r]=dom;clk=k+'_CLOCK';depth=self.sample_depth.get(self.m.pin(p,inputs[0]),0)
            self.add(f'EVENT_{k}_CLOCK {clk} MODE=PERIODIC PERIOD={time_literal(ts[0])} START={time_literal(offset)}')
            for level in range(depth):
                nextclk=k+'_DELTA'+str(level)
                self.add(f'EVENT_{nextclk} {nextclk} MODE=DELAY SOURCE={clk} DELAY=0 POLICY=TRANSPORT');clk=nextclk
            self.add(f'REG_{k}_SAMPLE {dom}::{s} {data} {clk} IC=0');self.sample_depth[r]=depth+1
        elif kind=='TransferFunction':
            numerator=self.vector(params['Numerator'],c['env']);denominator=self.vector(params['Denominator'],c['env'])
            initial=self.vector(params.get('X0','0'),c['env'])
            if any(initial) or not denominator or denominator[0]==0:raise ValueError('TransferFunction currently requires zero initial state and nonzero leading denominator '+p)
            if len(numerator)>len(denominator):raise ValueError('Improper TransferFunction '+p)
            scale=denominator[0];denominator=[v/scale for v in denominator];numerator=[0]*(len(denominator)-len(numerator))+[v/scale for v in numerator]
            self.emitted.add(r);self.domains[r]='REAL';data=real(inputs[0]);order=len(denominator)-1
            if order==0:self.add(f'MATH_{k} {s} = {f(numerator[0])}*{data}')
            else:
                states=[k+'_X'+str(i) for i in range(order)]
                for i,state in enumerate(states):
                    derivative=states[i+1] if i+1<order else k+'_DX'
                    self.add(f'INT_{k}_{i} {state} {derivative} IC=0')
                self.add(f'MATH_{k}_DX {k}_DX = {data} '+' '.join(f'- ({f(denominator[order-i])})*{state}' for i,state in enumerate(states)))
                self.add(f'MATH_{k}_OUT {s} = {f(numerator[0])}*{data} '+' '.join(f'+ ({f(numerator[order-i]-numerator[0]*denominator[order-i])})*{state}' for i,state in enumerate(states)))
        elif kind=='Reference' and ' '.join(c.get('SrcComponent','').replace('\\',' ').split()).endswith('Continuous PID Controller'):
            if params.get('cont_type')!='3' or params.get('par_source')!='1' or params.get('ex_reset')!='1' or len(inputs)!=1:raise ValueError('Only internally parameterized continuous PI without reset is verified '+p)
            if self.m.num(c,'x0')!=0 or self.m.num(c,'up_limit')!=math.inf or self.m.num(c,'low_limit')!=-math.inf:raise ValueError('PI initial state or saturation requires additional mapping '+p)
            self.emitted.add(r);self.domains[r]='REAL';data=real(inputs[0]);kp=self.m.num(c,'kp');ki=self.m.num(c,'ki')
            self.add(f'MATH_{k}_DI {k}_DI = {f(ki)}*{data}',f'INT_{k}_I {k}_I {k}_DI IC=0',f'MATH_{k}_OUT {s} = {f(kp)}*{data} + {k}_I')
        elif kind=='Product':
            values=[real(i) for i in inputs];signs=params.get('Inputs','')
            if signs.isdigit():signs='*'*int(signs)
            if len(signs)!=len(values) or len(values)!=2:raise ValueError('Only scalar two-input Product is verified '+p)
            if signs not in ('**','*/'):raise ValueError('Unsupported Product input operations '+p)
            # Preserve continuous/discrete phase. The unchanged compiler must
            # reject continuous nonlinear products, never insert hidden samples.
            frozen=[self.frozen_input(p,i) for i in inputs]
            if signs=='**' and any(v is not None for v in frozen):
                index=0 if frozen[0] is not None else 1
                self.add(f'MATH_{k}_PRODUCT {s} = {f(frozen[index])}*{values[1-index]}')
            elif signs=='*/' and frozen[1] is not None:
                if frozen[1]==0:raise ValueError('Product division by frozen zero '+p)
                self.add(f'MATH_{k}_PRODUCT {s} = {values[0]}/{f(frozen[1])}')
            else:self.add(f'MATH_{k}_PRODUCT {s} {values[0]} {values[1]} OP='+('MUL' if signs=='**' else 'DIV'))
        elif kind=='Abs':
            data=real(inputs[0]);self.add(f'MATH_{k}_NEG {k}_NEG = -{data}',f'CMP_{k}_SIGN {k}_SIGN {data} OP=GE THRESHOLD=0',f'SEL_{k}_ABS {s} {k}_SIGN {k}_NEG {data}')
        elif kind=='MinMax':
            values=[real(i) for i in inputs];operation=int(params['Operation'])
            if operation not in (1,2) or len(values)<2:raise ValueError('Unsupported MinMax '+p)
            acc=values[0]
            for j,item in enumerate(values[1:]):
                tag=k+'_REDUCE'+str(j);output=s if j==len(values)-2 else tag+'_OUT'
                self.add(f'MATH_{tag}_DIFF {tag}_DIFF = {acc} - {item}',f'CMP_{tag}_SELECT {tag}_SELECT {tag}_DIFF OP=GE THRESHOLD=0')
                false,true=(acc,item) if operation==1 else (item,acc)
                self.add(f'SEL_{tag}_OUT {output} {tag}_SELECT {false} {true}');acc=output
        elif kind=='Reference' and c.get('SrcComponent','').endswith('Symmetrical PWM'):
            sampling=int(params['sampling']);hz=self.m.num(c,'fc');phase=self.m.num(c,'carrier_phaseshift',0)
            limits=self.vector(params.get('carrier_limits','[-1 1]'),c['env']);levels=self.vector(params.get('output_values','[-1 1]'),c['env'])
            if sampling not in (1,2,3,4,5,6) or hz<=0 or not 0<=phase<1 or len(limits)!=2 or len(levels)!=2:raise ValueError('Unsupported PWM configuration '+p)
            if sampling==1:phase=(phase+.75)%1
            if sampling in (5,6):phase=(phase+.5)%1
            lo,hi=limits;period=1/hz;position=(-phase)%1;up=position>=.5
            if not lo<hi:raise ValueError('Invalid PWM carrier limits '+p)
            initial=hi-2*(hi-lo)*position if not up else lo+2*(hi-lo)*(position-.5)
            period_dec=Decimal(str(period));top_dec=Decimal(str(phase))*period_dec;bottom_dec=((Decimal(str(phase))+Decimal('.5'))%1)*period_dec
            bottom=float(bottom_dec);top=float(top_dec)
            self.add(f'EVENT_{k}_BOTTOM {k}_BOTTOM MODE=PERIODIC PERIOD={time_literal(period_dec)} START={time_literal(bottom_dec)}',f'EVENT_{k}_TOP {k}_TOP MODE=PERIODIC PERIOD={time_literal(period_dec)} START={time_literal(top_dec)}',f'REG_{k}_UP {k}_UP MODE=SR SET={k}_BOTTOM RESET={k}_TOP PRIORITY=RESET IC={int(up)}',f'SEL_{k}_SLOPE {k}_SLOPE {k}_UP {f(-2*(hi-lo)*hz)} {f(2*(hi-lo)*hz)}',f'INT_{k}_CARRIER {k}_CARRIER {k}_SLOPE IC={f(initial)}')
            self.emitted.add(r);self.domains[r]='REAL';data=real(inputs[0])
            if sampling in (3,4,5):
                step=period_dec/2 if sampling==3 else period_dec;start=min(top_dec,bottom_dec) if sampling==3 else (top_dec if sampling==4 else bottom_dec)
                clk=k+'_CLOCK';depth=self.sample_depth.get(self.m.pin(p,inputs[0]),0)
                self.add(f'EVENT_{k}_SAMPLE {clk} MODE=PERIODIC PERIOD={time_literal(step)} START={time_literal(start)}')
                for level in range(depth):
                    nextclk=k+'_SAMPLE_DELTA'+str(level);self.add(f'EVENT_{nextclk} {nextclk} MODE=DELAY SOURCE={clk} DELAY=0 POLICY=TRANSPORT');clk=nextclk
                self.add(f'REG_{k}_M {k}_M {data} {clk} IC=0');data=k+'_M'
            self.add(f'MATH_{k}_DIFF {k}_DIFF = {data} - {k}_CARRIER',f'CMP_{k}_PWM {k}_ON {k}_DIFF OP=GE THRESHOLD=0')
            if sampling in (3,4,5):
                self.add(f'REG_{k}_VALID {k}_VALID MODE=SR SET={clk} RESET={clk} PRIORITY=SET IC=0',f'SEL_{k}_PWM {k}_PWM {k}_ON {f(levels[0])} {f(levels[1])}',f'SEL_{k}_OUT {s} {k}_VALID {f(levels[0])} {k}_PWM')
            else:self.add(f'SEL_{k}_OUT {s} {k}_ON {f(levels[0])} {f(levels[1])}')
        elif kind=='Step':
            when=self.m.num(c,'Time');before=self.m.num(c,'Before');after=self.m.num(c,'After')
            if when<0:self.add(f'MATH_{k} {s} = {f(after)}')
            else:self.add(f'EVENT_{k}_AT {k}_AT MODE=AT AT={time_literal(when)}',f'REG_{k}_ON {k}_ON MODE=SR SET={k}_AT RESET={k}_AT PRIORITY=SET IC=0',f'SEL_{k}_OUT {s} {k}_ON {f(before)} {f(after)}')
            self.sample_depth[r]=1
        elif kind=='SignalMux':
            s=[item for i in inputs for item in channels(i)];dom='VECTOR'
        elif kind=='SignalDemux':
            values=channels(inputs[0]);width=int(self.m.num(c,'Width'))
            if width!=len(values) or out-2 not in range(width):raise ValueError('Unsupported vector grouping '+p)
            s,dom=values[out-2]
        elif kind=='LogicalOperator':
            values=[self.as_bool(ss,domain,k+'_IN'+str(j)) for j,(ss,domain) in enumerate(item for i in inputs for item in channels(i))]
            op=int(params['Operator'])
            if op==6:
                if len(values)!=1:raise ValueError('Vector NOT semantics require explicit mapping '+p)
                self.add(f'SEL_{k}_NOT BOOL::{s} {values[0]} 1 0')
            else:
                if op not in (1,2,3,4,5) or not values:raise ValueError('Unsupported logical operator '+p)
                acc=values[0]
                for j,item in enumerate(values[1:]):
                    output=k+'_REDUCE'+str(j)
                    if op in (1,3):self.add(f'SEL_{output} BOOL::{output} {acc} 0 {item}')
                    elif op in (2,4):self.add(f'SEL_{output} BOOL::{output} {acc} {item} 1')
                    else:
                        self.add(f'SEL_{output}_NOT BOOL::{output}_NOT {item} 1 0',f'SEL_{output} BOOL::{output} {acc} {item} {output}_NOT')
                    acc=output
                self.add(f'SEL_{k}_OUT BOOL::{s} {acc} '+('1 0' if op in (3,4) else '0 1'))
            dom='BOOL'
        elif kind=='TriangleGenerator':
            low=self.m.num(c,'Min');high=self.m.num(c,'Max');hz=self.m.num(c,'f');duty=self.m.num(c,'DutyCycle');delay=self.m.num(c,'Delay')
            if not hz>0 or not 0<duty<1 or not low<high:raise ValueError('Unsupported triangle parameters '+p)
            period=1/hz;bottom=delay%period;top=(bottom+duty*period)%period;phase=(-delay/period)%1
            rising=phase<duty;initial=low+(high-low)*(phase/duty if rising else (1-phase)/(1-duty))
            self.add(f'EVENT_{k}_BOTTOM {k}_BOTTOM MODE=PERIODIC PERIOD={f(period)} START={f(bottom)}',
                     f'EVENT_{k}_TOP {k}_TOP MODE=PERIODIC PERIOD={f(period)} START={f(top)}',
                     f'REG_{k}_UP {k}_UP MODE=SR SET={k}_BOTTOM RESET={k}_TOP PRIORITY=RESET IC={int(rising)}',
                     f'SEL_{k}_SLOPE {k}_SLOPE {k}_UP {f(-(high-low)*hz/(1-duty))} {f((high-low)*hz/duty)}',
                     f'INT_{k}_TRIANGLE {s} {k}_SLOPE IC={f(initial)}')
        elif kind=='Reference' and c.get('SrcComponent','').endswith(('Pulse Delay','Turn-on Delay')):
            turn_on=c['SrcComponent'].endswith('Turn-on Delay')
            if turn_on and params.get('DeadTimeSource','1')!='1':raise ValueError('External turn-on delay unsupported '+p)
            delay=self.m.num(c,'T_d');initial=self.m.num(c,'y_init',0)
            if initial not in (0,1):raise ValueError('Non-boolean delay initial value '+p)
            outputs=[]
            for j,(ss,domain) in enumerate(channels(inputs[0])):
                tag=k+'_DELAY'+str(j);source=self.as_bool(ss,domain,tag+'_INPUT');outputs.append((self.delay_bool(source,tag,delay,int(initial),turn_on),'BOOL'))
            if len(outputs)==1:s,dom=outputs[0]
            else:s,dom=outputs,'VECTOR'
        elif kind=='PulseGenerator':
            hz=self.m.num(c,'f');duty=self.m.num(c,'DutyCycle');delay=self.m.num(c,'Delay');hi=self.m.num(c,'Hi');lo=self.m.num(c,'Lo')
            if not 0<duty<1:raise ValueError('Unsupported degenerate PWM duty '+p)
            b=s if (hi,lo)==(1,0) else s+'_BOOL'
            period_dec=Decimal(str(1/hz));on_dec=period_dec*Decimal(str(duty))
            self.add(f'EVENT_{k}_CLK {k}_CLK MODE=PERIODIC PERIOD={time_literal(period_dec)} START={time_literal(delay)}',
                     f'EVENT_{k}_OFF {k}_OFF MODE=DELAY SOURCE={k}_CLK DELAY={time_literal(on_dec)} POLICY=TRANSPORT',
                     f'REG_{k}_PWM {b} MODE=SR SET={k}_CLK RESET={k}_OFF PRIORITY=RESET IC=0')
            if b==s:dom='BOOL'
            else:self.add(f'SEL_{k}_AMPLITUDE {s} {b} {f(lo)} {f(hi)}')
            self.sample_depth[r]=1
        elif kind=='Constant':self.add(f'MATH_{k} {s} = {f(self.m.num(c,"Value"))}')
        elif kind=='SineGenerator':
            units=params.get('Units','1');frequency=self.m.num(c,'Frequency');phase=self.m.num(c,'Phase')
            if units not in ('1','2','3'):raise ValueError('Unknown sine units '+p)
            w=frequency if units=='1' else 2*math.pi*frequency
            if units=='2':phase*=2*math.pi
            elif units=='3':phase*=math.pi/180
            self.add(f'MATH_{k}_DS {s}_DS = {f(w)}*{s}_COS',f'MATH_{k}_DC {s}_DC = {-w}*{s}_SIN',
                     f'INT_{k}_S {s}_SIN {s}_DS IC={f(math.sin(phase))}',f'INT_{k}_C {s}_COS {s}_DC IC={f(math.cos(phase))}',
                     f'MATH_{k} {s} = {f(self.m.num(c,"Amplitude"))}*{s}_SIN + {f(self.m.num(c,"Bias",0))}')
        elif kind in ('Ammeter','Voltmeter'):
            self.add(f'SENSOR_{k}_SIG {s} '+(f'I {self.branches[p]}' if kind=='Ammeter' else f'V {self.node(p,1)} {self.node(p,2)}'))
        elif kind=='PlecsProbe':
            values=[]
            for probe in subs(c['block'],'Probe'):
                d=scalar(probe);target=(d.get('Path','')+'/' if d.get('Path') else '')+d['Component']
                for sig in re.findall(r'"([^"]+)"',d['Signals']):
                    for leaf,signal in self.resolve_probe(target,sig):
                        name=k+'_P'+str(len(values));self.observe(leaf,signal,name);values.append((name,'REAL'))
            if len(values)==1:s,dom=values[0]
            elif values:s,dom=values,'VECTOR'
            else:raise ValueError('Empty live probe '+p)
        elif kind=='Gain':self.add(f'MATH_{k} {s} = {f(self.m.num(c,"K"))}*{real(inputs[0])}')
        elif kind=='Sum':
            signs=params.get('Inputs',params.get('Signs','+'*len(inputs))).strip('[] ').replace('|','')
            if len(signs)!=len(inputs):raise ValueError('Unsupported Sum format '+str(params))
            self.add(f'MATH_{k} {s} = '+' '.join(sign+real(i) for sign,i in zip(signs,inputs)))
        elif kind in ('Comparator','RelationalOperator','ConstantRelationalOperator'):
            if kind=='ConstantRelationalOperator':expr=real(inputs[0]);threshold=self.m.num(c,'Threshold',self.m.num(c,'Value',0))
            else:
                expr=s+'_DIFF';self.add(f'MATH_{k}_DIFF {expr} = {real(inputs[0])} - {real(inputs[1])}');threshold=0
            op=params.get('Operator','>');op={'>':'GT','>=':'GE','<':'LT','<=':'LE','1':'EQ','2':'NE','3':'LT','4':'LE','5':'GE','6':'GT'}.get(op,op)
            if op not in ('GT','GE','LT','LE'):raise ValueError('Unsupported comparator '+str(params))
            self.add(f'CMP_{k} {s} {expr} OP={op} THRESHOLD={f(threshold)}');dom='BOOL'
        else:raise ValueError(f'Unsupported live control: {kind} {p} {c.get("SrcComponent", "")} {params}')
        if r not in self.sample_depth:self.sample_depth[r]=max((self.sample_depth.get(self.m.pin(p,i),0) for i in inputs),default=0)
        self.visiting.remove(r);self.emitted.add(r);self.sig_names[r]=s;self.domains[r]=dom;return s,dom

    def convert(self,end=None,save_dt=2e-7):
        # Branch names are assigned before emitting dependent current sensors.
        for p,c in self.devices.items():
            kind=c['Type'];prefix={'DCVoltageSource':'V','ACVoltageSource':'V','Resistor':'R','Capacitor':'C','Inductor':'L','MosfetWithDiode':'SW','Diode':'R','Transformer':'I','Ammeter':'V'}.get(kind)
            if prefix:self.branches[p]=prefix+'_'+self.ids[p]
        for p,c in self.devices.items():
            kind=c['Type'];k=self.ids[p];a,b=self.node(p,1),self.node(p,2);branch=self.branches.get(p)
            if kind=='DCVoltageSource':self.add(f'{branch} {a} {b} DC={f(self.m.num(c,"V"))}')
            elif kind=='ACVoltageSource':
                w=self.m.num(c,'w');phase=self.m.num(c,'phi');amplitude=self.m.num(c,'V')
                self.add(f'MATH_{k}_DS {k}_DS = {f(w)}*{k}_COS',f'MATH_{k}_DC {k}_DC = {f(-w)}*{k}_SIN',
                         f'INT_{k}_S {k}_SIN {k}_DS IC={f(math.sin(phase))}',f'INT_{k}_C {k}_COS {k}_DC IC={f(math.cos(phase))}',
                         f'MATH_{k}_WAVE {k}_WAVE = {f(amplitude)}*{k}_SIN',f'{branch} {a} {b} {k}_WAVE')
            elif kind=='Resistor':
                resistance=self.m.num(c,'R')
                if resistance==0:resistance=1e-6;self.approximations.append(p+' 的 0 Ω 替换为 1 µΩ。')
                self.add(f'{branch} {a} {b} R={f(resistance)}')
            elif kind=='Inductor':self.add(f'{branch} {a} {b} L={f(self.m.num(c,"L"))} IC_I={f(self.m.num(c,"i_init",0))}')
            elif kind=='Capacitor':self.add(f'{branch} {a} {b} C={f(self.m.num(c,"C"))} IC_V={f(self.m.num(c,"v_init",0))}')
            elif kind=='Ammeter':self.add(f'{branch} {a} {b} DC=0')
            elif kind=='Voltmeter':pass
            elif kind=='Diode':
                vf=self.m.num(c,'Vf');ron=self.m.num(c,'Ron')
                self.add(f'{branch} {a} {b} IV_TABLE=[(-1000000,{f((-1e6-vf)/1e9)}),({f(vf)},0),(1000000,{f((1e6-vf)/ron)})] RANGE=EXTEND')
            elif kind=='MosfetWithDiode':
                gate,dom=self.emit(p,3)
                if dom!='BOOL':self.add(f'CMP_{k}_GATE {gate}_BOOL {gate} OP=GT THRESHOLD=0');gate+='_BOOL'
                self.add(f'SENSOR_{k}_VDS {k}_VDS V {a} {b}',f'CMP_{k}_BODY {k}_BODY {k}_VDS OP=LT THRESHOLD=0',
                         f'SEL_{k}_BODY BOOL::{k}_ON {gate} {k}_BODY 1',
                         f'{branch} {a} {b} {k}_ON RON={f(self.m.num(c,"Ron"))} ROFF=1G')
            elif kind=='Transformer':
                turns=self.vector(c['params']['n'],c['env']);polarity=c['params'].get('Polarity','+')
                if len(polarity)==len(turns):turns=[v*(-1 if sign=='-' else 1) for v,sign in zip(turns,polarity)]
                self.add(f'SENSOR_{k}_VP {k}_VP V {a} {b}');current=[]
                for i,n in enumerate(turns[1:],1):
                    ratio=n/turns[0];aa,bb=self.node(p,2*i+1),self.node(p,2*i+2)
                    self.add(f'MATH_{k}_V{i} {k}_V{i} = {f(ratio)}*{k}_VP',f'V_{k}_S{i} {aa} {bb} {k}_V{i}',f'SENSOR_{k}_I{i} {k}_I{i} I V_{k}_S{i}')
                    current.append(f'({f(-ratio)})*{k}_I{i}')
                self.add(f'MATH_{k}_IP {k}_IP = '+' + '.join(current),f'{branch} {a} {b} {k}_IP')
                lm=self.m.num(c,'Lm');im=self.m.num(c,'im0',0)
                if math.isfinite(lm):self.add(f'L_{k}_MAG {a} {b} L={f(lm)} IC_I={f(im)}')
            else:raise ValueError('Unsupported electrical device '+kind+' '+p)
        self.add_observations()
        if not self.channels:raise ValueError('No electrical probe channels found')
        end=end or number(scalar(self.m.schematics['']).get('TimeSpan','Test_time'),self.m.env)
        return '# PULSE Netlist v1.1\n\n## Parameters\n\n```pulse\n.PARAM ROFF=1G\n```\n\n## Network\n\n```pulse\n'+'\n'.join(self.lines)+'\n```\n\n## Simulation\n\n```pulse\n.TRAN T_END='+f(end)+' SAVE_DT='+f(save_dt)+'\n.SAVE '+' '.join(ch['pulse'] for ch in self.channels)+'\n```\n\n## Layout\n\n```json\n{"version":"1.1","components":{},"wires":[]}\n```\n'

    def resolve_probe(self,target,signal,seen=None):
        seen=set() if seen is None else set(seen)
        if (target,signal) in seen:raise ValueError('Mask probe recursion '+str((target,signal)))
        seen.add((target,signal));c=self.m.components.get(target)
        if c:
            matches=[x for x in subs(c['block'],'MaskProbe') if scalar(x).get('Name')==signal]
            if len(matches)>1:raise ValueError('Ambiguous mask probe '+str((target,signal)))
            if matches:
                values=[]
                for probe in subs(matches[0],'Probe'):
                    d=scalar(probe);subpath='/'.join(x for x in (target,d.get('Path',''),d['Component']) if x)
                    for sig in re.findall(r'"([^"]+)"',d['Signals']):values.extend(self.resolve_probe(subpath,sig,seen))
                return values
        if target in self.devices:return [(target,signal)]
        leaves=[q for q in self.devices if q.startswith(target+'/') and self.m.components[q]['Type'] not in ('Ammeter','Voltmeter')]
        if len(leaves)!=1:raise ValueError('Probe requires explicit export mapping '+str((target,signal))+' '+str(leaves))
        return [(leaves[0],signal)]

    def observe(self,path,signal,name):
        device=self.m.components[path]
        if 'voltage' in signal.lower():self.add(f'SENSOR_{name} {name} V {self.node(path,1)} {self.node(path,2)}');return 'V'
        if 'current' in signal.lower():
            if device['Type'] in ('DCVoltageSource','ACVoltageSource'):
                self.add(f'SENSOR_{name} {name}_RAW I {self.branches[path]}',f'MATH_{name}_SIGN {name} = -{name}_RAW')
            else:self.add(f'SENSOR_{name} {name} I {self.branches[path]}')
            return 'A'
        if 'gate' in signal.lower() and device['Type']=='MosfetWithDiode':
            source,domain=self.emit(path,3)
            if domain=='BOOL':self.add(f'SEL_{name} {name} {source} 0 1')
            elif domain=='REAL':self.add(f'MATH_{name} {name} = {source}')
            else:raise ValueError('Vector gate probe '+path)
            return '1'
        raise ValueError('Unsupported electrical probe '+str((path,signal)))

    def add_observations(self):
        seen=set()
        for p,c in self.m.components.items():
            if c['Type']!='PlecsProbe' or p.startswith(('Calc','Sub/')):continue
            for probe in subs(c['block'],'Probe'):
                d=scalar(probe);target=(d.get('Path','')+'/' if d.get('Path') else '')+d['Component']
                for signal in re.findall(r'"([^"]+)"',d['Signals']):
                    if any(s in signal.lower() for s in ('temp','loss','heat','power')):continue
                    if (target,signal) in seen:continue
                    seen.add((target,signal))
                    for leaf,sig in self.resolve_probe(target,signal):
                        name='CH'+str(len(self.channels)+1).zfill(3);unit=self.observe(leaf,sig,name)
                        self.channels.append(dict(pulse=name,plecs_component=target,plecs_signal=signal,resolved_component=leaf,resolved_signal=sig,unit=unit,atol=1e-4))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('model');p.add_argument('--out',required=True);p.add_argument('--end',type=float);p.add_argument('--save-dt',type=float,default=2e-7);a=p.parse_args()
    inv,root=inventory(a.model);out=Path(a.out);out.mkdir(parents=True,exist_ok=True);converter=Converter(root)
    text=converter.convert(end=a.end or number(inv['settings']['TimeSpan'],converter.m.env),save_dt=a.save_dt)
    (out/'converted.md').write_text(text)
    (out/'conversion.json').write_text(json.dumps(dict(source=inv['source'],source_sha256=inv['sha256'],channels=converter.channels,approximations=converter.approximations,reference_planes=converter.reference_planes,parameters=converter.m.env,unresolved=converter.m.unresolved,component_map={p:dict(branch=converter.branches.get(p),type=c['Type']) for p,c in converter.devices.items()},control_map={converter.ids[p]:dict(path=p,type=c['Type'],parameters=c['params']) for p,c in converter.m.components.items() if c['Type'] not in converter.physical}),ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(channels=len(converter.channels),out=str(out)),ensure_ascii=False))
