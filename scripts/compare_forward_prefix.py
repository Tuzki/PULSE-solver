"""Compare a committed prefix without relabeling the incomplete full run PASS."""
from pathlib import Path
import json,socket,sys,time,xmlrpc.client
root=Path(r'D:\codex\pulse-solver-v1.15win')
sys.path.insert(0,str(root/'scripts'))
import windows_compare as w
np=w.np
batch=root/'reports/island_reference_fix_20261027'
prior=batch/'other_cases/rohm-c011-d-forward-v001'
out=batch/'forward_prefix_02';out.mkdir(exist_ok=False)
case=w.LIBRARY/'cases/rohm-c011-d-forward/v001'
config=json.loads((prior/'case_snapshot.json').read_text(encoding='utf-8'))
channels=json.loads((prior/'channel_mapping.json').read_text(encoding='utf-8'))
schedule=json.loads((prior/'comparison_schedule.json').read_text(encoding='utf-8'))['schedule']
source=case/config['source_model']
pt,ps=w.read_wave(next((prior/'pulse').glob('*.npz')))
assert pt[-1]>.2
capture=w.capture_model(source,out/'plecs_model',channels)
socket.setdefaulttimeout(240)
proxy=xmlrpc.client.ServerProxy('http://127.0.0.1:1080')
try:
    try:proxy.plecs.close(source.stem)
    except xmlrpc.client.Fault:pass
    proxy.plecs.load(capture.as_posix())
    outputs=np.unique(np.r_[np.arange(0,.005,2e-7),.005,np.arange(.1,.2,2e-7),.1,.2])
    outputs=outputs[(outputs>=0)&(outputs<=.2)]
    result=proxy.plecs.simulate(source.stem,{'SolverOpts':{'TimeSpan':.2,'Timeout':180,'OutputTimes':outputs.tolist(),'OutputTimesOption':'specified'}})
finally:proxy.plecs.close(source.stem)
rt=np.asarray(result['Time']);values=np.asarray(result['Values'])
if values.shape==(len(channels),len(rt)):values=values.T
assert values.shape==(len(rt),len(channels)) and np.all(np.isfinite(values))
rs={ch['pulse']:values[:,i] for i,ch in enumerate(channels)}
np.savez_compressed(out/'plecs_waveforms.npz',time=rt,**rs)
window=[.1,.2]
mask=(rt>=window[0])&(rt<=window[1])
actual=w.mode_statistics(pt,ps,[ch['pulse'] for ch in channels],window,schedule)
reference=w.mode_statistics(rt[mask],{n:v[mask] for n,v in rs.items()},[ch['pulse'] for ch in channels],window,schedule)
rows=[]
for ch in channels:
    n=ch['pulse']
    for metric in ('rms','max','mean'):
        r=reference[n][metric];a=actual[n][metric];allowed=ch['atol']+.01*abs(r)
        rows.append({'channel':n,'metric':metric,'plecs':r,'pulse':a,'abs_error':abs(a-r),'allowed_error':allowed,'passed':abs(a-r)<=allowed})
w.dump(out/'statistics.json',rows)
w.plots(out,pt,ps,rt,rs,channels,.2)
summary={'status':'PREFIX_STATISTICS_PASS_VISUAL_REVIEW_PENDING' if all(x['passed'] for x in rows) else 'PREFIX_STATISTICS_FAIL',
 'compared_window':window,'prefix_view_end':.2,'original_requested_end':.4,'full_run_status':'STOPPED_UNRESOLVED',
 'full_run_stop_reason':'TRANSACTION_BUDGET','full_run_effective_end':json.loads((prior/'result.json').read_text(encoding='utf-8'))['effective_end'],
 'statistics_passed':sum(x['passed'] for x in rows),'statistics_total':len(rows),'channels':len(channels),
 'pulse_run':'Reuse only the committed prefix from the unmodified-budget 0.4 s attempt; no PULSE rerun or budget change',
 'source_sha256':w.sha(source),'capture_model_sha256':w.sha(capture)}
w.dump(out/'summary.json',summary)
print(json.dumps(summary,indent=2),flush=True)
