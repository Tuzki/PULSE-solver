"""End-to-end software ABI, five-zone input and event acceptance."""
import argparse,json,math,pathlib,shutil,subprocess,sys,zipfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from read_pevt import read as read_pevt

def main():
    p=argparse.ArgumentParser();p.add_argument('--binary',type=pathlib.Path,required=True)
    p.add_argument('--cc',required=True);p.add_argument('--out',type=pathlib.Path,required=True);a=p.parse_args()
    root=pathlib.Path(__file__).resolve().parents[1];a.out.mkdir(parents=True,exist_ok=True)
    checks=[]
    def check(condition,label):
        if not condition:raise AssertionError(label)
        checks.append(label)
    def prepare(name,example):
        dest=a.out/name;dest.mkdir(exist_ok=True)
        for f in (root/'examples'/example).iterdir():
            if f.is_file():shutil.copyfile(f,dest/f.name)
        return dest/'input.md'
    def build(model):
        result=subprocess.run([sys.executable,str(root/'scripts/build_software.py'),str(model),'--cc',a.cc],capture_output=True,text=True)
        check(result.returncode==0,'build '+model.parent.name+': '+result.stderr)
    def run(model,name,*opts,success=True):
        dest=a.out/name
        result=subprocess.run([str(a.binary),str(model),'--out',str(dest),*opts],capture_output=True,text=True,timeout=30)
        (a.out/(name+'_stdout.txt')).write_text(result.stdout,encoding='utf-8')
        (a.out/(name+'_stderr.txt')).write_text(result.stderr,encoding='utf-8')
        report=dest/'simulation_report.json'
        check(report.exists(),'report '+name+': '+result.stdout+result.stderr)
        r=json.loads(report.read_text(encoding='utf-8'))
        check((result.returncode==0)==success,'status '+name+': '+str(r.get('diagnostic')))
        return r,dest
    model=prepare('rc_model','software_rc');build(model)
    report,dest=run(model,'rc_run')
    expected=1-(2*math.exp(-.125)-1)**8
    measured=2-report['software_final_outputs']['COMMAND']
    check(abs(measured-expected)<2e-11,'sampled feedback independent recurrence')
    check(report['software_states']['CONTROL']['invocations']==9,'exactly nine periodic calls')
    check(report['software_final_outputs']['CALLS']==9,'persistent per-instance state')
    check(len(report['software_modules'])==1,'compiled module identity recorded')
    overridden,_=run(model,'rc_atomic_override','--atomic-time','20f')
    check(math.isclose(overridden['T_atom'],2e-14,rel_tol=1e-15),'explicit CLI atomic time overrides netlist default')
    again,_=run(model,'rc_repeat')
    check(again['software_final_outputs']==report['software_final_outputs'],'repeat starts with fresh state')
    uncached,_=run(model,'rc_uncached','--no-mode-cache')
    check(uncached['software_final_outputs']==report['software_final_outputs'],'software outputs included in cache identity')
    fault,_=run(model,'rc_rollback','--fault','after_mode',success=False)
    check(fault['simulated_seconds']==0 and fault['software_states']['CONTROL']['invocations']==0,'failed transaction rolls back software state')
    check(fault['software_final_outputs']['CALLS']==0,'failed transaction rolls back held outputs')
    text=model.read_text(encoding='utf-8')
    dual=text.replace('SENSOR_V MEASURED V OUT 0','SENSOR_V MEASURED V OUT 0\nV_COPY IN2 0 COMMAND2\nR_COPY IN2 OUT2 R=1\nC_COPY OUT2 0 C=1 IC_V=0\nSENSOR_COPY MEASURED2 V OUT2 0')
    marker='TASK CONTROL MCU=MCU0 TRIGGER=CTRL_CLK ENTRY=controller_step INPUTS=[MEASURED] OUTPUTS=[COMMAND,CALLS] INIT_OUTPUTS=[0,0] PARAMS=[{REFERENCE}]'
    dual=dual.replace(marker,marker+'\nMCU MCU1 PROGRAM=CTRL INIT=controller_init\nTASK CONTROL2 MCU=MCU1 TRIGGER=CTRL_CLK ENTRY=controller_step INPUTS=[MEASURED2] OUTPUTS=[COMMAND2,CALLS2] INIT_OUTPUTS=[0,0] PARAMS=[{REFERENCE}]')
    dual_model=model.parent/'dual.md';dual_model.write_text(dual,encoding='utf-8')
    dual_report,_=run(dual_model,'dual_run')
    check(dual_report['software_final_outputs']['CALLS2']==9 and dual_report['software_final_outputs']['CALLS']==9,'shared code has independent instance states')
    check(dual_report['software_final_outputs']['COMMAND']==dual_report['software_final_outputs']['COMMAND2'],'same-time tasks use consistent snapshots')
    dependency=model.parent/'feedback.c';saved=dependency.read_bytes()
    try:
        dependency.write_bytes(saved+b'\n/* changed after build */\n')
        stale,_=run(model,'stale_module',success=False)
        check(stale['diagnostic']['subcode']=='SOFTWARE_STALE_MODULE','stale source is detected')
    finally:dependency.write_bytes(saved)
    extension='.dll' if sys.platform=='win32' else '.so'
    module=model.parent/'.pulse_modules'/('CTRL'+extension)
    saved_binary=module.read_bytes()
    try:
        module.write_bytes(saved_binary+b'tampered')
        stale,_=run(model,'tampered_binary',success=False)
        check(stale['diagnostic']['subcode']=='SOFTWARE_STALE_MODULE','binary hash is checked before loading')
    finally:module.write_bytes(saved_binary)
    manifest=pathlib.Path(str(module)+'.json');saved_manifest=manifest.read_bytes()
    try:
        metadata=json.loads(saved_manifest);metadata['abi']=1
        manifest.write_text(json.dumps(metadata),encoding='utf-8')
        stale,_=run(model,'wrong_manifest_abi',success=False)
        check(stale['diagnostic']['subcode']=='SOFTWARE_STALE_MODULE','manifest ABI is checked')
    finally:manifest.write_bytes(saved_manifest)
    gate=prepare('gate_model','software_gate');build(gate)
    gate_report,gate_dest=run(gate,'gate_run')
    events=[json.loads(x) for x in (gate_dest/'event_log.jsonl').read_text().splitlines()]
    calls=[e for e in events if e['kind']=='SOFTWARE_TASK']
    check(all(not(e['outputs'][0] and e['outputs'][1]) for e in calls),'complementary outputs never overlap')
    rises=[e['time_seconds_display'] for e in calls if e['outputs'][0]]
    check(rises==[.015625,.265625,.390625],'self events implement alternating carrier periods')
    check(set(e['outputs'][2] for e in calls)=={4,8},'carrier changes are retained')
    last_on=None
    for e in calls:
        h,l,_=e['outputs'];t=e['time_seconds_display']
        if not h and not l:last_on=t
        elif last_on is not None:check(t-last_on==.015625,'explicit deadtime interval')
    check(gate_report['simulated_seconds']==.5,'self-event circuit reaches full end time')
    replay_binary=a.binary.with_name('pulse-replay'+a.binary.suffix)
    for source,baseline,baseline_dest,label in [(model,report,dest,'rc'),(gate,gate_report,gate_dest,'gate')]:
        trace,trace_dest=run(source,label+'_trajectory','--output-format','trajectory')
        check(trace['software_states']==baseline['software_states'],'trajectory preserves '+label+' C instance state counters')
        check(trace['software_final_outputs']==baseline['software_final_outputs'],'trajectory preserves '+label+' held C outputs')
        check(read_pevt(trace_dest)['sections'][10][1]==(baseline_dest/'event_log.jsonl').read_bytes(),'trajectory preserves '+label+' software scheduling and events')
        replay_dest=a.out/(label+'_trajectory_replay')
        replayed=subprocess.run([str(replay_binary),str(trace_dest),'--out',str(replay_dest)],capture_output=True,text=True,timeout=30)
        check(replayed.returncode==0,'replay '+label+': '+replayed.stderr)
        with zipfile.ZipFile(baseline_dest/'out.pewave.npz') as left,zipfile.ZipFile(replay_dest/'out.pewave.npz') as right:
            arrays=[n for n in left.namelist() if n!='metadata_json.npy']
            check(all(left.read(n)==right.read(n) for n in arrays),'trajectory replay preserves '+label+' arrays byte for byte')
    fault_trace,_=run(model,'rc_trajectory_rollback','--output-format','trajectory','--fault','after_mode',success=False)
    check(fault_trace['software_states']==fault['software_states'] and fault_trace['software_final_outputs']==fault['software_final_outputs'],'trajectory output preserves C rollback on failed transaction')
    (a.out/'acceptance.json').write_text(json.dumps({'passed':True,'checks':checks,'count':len(checks)},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('PASS software domain:',len(checks),'checks')
    return 0
if __name__=='__main__':sys.exit(main())
