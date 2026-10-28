from pathlib import Path
import copy,importlib.util,json,os,socket,subprocess,sys,traceback
root=Path(r'D:\codex\pulse-solver-v1.15win')
sys.path.insert(0,str(root/'scripts'))
import windows_compare as w
spec=importlib.util.spec_from_file_location('primitive_converter',root/'tools/plecs_conversion/convert_rohm.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
np=w.np
out=root/'reports/primitive_translation_20261027/block_validation_delivery'
out.mkdir(exist_ok=False)
base=next((w.LIBRARY/'cases/rohm-a002-d-boost-pfc/v001/source/model').glob('*.plecs'))
_,basetree=w.inventory(base);model=w.Converter(basetree).m
pi=copy.deepcopy(next(c['block'] for c in model.components.values() if c['Type']=='Reference' and c['params'].get('cont_type')=='3'))

def component(kind,name,params=None,source=None):
    text=f'Component {{\nType {kind}\n'
    if source:text+='SrcComponent '+json.dumps(source)+'\n'
    text+=f'Name "{name}"\nShow off\nPosition [1000,1000]\nDirection right\nFlipped off\nLabelPosition south\n'
    for key,value in (params or {}).items():text+='Parameter {\nVariable '+json.dumps(key)+'\nValue '+json.dumps(str(value))+'\nShow off\n}\n'
    return w.parse((text+'}\n').splitlines())[0][0]
def wire(src,st,dst,dt):return w.parse(f'Connection {{\nType Signal\nSrcComponent "{src}"\nSrcTerminal {st}\nDstComponent "{dst}"\nDstTerminal {dt}\n}}'.splitlines())[0][0]
def const(name,value):return component('Constant',name,{'Value':value})
def step(name,before,after,t=.00035):return component('Step',name,{'Time':t,'Before':before,'After':after})

fixtures=[]
fixtures.append(('absolute_value',[component('SineGenerator','A',{'Units':1,'Frequency':6283.185307179586,'Phase':.3,'Amplitude':2,'Bias':0}),component('Abs','Unit')],[wire('A',1,'Unit',1)],'Unit',2,True))
for criterion in [1,2]:
    fixtures.append((f'switch_criterion_{criterion}',[const('A',11),step('Control',-1,1),const('B',22),component('SignalSwitch','Unit',{'Criteria':criterion,'Threshold':0})],
        [wire('A',1,'Unit',2),wire('Control',1,'Unit',4),wire('B',1,'Unit',3)],'Unit',1,False))
    fixtures.append((f'switch_zero_criterion_{criterion}',[const('A',11),step('Control',0,1),const('B',22),component('SignalSwitch','Unit',{'Criteria':criterion,'Threshold':0})],[wire('A',1,'Unit',2),wire('Control',1,'Unit',4),wire('B',1,'Unit',3)],'Unit',1,False))
fixtures.append(('switch_boolean_data',[step('A',-1,1),component('ConstantRelationalOperator','AB',{'Operator':6,'Threshold':0}),component('LogicalOperator','B',{'Operator':6,'Inputs':1}),step('Control',-1,1,.0013),component('ConstantRelationalOperator','CB',{'Operator':6,'Threshold':0}),component('SignalSwitch','Unit',{'Criteria':2,'Threshold':0})],[wire('A',1,'AB',1),wire('AB',2,'B',2),wire('Control',1,'CB',1),wire('AB',2,'Unit',2),wire('B',1,'Unit',3),wire('CB',2,'Unit',4)],'Unit',1,False))
for operator in range(1,7):
    parts=[step('A',0,1,.0004),component('PulseGenerator','B',{'Hi':1,'Lo':0,'f':1000,'DutyCycle':.5,'Delay':.0002}),component('LogicalOperator','Unit',{'Operator':operator,'Inputs':1 if operator==6 else 2})]
    edges=[wire('A',1,'Unit',2)]+([] if operator==6 else [wire('B',1,'Unit',3)])
    fixtures.append((f'logical_operator_{operator}',parts,edges,'Unit',1,False))
for operator in range(3,7):
    parts=[const('Minus',-1),step('A',0,1,.001),step('B',0,1,.002),component('Sum','Sum',{'Inputs':'+++'}),component('ConstantRelationalOperator','Unit',{'Operator':operator,'Threshold':0})]
    edges=[wire('Minus',1,'Sum',2),wire('A',1,'Sum',3),wire('B',1,'Sum',4),wire('Sum',1,'Unit',1)]
    fixtures.append((f'constant_comparison_{operator}',parts,edges,'Unit',2,False))
for operation in [1,2]:
    fixtures.append((f'minmax_{operation}',[step('A',-2,3),const('B',1),component('MinMax','Unit',{'Operation':operation,'Inputs':2})],[wire('A',1,'Unit',2),wire('B',1,'Unit',3)],'Unit',1,False))
fixtures.append(('zoh',[step('A',0,3),component('ZeroOrderHold','Unit',{'Ts':.0002})],[wire('A',1,'Unit',1)],'Unit',2,False))
fixtures.append(('zoh_cascade',[step('A',0,3),component('ZeroOrderHold','First',{'Ts':.0002}),component('ZeroOrderHold','Unit',{'Ts':.0002})],[wire('A',1,'First',1),wire('First',2,'Unit',1)],'Unit',2,False))
fixtures.append(('zoh_step_at_sample',[step('A',0,3,.0004),component('ZeroOrderHold','Unit',{'Ts':.0002})],[wire('A',1,'Unit',1)],'Unit',2,False))
for name,num,den in [('transfer_first_order','[1]','[0.001 1]'),('transfer_resonant','[1 0]','[1 0 (2*pi*50)^2]')]:
    fixtures.append((name,[const('A',1),component('TransferFunction','Unit',{'Numerator':num,'Denominator':den,'X0':0})],[wire('A',1,'Unit',1)],'Unit',2,True))
pi_block={'key':'Component','children':pi}
for field in pi:
    if field['key']=='Name':field['raw']='"Unit"'
fixtures.append(('continuous_pi',[const('A',1),pi_block],[wire('A',1,'Unit',1)],'Unit',2,True))
for sampling in range(1,7):
    fixtures.append((f'pwm_sampling_{sampling}',[step('A',.2,-.4),component('Reference','Unit',{'sampling':sampling,'fc':1000,'carrier_phaseshift':0,'carrier_limits':'[-1 1]','output_values':'[-1 1]'},'Components/Control/Modulators/Symmetrical PWM')],[wire('A',1,'Unit',2)],'Unit',1,False))
for sampling in [2,4,5]:
    fixtures.append((f'pwm_phase_sampling_{sampling}',[step('A',.2,-.4),component('Reference','Unit',{'sampling':sampling,'fc':1000,'carrier_phaseshift':.125,'carrier_limits':'[-1 1]','output_values':'[-1 1]'},'Components/Control/Modulators/Symmetrical PWM')],[wire('A',1,'Unit',2)],'Unit',1,False))
fixtures.append(('held_product',[step('A',2,3),const('B',4),component('ZeroOrderHold','Held',{'Ts':.0002}),component('Product','Unit',{'Inputs':'2'})],[wire('A',1,'Held',1),wire('Held',2,'Unit',2),wire('B',1,'Unit',3)],'Unit',1,False))
fixtures.append(('held_product_two_samples',[step('A',2,3),step('B',4,5,.0007),component('ZeroOrderHold','HA',{'Ts':.0002}),component('ZeroOrderHold','HB',{'Ts':.0003}),component('Product','Unit',{'Inputs':'2'})],[wire('A',1,'HA',1),wire('B',1,'HB',1),wire('HA',2,'Unit',2),wire('HB',2,'Unit',3)],'Unit',1,False))
fixtures.append(('held_product_same_clock',[step('A',2,3),step('B',4,5,.0007),component('ZeroOrderHold','HA',{'Ts':.0002}),component('ZeroOrderHold','HB',{'Ts':.0002}),component('Product','Unit',{'Inputs':'2'})],[wire('A',1,'HA',1),wire('B',1,'HB',1),wire('HA',2,'Unit',2),wire('HB',2,'Unit',3)],'Unit',1,False))
fixtures.append(('continuous_affine_product',[component('SineGenerator','A',{'Units':1,'Frequency':6283.185307179586,'Phase':.3,'Amplitude':2,'Bias':0}),const('B',2),component('Product','Unit',{'Inputs':'2'})],[wire('A',1,'Unit',2),wire('B',1,'Unit',3)],'Unit',1,True))
socket.setdefaulttimeout(30)
proxy=w.xmlrpc.client.ServerProxy('http://127.0.0.1:1080')
results=[]
for name,components,connections,signal,term,continuous in fixtures:
    dest=out/name;dest.mkdir()
    entry={'test':name}
    try:
        output=component('Output','OUT',{'Index':1,'Width':1})
        # Keep every unconnected fixture separate, with enough schematic space.
        for index,c in enumerate(components+[output]):
            for field in c['children']:
                if field['key']=='Position':field['raw']=f'[{1000+index*200},1000]'
        header=w.parse(f'''Plecs {{
Name "{name}"
Version "4.8"
CircuitModel "ContStateSpace"
StartTime "0"
TimeSpan "0.004"
Solver "radau"
MaxStep "1e-6"
RelTol "1e-7"
InitializationCommands "Rv_Kp=2; Rv_Ki=3;"
Terminal {{
Type Output
Index "1"
}}
Schematic {{
Location [0,0;1800,1200]
ZoomFactor 1
SliderPosition [0,0]
ShowBrowser off
BrowserWidth 100
}}
}}'''.splitlines())[0]
        schematic=w.subs(header[0]['children'],'Schematic')[0]
        # Native PLECS requires one Connection with Branch nodes for fan-out.
        by_source={}
        for edge in connections+[wire(signal,term,'OUT',1)]:
            data=w.scalar(edge['children']);key=(data['SrcComponent'],data['SrcTerminal'])
            by_source.setdefault(key,[]).append(edge)
        joined=[]
        for (src,terminal),edges in by_source.items():
            if len(edges)==1:joined.extend(edges);continue
            block=w.parse(f'Connection {{\nType Signal\nSrcComponent "{src}"\nSrcTerminal {terminal}\n}}'.splitlines())[0][0]
            for edge in edges:
                block['children'].append({'key':'Branch','children':[v for v in edge['children'] if v['key'] in ('DstComponent','DstTerminal')]})
            joined.append(block)
        schematic.extend(components+[output]+joined)
        path=dest/(name+'.plecs');path.write_text(w.serialize(header),encoding='utf-8')
        _,tree=w.inventory(path);converter=module.Converter(tree)
        sig,domain=converter.emit('OUT',1)
        network='\n'.join(converter.lines)
        text='# PULSE Netlist v1.1\n\n## Parameters\n```pulse\n```\n\n## Network\n```pulse\n'+network+'\n```\n\n## Simulation\n```pulse\n.TRAN T_END=.004 SAVE_DT=1u\n.SAVE '+sig+'\n```\n\n## Layout\n```json\n{}\n```\n'
        net=dest/'translated.md';net.write_text(text,encoding='utf-8')
        run=subprocess.run([str(root/'build/pulse-solver.exe'),str(net),'--out',str(dest/'pulse')],capture_output=True,text=True,encoding='utf-8',timeout=30)
        (dest/'pulse_stdout.json').write_text(run.stdout,encoding='utf-8');(dest/'pulse_stderr.txt').write_text(run.stderr,encoding='utf-8')
        if run.returncode:raise RuntimeError('PULSE '+run.stdout[:1200])
        pt,ps=w.read_wave(next((dest/'pulse').glob('*.npz')));py=ps[sig]
        proxy.plecs.load(path.as_posix())
        try:reference=proxy.plecs.simulate(name,{'SolverOpts':{'OutputTimes':pt.tolist(),'OutputTimesOption':'specified'}})
        finally:proxy.plecs.close(name)
        rt=np.asarray(reference['Time']);ry=np.asarray(reference['Values']).reshape(-1)
        assert np.array_equal(rt,pt)
        np.savez_compressed(dest/'comparison.npz',time=pt,pulse=py,plecs=ry)
        stable=np.ones(len(pt),dtype=bool)
        if not continuous:
            # Ignore the single saved point on either side of a discontinuity,
            # while still detecting wrong phases, selections or sample delays.
            jumps=np.flatnonzero((np.abs(np.diff(py))>1e-4)|(np.abs(np.diff(ry))>1e-4))
            for j in jumps:stable[max(0,j-1):min(len(pt),j+3)]=False
        error=float(np.max(np.abs(py[stable]-ry[stable])))
        entry.update(status='PASS' if error<1e-4 else 'FAIL',max_abs_error=error,stable_samples=int(stable.sum()),total_samples=len(pt))
    except Exception as exc:
        (dest/'error.txt').write_text(traceback.format_exc(),encoding='utf-8');entry.update(status='ERROR',error=str(exc))
    results.append(entry);w.dump(out/'summary.json',results);print(json.dumps(entry),flush=True)
