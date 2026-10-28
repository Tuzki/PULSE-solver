"""Replay all six requested cases, preserving model/time/tolerance evidence."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys,time,re
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import windows_compare as w
np=w.np

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def five_zone(text):
    blocks={}
    for name,body in re.findall(r'^##\s+(Parameters|Network|Simulation|Layout)\s*\n(.*?)(?=^##\s|\Z)',text,re.M|re.S):
        match=re.search(r'```(?:pulse|json)\s*\n(.*?)```',body,re.S)
        blocks[name]=match[1] if match else ''
    assert all(n in blocks for n in ('Parameters','Network','Simulation','Layout'))
    parts=['# PULSE Netlist v1.2pre\n']
    for name,body in [('参数域',blocks['Parameters']),('仿真参数配置',blocks['Simulation']),('电气域连接网表',blocks['Network']),('虚拟MCU配置域',''),('代码域','')]:
        parts.append('## '+name+'\n```pulse\n'+body+'```\n')
    return '\n'.join(parts)

def main():
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,default=Path(r'D:\codex\pulse-solver-v1.15win'))
    p.add_argument('--evidence',type=Path,default=Path(r'D:\codex\using plecs'))
    p.add_argument('--out',type=Path,default=ROOT/'reports/stage_acceptance');p.add_argument('--case',action='append')
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    binary=ROOT/'build/pulse-solver.exe';cases=[]
    for folder,name in [('buck_boost_live','rohm-c006-d-buck-v001'),('buck_boost_live','rohm-c002-d-boost-v002'),('flyback_live','rohm-c010-d-flyback-v002')]:
        base=a.baseline/'reports/island_reference_fix_20261027'/folder/name
        cases.append((name,base,base/'pulse',.3,base/'statistics.json',base/'plecs_waveforms.npz'))
    for name in ('rohm-b004-d-single-phase-inverter-v001','rohm-b004-dot-single-phase-inverter-v001'):
        base=a.evidence/'unlock_sweep_20261027'/name/'full_body_pwa'
        tight='-dot-' in name
        cases.append((name,base,base/'native/pulse',.5,base/('tight_statistics.json' if tight else 'statistics.json'),base/('plecs_tight_waveforms.npz' if tight else 'plecs_waveforms.npz')))
    base=a.evidence/'frozen_zoh_sweep_20261027/ts_20us'
    cases.append(('rohm-a002-d-boost-pfc-v001-zoh20us',base,base/'pulse',.08,None,a.evidence/'frozen_zoh_sweep_20261027/plecs/zoh_20us/waveforms.npz'))
    summary={'solver_sha256':sha(binary),'cases':[],'baseline_sources_unchanged':False,
      'reference_policy':'Reuse previously validated, immutable PLECS captures and their exact statistics tolerances; no new PLECS run claimed.'}
    def save():w.dump(a.out/'summary.json',summary)
    for name,base,oldrun,duration,statpath,refpath in cases:
        if a.case and name not in a.case:continue
        print('START',name,flush=True);dest=a.out/name;dest.mkdir(exist_ok=True)
        source=base/'input.md';oldwave=oldrun/'out.pewave.npz'
        if not oldwave.exists():
            choices=list(base.rglob('out.pewave.npz'))
            if len(choices)!=1:raise ValueError('ambiguous baseline waveform '+str(base)+' '+str(choices))
            oldwave=choices[0]
        model=dest/'input.md';model.write_text(five_zone(source.read_text(encoding='utf-8-sig')),encoding='utf-8')
        started=time.perf_counter()
        result=subprocess.run([str(binary),str(model),'--out',str(dest/'pulse')],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=600)
        (dest/'stdout.txt').write_text(result.stdout,encoding='utf-8');(dest/'stderr.txt').write_text(result.stderr,encoding='utf-8')
        row={'case':name,'returncode':result.returncode,'wall_seconds':time.perf_counter()-started,
          'legacy_input_sha256':sha(source),'five_zone_input_sha256':sha(model),'baseline_wave_sha256':sha(oldwave),
          'reference_sha256':sha(refpath),'target_seconds':duration}
        report=dest/'pulse/simulation_report.json'
        if not report.exists():
            row.update(passed=False,diagnostic=result.stdout+result.stderr);summary['cases'].append(row);save();continue
        r=json.loads(report.read_text(encoding='utf-8'));row.update(status=r['status'],simulated_seconds=r['simulated_seconds'],transactions=r['transactions'],diagnostic=r.get('diagnostic'),transaction_limit=r.get('transaction_limit'))
        if result.returncode or r['simulated_seconds']!=duration:
            row['passed']=False;summary['cases'].append(row);save();print('FAIL',name,row,flush=True);continue
        t,signals=w.read_wave(dest/'pulse/out.pewave.npz');ot,old=w.read_wave(oldwave)
        row['same_time_grid']=np.array_equal(t,ot);row['same_channels']=signals.keys()==old.keys()
        row['baseline_waveform_errors']={}
        if row['same_time_grid'] and row['same_channels']:
            for channel,y in old.items():
                error=signals[channel]-y;scale=max(float(np.sqrt(np.mean(y*y))),float(np.ptp(y)),1e-9)
                row['baseline_waveform_errors'][channel]={'max_abs':float(np.max(np.abs(error))),'nrmse':float(np.sqrt(np.mean(error*error))/scale),'array_equal':np.array_equal(signals[channel],y)}
        row['all_saved_arrays_equal']=bool(row['baseline_waveform_errors']) and all(v['array_equal'] for v in row['baseline_waveform_errors'].values())
        comparisons=[]
        if statpath:
            template=json.loads(statpath.read_text(encoding='utf-8'));schedule=None
            if (base/'case_snapshot.json').exists():schedule=json.loads((base/'case_snapshot.json').read_text(encoding='utf-8')).get('switching_schedule')
            cached={}
            for item in template:
                channel=item['channel'];window=item.get('window_s',item.get('window'));key=tuple(window)
                if key not in cached:
                    names=sorted({x['channel'] for x in template if x.get('window_s',x.get('window'))==window})
                    cached[key]=w.mode_statistics(t,signals,names,window,schedule) if schedule else {n:w.measure(t,signals[n],window) for n in names}
                actual=cached[key][channel][item['metric']];ref=item['plecs'];allowed=item.get('allowed_error',item.get('tolerance'))
                comparisons.append({'channel':channel,'window':window,'metric':item['metric'],'pulse':actual,'plecs':ref,'allowed_error':allowed,'abs_error':abs(actual-ref),'passed':abs(actual-ref)<=allowed})
            w.dump(dest/'statistics.json',comparisons)
            row['statistics_passed']=sum(x['passed'] for x in comparisons);row['statistics_total']=len(comparisons)
        with np.load(refpath) as z:
            rt=z['time'];rs={k:z[k] for k in z.files if k!='time'}
        row['plecs_waveform_errors']={}
        for channel,y in rs.items():
            if channel not in signals:continue
            predicted=np.interp(rt,t,signals[channel]);error=predicted-y;scale=max(float(np.sqrt(np.mean(y*y))),1e-9)
            row['plecs_waveform_errors'][channel]={'rmse':float(np.sqrt(np.mean(error*error))),'nrmse':float(np.sqrt(np.mean(error*error))/scale),'max_abs':float(np.max(np.abs(error)))}
        row['passed']=bool(row['baseline_waveform_errors']) and max(x['nrmse'] for x in row['baseline_waveform_errors'].values())<.01 and all(x['passed'] for x in comparisons)
        row['reference_validation']=('ORIGINAL_STATISTICS_THRESHOLDS' if comparisons else 'NO_REGRESSION_AGAINST_VALIDATED_SAME_MODEL; PLECS_WAVEFORM_ERRORS_REPORTED')
        w.dump(dest/'comparison.json',row);summary['cases'].append(row);save()
        # A compact overview; acceptance uses every saved point, without alignment shifts.
        channels=[n for n in ('VOUT','IOUT','CH006','CH001') if n in signals][:2] or list(rs)[:2]
        fig,axes=w.plt.subplots(len(channels),1,figsize=(11,3*len(channels)),squeeze=False)
        for ax,n in zip(axes[:,0],channels):
            stride=max(1,len(t)//5000);ax.plot(t[::stride],signals[n][::stride],label='V1.2pre',lw=1)
            if n in rs:
                stride2=max(1,len(rt)//5000);ax.plot(rt[::stride2],rs[n][::stride2],label='saved PLECS',lw=.7,alpha=.7)
            ax.set_ylabel(n);ax.grid(alpha=.2);ax.legend()
        axes[-1,0].set_xlabel('Time (s)');fig.suptitle(name);fig.tight_layout();fig.savefig(dest/'overview.png',dpi=140);w.plt.close(fig)
        print('PASS' if row['passed'] else 'FAIL',name,r['simulated_seconds'],str(row.get('statistics_passed','-'))+'/'+str(row.get('statistics_total','-')),'transactions',r['transactions'],flush=True)
    manifest=json.loads((ROOT/'reports/baseline_source_manifest.json').read_text(encoding='utf-8'))
    baseline_checks=[{'path':x['path'],'unchanged':sha(a.baseline/x['path'])==x['sha256']} for x in manifest['files']]
    summary['baseline_sources_unchanged']=all(x['unchanged'] for x in baseline_checks)
    w.dump(a.out/'baseline_integrity.json',baseline_checks)
    summary['passed']=len(summary['cases'])==len([x for x in cases if not a.case or x[0] in a.case]) and all(x['passed'] for x in summary['cases']) and summary['baseline_sources_unchanged'];save()
    print('STAGE CASES',summary['passed'],flush=True)
    return 0 if summary['passed'] else 1
if __name__=='__main__':sys.exit(main())
