from pathlib import Path
import hashlib,json,subprocess,sys,socket,traceback
root=Path(r'D:\codex\pulse-solver-v1.15win')
sys.path.insert(0,str(root/'scripts'))
import windows_compare as w
np=w.np
out=root/'reports/primitive_translation_20261027'
tests=json.loads((out/'block_validation_verified/summary.json').read_text(encoding='utf-8'))
edge_audit=[]
for row in tests:
    assert row['status']=='PASS',row
    name=row['test']
    if name in ['absolute_value','transfer_first_order','transfer_resonant','continuous_pi']:continue
    with np.load(out/'block_validation_verified'/name/'comparison.npz') as z:
        a=np.flatnonzero(np.abs(np.diff(z['pulse']))>1e-4)+1;b=np.flatnonzero(np.abs(np.diff(z['plecs']))>1e-4)+1
        error=float(np.max(np.abs(z['time'][a]-z['time'][b]))) if len(a)==len(b) and len(a) else 0.0
        item={'test':name,'pulse_edges':len(a),'plecs_edges':len(b),'max_saved_edge_time_difference_s':error,'passed':len(a)==len(b) and error<=2e-6}
        edge_audit.append(item)
# Retain any edge-only difference explicitly; stable samples are not sufficient
# to call a switching waveform fully equivalent.
w.dump(out/'edge_audit.json',edge_audit)

# A minimal expression-phase refusal, independent of the PFC topology.
guard=out/'continuous_product_guard';guard.mkdir(exist_ok=True)
net=guard/'input.md'
net.write_text('# PULSE Netlist v1.1\n\n## Parameters\n```pulse\n```\n\n## Network\n```pulse\nMATH_ONE ONE = 1\nINT_X X ONE IC=1\nINT_Y Y ONE IC=2\nMATH_P P X Y OP=MUL\n```\n\n## Simulation\n```pulse\n.TRAN T_END=1m SAVE_DT=10u\n.SAVE P\n```\n\n## Layout\n```json\n{}\n```\n',encoding='utf-8')
run=subprocess.run([str(root/'build/pulse-solver.exe'),str(net),'--out',str(guard/'pulse')],capture_output=True,text=True,encoding='utf-8')
(guard/'stdout.txt').write_text(run.stdout,encoding='utf-8');(guard/'stderr.json').write_text(run.stderr,encoding='utf-8')
diagnostic=json.loads(run.stdout or run.stderr);assert diagnostic['subcode']=='CONTINUOUS_NONAFFINE'
w.dump(guard/'diagnostic.json',diagnostic)

previous=json.loads((root/'reports/island_reference_fix_20261027/other_cases/summary.json').read_text(encoding='utf-8'))
command=[sys.executable,str(root/'scripts/windows_compare.py'),'--out',str(out/'similar_cases_final')]
for c in previous['cases']:
    if c['status']=='ERROR':command+=['--case',c['case'].rsplit('-v',1)[0]]
run=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',timeout=180)
(out/'similar_cases_stdout.txt').write_text(run.stdout,encoding='utf-8');(out/'similar_cases_stderr.txt').write_text(run.stderr,encoding='utf-8')
print(run.stdout,flush=True)

case=w.LIBRARY/'cases/rohm-a002-d-boost-pfc/v001'
config=json.loads((case/'case.json').read_text(encoding='utf-8'))
source=case/config['source_model'];inv,tree=w.inventory(source);conv=w.Converter(tree);conv.convert(end=.5,save_dt=2e-7)
w.dump(out/'pfc_control_audit.json',{'products':{p:{'type':c['Type'],'parameters':c['params'],'generated_id':conv.ids[p]} for p,c in conv.m.components.items() if p in ['PFC/Product1','PFC/Gain','PFC/Voltage Compensator\n(PI)','PFC/Modulator/Divide1']},'source_sha256':w.sha(source),'parameters':conv.m.env})

# Run the untouched original PLECS independently, with a modest output grid;
# there is no valid PULSE trajectory, so this is not a comparison PASS.
dest=out/'pfc_original_plecs';dest.mkdir(exist_ok=False)
capture=w.capture_model(source,dest/'model',conv.channels)
socket.setdefaulttimeout(240)
proxy=w.xmlrpc.client.ServerProxy('http://127.0.0.1:1080')
try:
    proxy.plecs.load(capture.as_posix())
    times=np.unique(np.r_[np.arange(0,.5,50e-6),np.arange(0,.005,1e-6),np.arange(.49,.5,2e-7),.5]);times=times[(times>=0)&(times<=.5)]
    result=proxy.plecs.simulate(source.stem,{'SolverOpts':{'TimeSpan':.5,'Timeout':180,'OutputTimes':times.tolist(),'OutputTimesOption':'specified'}})
    rt=np.asarray(result['Time']);values=np.asarray(result['Values'])
    if values.shape==(len(conv.channels),len(rt)):values=values.T
    assert values.shape==(len(rt),len(conv.channels)) and np.all(np.isfinite(values))
    rs={ch['pulse']:values[:,i] for i,ch in enumerate(conv.channels)}
    np.savez_compressed(dest/'waveforms.npz',time=rt,**rs)
    w.dump(dest/'result.json',{'status':'PLECS_REFERENCE_ONLY_COMPLETED','end':float(rt[-1]),'channels':conv.channels,'samples':len(rt),'comparison_pass':False,'reason':'PULSE candidate rejected continuous nonlinear arithmetic before simulation'})
    fig,axes=w.plt.subplots(len(conv.channels),1,figsize=(13,2*len(conv.channels)),sharex=True)
    for ax,ch in zip(axes,conv.channels):
        ax.plot(rt,rs[ch['pulse']],lw=.6);ax.set_ylabel(ch['pulse']+' ('+ch['unit']+')');ax.grid(alpha=.2)
    axes[-1].set_xlabel('Time (s)');fig.suptitle('A002 Boost PFC | Original PLECS only');fig.tight_layout(rect=[0,0,1,.98]);fig.savefig(dest/'overview.png',dpi=120);w.plt.close(fig)
    print('Original PLECS completed',rt[-1],len(rt),flush=True)
except Exception:
    (dest/'error.txt').write_text(traceback.format_exc(),encoding='utf-8');print('Original PLECS error',traceback.format_exc(),flush=True)
finally:
    try:proxy.plecs.close(source.stem)
    except:pass
