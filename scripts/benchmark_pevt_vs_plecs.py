#!/usr/bin/env python3
"""Full original cases: fresh PLECS versus optimized native PULSEES1 only.

Simulation timing ends at COMPLETED after archive write; replay is separate.
An event-generation timeout stops the whole batch. Source inputs stay immutable.
"""
import argparse
import io
import json
import pathlib
import shutil
import subprocess
import sys
import threading
import time
import xmlrpc.client
import numpy as np
from scipy.io import loadmat
from benchmark_all_platforms import sha, statistics
from benchmark_c002_end_to_end import Transport
from read_pevt import read, summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('case-set','out','win-event'):
        p.add_argument('--'+name,type=pathlib.Path,required=True)
    for name in ('linux-event','linux-source','native-out'):
        p.add_argument('--'+name,required=True)
    p.add_argument('--only',nargs='+',required=True)
    p.add_argument('--max-event-plecs-ratio',type=float,default=10)
    p.add_argument('--diagnostic-t-end',type=float,help='Explicit diagnostic prefix only; never full-case acceptance')
    p.add_argument('--platforms',nargs='+',choices=['linux','win'],default=['linux','win'])
    a=p.parse_args();root=pathlib.Path(__file__).resolve().parents[1];a.out=a.out.resolve()
    a.out.mkdir(parents=True,exist_ok=True)
    if (a.out/'ledger.json').exists():raise ValueError('use a fresh output directory')
    prefix=['wsl.exe','-d','Ubuntu-24.04','-u','root','--exec']
    def native(path):return subprocess.check_output(prefix+['wslpath','-u',str(path)],text=True).strip()
    binaries={'linux':a.linux_event,'win':str(a.win_event.resolve())}
    ledger={'timing':'command start to COMPLETED notification after archive write; process exit separately; replay excluded',
            'policy':{'max_event_plecs_ratio':a.max_event_plecs_ratio,'on_timeout':'stop entire batch'},'binaries':{},'cases':{}}
    for platform,binary in binaries.items():
        if platform=='linux':
            description=subprocess.check_output(prefix+['file',binary],text=True).strip()
            if 'ELF 64-bit' not in description or 'x86-64' not in description:raise ValueError('native ELF required')
            digest=subprocess.check_output(prefix+['sha256sum',binary],text=True).split()[0]
        else:description,digest='Windows native x86-64',sha(binary)
        ledger['binaries'][platform]={'path':binary,'description':description,'sha256':digest}
    def save():(a.out/'ledger.json').write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    save()
    for name in a.only:
        case=a.case_set.resolve()/name;meta=json.loads((case/'provenance.json').read_text(encoding='utf-8'))
        dest=a.out/name;dest.mkdir()
        end=a.diagnostic_t_end if a.diagnostic_t_end is not None else meta['original_end_seconds']
        if not 0<end<=meta['original_end_seconds']:raise ValueError('diagnostic duration outside original case')
        row={'target_seconds':end,'original_end_seconds':meta['original_end_seconds'],
             'scope':'diagnostic prefix' if a.diagnostic_t_end is not None else 'full original duration',
             'runs':{},'validation':{},'input_sha256':{},'finished':False}
        ledger['cases'][name]=row
        for item in meta['pulse_inputs']+meta['csv_exports']+[{'file':meta['capture_model'],'sha256':meta['capture_sha256']}]:
            digest=sha(case/item['file'])
            if digest!=item['sha256']:raise ValueError('input integrity: '+item['file'])
            row['input_sha256'][item['file']]=digest
        save()
        rpc=xmlrpc.client.ServerProxy('http://127.0.0.1:1080',transport=Transport(),allow_none=True)
        try:
            rpc.plecs.load((case/meta['capture_model']).as_posix())
            n=round(end/meta['csv_grid_seconds'])+1
            opts={'OutputFormat':'MatFile','SolverOpts':{'TimeSpan':end,'OutputTimesOption':'specified',
                  'OutputTimes':np.linspace(0,end,n).tolist(),'Timeout':900}}
            print('START PLECS',name,flush=True);start=time.perf_counter();data=rpc.plecs.simulate(meta['capture_name'],opts);seconds=time.perf_counter()-start
            (dest/'plecs.mat').write_bytes(data.data);fresh=loadmat(io.BytesIO(data.data))
            if fresh['Time'].size!=n or fresh['Time'].ravel()[-1]!=end or not np.isfinite(fresh['Values']).all():raise ValueError('incomplete PLECS')
            row['runs']['PLECS']={'status':'COMPLETED','seconds':seconds,'simulated_seconds':end,'bytes':len(data.data),'samples':n}
        except Exception as e:
            row['runs']['PLECS']={'status':'FAILED','error':str(e)};save();raise
        finally:
            try:rpc.plecs.close(meta['capture_name'])
            except Exception:pass
        limit=a.max_event_plecs_ratio*seconds;row['event_generation_limit_seconds']=limit;save()
        print(f'DONE PLECS {seconds:.6f}s; limit {limit:.6f}s',flush=True)
        for platform in a.platforms:
            model=dest/('model-'+platform);shutil.copytree(case/'pulse',model,ignore=shutil.ignore_patterns('.pulse_modules'))
            local=dest/(platform+'_event');local.mkdir()
            if platform=='linux':
                nm=a.native_out+'/'+name+'/model-linux';output=a.native_out+'/'+name+'/linux_event'
                subprocess.run(prefix+['mkdir','-p',nm],check=True);subprocess.run(prefix+['cp','-a',native(model)+'/.',nm],check=True)
                prepare=prefix+['python3',a.linux_source+'/scripts/build_software.py',nm+'/netlist.md']
                command=prefix+['timeout','--signal=KILL',f'{limit:.9f}s',binaries[platform],nm+'/netlist.md','--t-end',str(end),'--output-format','trajectory','--out',output]
            else:
                output=str(local);prepare=[sys.executable,str(root/'scripts/build_software.py'),str(model/'netlist.md')]
                command=[binaries[platform],str(model/'netlist.md'),'--t-end',str(end),'--output-format','trajectory','--out',output]
            prepared=subprocess.run(prepare,capture_output=True,text=True,encoding='utf-8')
            (dest/(platform+'-module.txt')).write_text(prepared.stdout+prepared.stderr,encoding='utf-8')
            if prepared.returncode:raise RuntimeError('controller compilation failed')
            print('START',name,platform,'event generation',flush=True)
            start=time.perf_counter();notified=None;timed_out=False;timer=None;lines=[]
            with (dest/(platform+'-stderr.txt')).open('w',encoding='utf-8') as err:
                proc=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=err,text=True,encoding='utf-8')
                if platform=='win':
                    def stop():
                        nonlocal timed_out
                        if proc.poll() is None:timed_out=True;proc.kill()
                    timer=threading.Timer(max(0,limit-(time.perf_counter()-start)),stop);timer.start()
                for line in proc.stdout:
                    lines.append(line)
                    if line.startswith('  "status":') and '"COMPLETED"' in line:notified=time.perf_counter()-start
                rc=proc.wait()
                if timer:timer.cancel()
            elapsed=time.perf_counter()-start
            timed_out=timed_out or (platform=='linux' and (rc in (124,137) or (rc==9 and elapsed>=limit)))
            (dest/(platform+'-stdout.txt')).write_text(''.join(lines),encoding='utf-8')
            if platform=='linux':subprocess.run(prefix+['cp','-a',output+'/.',native(local)],capture_output=True)
            result={'status':'TIME_LIMIT_EXCEEDED' if timed_out else 'OUTPUT_FAILED','seconds':notified,'process_exit_seconds':elapsed,'returncode':rc,'limit_seconds':limit}
            if (local/'simulation_report.json').exists():
                result['report']=json.loads((local/'simulation_report.json').read_text(encoding='utf-8'))
                if not timed_out and rc==0 and notified is not None:result['status']=result['report']['status']
            result['files']={f.name:{'bytes':f.stat().st_size,'sha256':sha(f)} for f in local.iterdir() if f.is_file()}
            result['total_bytes']=sum(f['bytes'] for f in result['files'].values());row['runs'][platform+'_event']=result;save()
            print('DONE',platform,result['status'],elapsed,flush=True)
            if timed_out:
                row['stopped_reason']='Event generation exceeded '+str(a.max_event_plecs_ratio)+'x fresh PLECS; remaining work not started.';save();return 2
            if result['status']!='COMPLETED':raise RuntimeError('event generation failed')
            row['validation'][platform+'_protocol']=summary(read(local));save()
            replay=str(pathlib.PurePosixPath(binaries[platform]).parent/'pulse-replay') if platform=='linux' else str(a.win_event.resolve().parent/'pulse-replay.exe')
            replay_out=a.native_out+'/'+name+'/linux_replay' if platform=='linux' else str(dest/'win_replay')
            print('START',platform,'separate reconstruction',flush=True);start=time.perf_counter()
            rr=subprocess.run((prefix if platform=='linux' else [])+[replay,output,'--out',replay_out],capture_output=True,text=True,encoding='utf-8')
            replay_seconds=time.perf_counter()-start
            (dest/(platform+'-replay-stdout.txt')).write_text(rr.stdout,encoding='utf-8');(dest/(platform+'-replay-stderr.txt')).write_text(rr.stderr,encoding='utf-8')
            if rr.returncode:raise RuntimeError('reconstruction failed')
            reconstructed=dest/(platform+'_replay')
            if platform=='linux':
                reconstructed.mkdir();subprocess.run(prefix+['cp','-a',replay_out+'/.',native(reconstructed)],check=True)
            row['runs'][platform+'_replay']={'status':'COMPLETED','seconds':replay_seconds}
            csv=np.concatenate([np.loadtxt(case/e['file'],delimiter=',',skiprows=1,ndmin=2) for e in meta['csv_exports']])
            csv=csv[csv[:,0]<=end]
            reference={'Time':csv[:,0].reshape(1,-1),'Values':csv[:,1:].T}
            row['validation']['fresh_PLECS_matches_original_CSV']=bool(np.array_equal(fresh['Time'].ravel(),csv[:,0]) and np.array_equal(fresh['Values'],csv[:,1:].T))
            row['validation'][platform+'_vs_PLECS']=statistics(reconstructed,reference,meta);save()
            print('DONE',platform,'accuracy',row['validation'][platform+'_vs_PLECS']['passed'],'/',row['validation'][platform+'_vs_PLECS']['total'],flush=True)
        row['finished']=True;save()
    print('BENCHMARK FINISHED',flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
