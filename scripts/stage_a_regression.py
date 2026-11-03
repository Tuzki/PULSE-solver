#!/usr/bin/env python3
"""Sequential native Stage A regression; unchanged A010 model and 17 outputs."""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import resource
import shutil
import statistics
import struct
import subprocess
import threading
import time


def sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()


def archive(path):
    sections=[]
    with pathlib.Path(path).open('rb') as f:
        magic,version,count,flags=struct.unpack('<8sHHI',f.read(16))
        assert (magic,version,flags)==(b'PULSEES1',1,0)
        for _ in range(count):
            kind,codec,stored,decoded,n,expected=struct.unpack('<IIQQQ32s',f.read(64))
            assert codec==0 and stored==decoded
            h=hashlib.sha256();remaining=stored
            while remaining:
                b=f.read(min(1<<20,remaining));assert b
                h.update(b);remaining-=len(b)
            assert h.digest()==expected
            sections.append({'kind':kind,'bytes':stored,'records':n,'sha256':expected.hex()})
        assert not f.read(1)
    return sections


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('baseline','stage-a','case','build-software','out','prefix-baseline'):
        p.add_argument('--'+name,type=pathlib.Path,required=True)
    p.add_argument('--wall-limit',type=float,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    assert not (a.out/'ledger.json').exists(),'Use a fresh directory'
    ledger={'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'command':__import__('sys').argv,'runs':[],'wall_limit':a.wall_limit,
            'timing':'command to COMPLETED after archive write; process exit/OS CPU separately; replay excluded',
            'binaries':{label:{'path':str(binary),'sha256':sha(binary)} for label,binary in [('baseline',a.baseline),('stage_a',a.stage_a)]}}
    def save():(a.out/'ledger.json').write_text(json.dumps(ledger,indent=2)+'\n')
    meta=json.loads((a.case/'provenance.json').read_text())
    ledger['inputs']={}
    for item in meta['pulse_inputs']:
        assert sha(a.case/item['file'])==item['sha256'];ledger['inputs'][item['file']]=item['sha256']
    model=a.out/'model';shutil.copytree(a.case/'pulse',model,ignore=shutil.ignore_patterns('.pulse_modules'))
    c=subprocess.run(['python3',str(a.build_software),str(model/'netlist.md')],capture_output=True,text=True)
    (a.out/'controller-build.txt').write_text(c.stdout+c.stderr);c.check_returncode()
    def payload(sections):return [(s['kind'],s['sha256']) for s in sections if s['kind']!=1]
    def run(label,binary,end):
        dest=a.out/label;dest.mkdir();env=os.environ.copy()
        for key in ('PULSE_PROFILE_PHASES','PULSE_WALL_SECONDS'):env.pop(key,None)
        command=[str(binary),str(model/'netlist.md'),'--t-end',str(end),'--output-format','trajectory','--out',str(dest)]
        print('START',label,flush=True);before=resource.getrusage(resource.RUSAGE_CHILDREN)
        started=datetime.datetime.now(datetime.timezone.utc).isoformat();lines=[];notified=None;timeout=False
        with (dest/'stderr.txt').open('w') as err:
            start=time.perf_counter();proc=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=err,text=True,env=env)
            def stop():
                nonlocal timeout
                if proc.poll() is None:timeout=True;proc.kill()
            timer=threading.Timer(a.wall_limit,stop);timer.start()
            for line in proc.stdout:
                lines.append(line)
                if line.startswith('  "status":') and '"COMPLETED"' in line:notified=time.perf_counter()-start
            rc=proc.wait();elapsed=time.perf_counter()-start;timer.cancel()
        after=resource.getrusage(resource.RUSAGE_CHILDREN)
        (dest/'stdout.txt').write_text(''.join(lines))
        row={'label':label,'command':command,'started_utc':started,'returncode':rc,'timeout':timeout,
             'completion_wall_seconds':notified,'exit_wall_seconds':elapsed,
             'cpu_user_seconds':after.ru_utime-before.ru_utime,'cpu_system_seconds':after.ru_stime-before.ru_stime,
             'cpu_seconds':after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
             'output_path':str(dest)}
        ledger['runs'].append(row);save()
        assert rc==0 and not timeout,label+' failed/time limit reached; batch stopped'
        q=json.loads((dest/'simulation_report.json').read_text());row['report']=q
        assert q['status']=='COMPLETED' and q['simulated_seconds']==end and q['effective_SAVE_DT']==1e-7
        assert len(q['analog_channels'])==13 and len(q['digital_channels'])==4
        assert not q['performance_phases']['enabled']
        row['sections']=archive(dest/'out.pevt')
        row['files']={f.name:{'bytes':f.stat().st_size,'sha256':sha(f)} for f in dest.iterdir() if f.suffix in ('.pevt','.json')}
        save();print('DONE',label,'wall',notified,'CPU',row['cpu_seconds'],flush=True);return row
    for seconds,label in [(.005,'5ms')]:
        r=run(label+'_stage_a',a.stage_a,seconds)
        base=archive(a.prefix_baseline/(label+'_on' if label!='20ms' else '20ms_off_1')/'out.pevt')
        r['baseline_archive_path']=str(a.prefix_baseline/(label+'_on' if label!='20ms' else '20ms_off_1')/'out.pevt')
        r['payload_equal_baseline']=payload(r['sections'])==payload(base);save()
        assert r['payload_equal_baseline'],'Short prefix changed; stop and investigate'
    expected=None
    for i in range(1,2):
        base=run(f'500ms_baseline_{i}',a.baseline,.5)
        if expected is None:expected=payload(base['sections'])
        assert payload(base['sections'])==expected
        stage=run(f'500ms_stage_a_{i}',a.stage_a,.5)
        stage['payload_equal_baseline']=payload(stage['sections'])==expected;save()
        assert stage['payload_equal_baseline'],'Full event payload changed; stop and investigate'
    medians={label:statistics.median(r['completion_wall_seconds'] for r in ledger['runs'] if r['label'].startswith('500ms_'+label)) for label in ('baseline','stage_a')}
    ledger['wall_seconds_single_repetition']=medians;ledger['speedup']=medians['baseline']/medians['stage_a']
    ledger['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();save()
    print('FINISHED',json.dumps(medians),'speedup',ledger['speedup'],flush=True)


if __name__=='__main__':main()
