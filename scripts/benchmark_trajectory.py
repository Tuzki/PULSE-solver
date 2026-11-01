#!/usr/bin/env python3
"""Full original Boost: PLECS vs frozen Linux PULSE vs trajectory + replay.

Use one host clock, sequential runs, start-command to completion notification.
The input/controller are prepared before timing; no physical settings change.
"""
import argparse
import hashlib
import io
import json
import pathlib
import subprocess
import time
import xmlrpc.client
import numpy as np
from scipy.io import loadmat
from benchmark_c002_end_to_end import Transport, sha


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case-set',type=pathlib.Path,required=True)
    p.add_argument('--out',type=pathlib.Path,required=True)
    p.add_argument('--native-out',required=True)
    p.add_argument('--baseline',required=True)
    p.add_argument('--variant',required=True)
    p.add_argument('--replay',required=True)
    p.add_argument('--model',required=True)
    p.add_argument('--wsl-distro',default='Ubuntu-24.04')
    a=p.parse_args();a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=False)
    prefix=['wsl.exe','-d',a.wsl_distro,'-u','root','--exec']
    case=a.case_set.resolve()/'rohm-c002-d-boost'
    meta=json.loads((case/'provenance.json').read_text(encoding='utf-8'))
    for entry in meta['pulse_inputs']:
        original=case/entry['file'];native=str(pathlib.PurePosixPath(a.model).parent/original.name)
        if sha(original)!=entry['sha256'] or hashlib.sha256(subprocess.check_output(prefix+['cat',native])).hexdigest()!=entry['sha256']:
            raise RuntimeError('original input integrity failure')
    if subprocess.run(prefix+['test','-e',a.native_out]).returncode==0:
        raise RuntimeError('native output directory already exists')
    ledger={'case_revision':'13660577132de41c37c1c47576c02941d21c532a',
            'timing':'same host perf_counter; command issued to completion notification; sequential single runs',
            'native_out':a.native_out,'target_seconds':.3,'save_dt':2e-7,'runs':{},'binary_sha256':{}}
    for label,binary in [('original',a.baseline),('trajectory',a.variant),('replay',a.replay)]:
        description=subprocess.check_output(prefix+['file',binary],text=True)
        if 'ELF 64-bit' not in description or 'x86-64' not in description:raise RuntimeError('native Linux ELF required')
        ledger['binary_sha256'][label]=subprocess.check_output(prefix+['sha256sum',binary],text=True).split()[0]
    def save():
        (a.out/'comparison.json').write_text(json.dumps(ledger,indent=2)+'\n',encoding='utf-8')
    save()
    capture=case/meta['capture_model']
    if sha(capture)!=meta['capture_sha256']:raise RuntimeError('PLECS source changed')
    rpc=xmlrpc.client.ServerProxy('http://127.0.0.1:1080',transport=Transport(),allow_none=True)
    rpc.plecs.load(capture.as_posix())
    try:
        times=np.linspace(0,.3,300001)
        options={'OutputFormat':'MatFile','SolverOpts':{'TimeSpan':.3,'OutputTimesOption':'specified','OutputTimes':times.tolist(),'Timeout':900}}
        print('START PLECS',flush=True);start=time.perf_counter()
        result=rpc.plecs.simulate(meta['capture_name'],options)
        elapsed=time.perf_counter()-start;print(f'DONE PLECS {elapsed:.9f} s',flush=True)
        data=loadmat(io.BytesIO(result.data));t=data['Time'].ravel()
        if t.size!=300001 or t[-1]!=.3 or not np.isfinite(data['Values']).all():raise RuntimeError('PLECS incomplete')
        (a.out/'plecs.mat').write_bytes(result.data)
        ledger['runs']['PLECS']={'seconds':elapsed,'status':'COMPLETED','end_seconds':float(t[-1])};save()
    finally:rpc.plecs.close(meta['capture_name'])
    def run(label,command):
        print('START '+label,flush=True);start=time.perf_counter();notified=None;lines=[]
        with (a.out/(label+'-stderr.txt')).open('w',encoding='utf-8') as err:
            proc=subprocess.Popen(prefix+command,stdout=subprocess.PIPE,stderr=err,text=True,encoding='utf-8')
            for line in proc.stdout:
                lines.append(line)
                if line.startswith('  "status":') and '"COMPLETED"' in line:notified=time.perf_counter()-start
            rc=proc.wait()
        total=time.perf_counter()-start
        (a.out/(label+'-stdout.json')).write_text(''.join(lines),encoding='utf-8')
        report=json.loads(''.join(lines))
        if rc or notified is None:raise RuntimeError(label+' did not complete')
        if label!='replay' and (report['simulated_seconds']!=.3 or report['effective_SAVE_DT']!=2e-7):raise RuntimeError('duration/sampling changed')
        ledger['runs'][label]={'seconds':notified,'process_exit_seconds':total,'status':report['status'],
                             'report':report};save();print(f'DONE {label} {notified:.9f} s',flush=True)
        return report
    original=run('original',[a.baseline,a.model,'--out',a.native_out+'/original'])
    trace=run('trajectory',[a.variant,a.model,'--output-format','trajectory','--out',a.native_out+'/trajectory'])
    run('replay',[a.replay,a.native_out+'/trajectory','--out',a.native_out+'/replay'])
    # Copy result files only after all measured completion notifications.
    host_native=subprocess.check_output(prefix+['wslpath','-u',str(a.out)],text=True).strip()
    subprocess.run(prefix+['cp','-a',a.native_out,host_native+'/native-results'],check=True)
    dirs=a.out/'native-results'
    differences={}
    with np.load(dirs/'original/out.pewave.npz',allow_pickle=False) as x,np.load(dirs/'replay/out.pewave.npz',allow_pickle=False) as y:
        xm=json.loads(str(x['metadata_json']));ym=json.loads(str(y['metadata_json']))
        xi={s['name']:s['id'] for s in xm['signals']};yi={s['name']:s['id'] for s in ym['signals']}
        if xi.keys()!=yi.keys():raise RuntimeError('channel sets differ')
        for name,xx,yy in [('time',x['time'],y['time'])]+[(n,x[xi[n]],y[yi[n]]) for n in xi]:
            differences[name]={'bytes_equal':xx.dtype==yy.dtype and xx.shape==yy.shape and xx.tobytes()==yy.tobytes(),
                               'max_abs':float(np.max(np.abs(xx.astype(float)-yy.astype(float))))}
    event_hashes={name:sha(dirs/name/'event_log.jsonl') for name in ('original','trajectory','replay')}
    fields=['status','simulated_seconds','effective_T_END','effective_SAVE_DT','T_atom','transactions',
            'internal_state','physical_state_view','software_states','software_final_outputs',
            'root_queries','root_failures','mode_compilations','microsteps','rollbacks','matrix_exponentials']
    changed=[k for k in fields if original.get(k)!=trace.get(k)]
    ledger['equivalence']={'arrays':differences,'event_hashes':event_hashes,'changed_solver_fields':changed}
    ledger['bytes']={label:{f.name:f.stat().st_size for f in (dirs/label).iterdir() if f.is_file()} for label in ('original','trajectory','replay')}
    ledger['totals_bytes']={k:sum(v.values()) for k,v in ledger['bytes'].items()}
    ledger['trajectory_plus_replay_seconds']=ledger['runs']['trajectory']['seconds']+ledger['runs']['replay']['seconds']
    ledger['passed']=not changed and len(set(event_hashes.values()))==1 and all(v['bytes_equal'] for v in differences.values())
    save()
    print(json.dumps({k:v for k,v in ledger.items() if k not in ('runs',)},indent=2),flush=True)
    return 0 if ledger['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
