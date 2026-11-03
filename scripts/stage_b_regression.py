#!/usr/bin/env python3
"""Compare an A010 Stage A baseline with Stage B candidate, strictly identical PEVT payload.

Build the C controller before running; both solvers use the same frozen model
and do not alter mathematical rules, sample times, output format or channels.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import struct
import subprocess
import time
import os
import resource
import threading


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pevt_sections(path: Path):
    out = []
    with path.open('rb') as f:
        magic, version, count, flags = struct.unpack('<8sHHI', f.read(16))
        assert (magic,version,flags)==(b'PULSEES1',1,0), 'PEVT header differs'
        for _ in range(count):
            kind,codec,stored,unpacked,n,expected=struct.unpack('<IIQQQ32s',f.read(64))
            assert codec==0 and stored==unpacked, 'PEVT compression policy differs'
            digest=hashlib.sha256()
            remaining=stored
            while remaining:
                b=f.read(min(1<<20,remaining)); assert b,'truncated PEVT section'
                digest.update(b); remaining-=len(b)
            assert digest.digest()==expected, 'PEVT digest mismatch'
            out.append((kind,n,expected.hex()))
        assert not f.read(1),'trailing bytes'
    return out


def run(binary: Path, model: Path, t_end: str, out: Path, wall_limit: float):
    out.mkdir(parents=True,exist_ok=True)
    cmd=[str(binary),str(model),'--t-end',t_end,'--output-format','trajectory','--out',str(out)]
    env=os.environ.copy()
    for key in ('PULSE_PROFILE_PHASES','PULSE_WALL_SECONDS'):env.pop(key,None)
    before=resource.getrusage(resource.RUSAGE_CHILDREN);notified=None;lines=[];timed_out=False
    start=time.perf_counter()
    with (out/'stderr.txt').open('w') as err:
        p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=err,text=True,env=env)
        def stop():
            nonlocal timed_out
            if p.poll() is None:timed_out=True;p.kill()
        timer=threading.Timer(wall_limit,stop);timer.start()
        for line in p.stdout:
            lines.append(line)
            if line.startswith('  "status":') and '"COMPLETED"' in line:notified=time.perf_counter()-start
        code=p.wait();wall=time.perf_counter()-start;timer.cancel()
    after=resource.getrusage(resource.RUSAGE_CHILDREN)
    (out/'stdout.txt').write_text(''.join(lines),encoding='utf-8')
    measured={'command':cmd,'pid':p.pid,'returncode':code,'timed_out':timed_out,
              'completion_wall_seconds':notified,'exit_wall_seconds':wall,
              'cpu_user_seconds':after.ru_utime-before.ru_utime,'cpu_system_seconds':after.ru_stime-before.ru_stime,
              'cpu_seconds':after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime}
    (out/'measurement.json').write_text(json.dumps(measured,indent=2)+'\n')
    assert code==0 and not timed_out and notified is not None,f'Failed {cmd!r}; see measurement.json/stderr.txt'
    report=json.loads((out/'simulation_report.json').read_text())
    assert report['status']=='COMPLETED' and abs(report['simulated_seconds']-float(t_end))<1e-15
    assert len(report['analog_channels'])==13 and len(report['digital_channels'])==4
    return {'wall_seconds':notified,'exit_wall_seconds':wall,'measurement':measured,'report':report,'run_seconds':report['run_seconds'],
            'transactions':report['transactions'], 'root_queries':report['root_queries'],
            'original_equation_cache':report['original_equation_cache'],
            'mode_compilations':report['mode_compilations'],
            'sections':pevt_sections(out/'out.pevt')}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--netlist',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--duration',default='0.5')
    p.add_argument('--repeats',type=int,default=1)
    p.add_argument('--reference-ledger',type=Path,help='Reuse pinned Stage A single-round raw ledger; verify its binary SHA256')
    p.add_argument('--wall-limit',type=float,default=132.8290989997913,help='Explicit per-run limit; default is 10x saved Stage A PLECS timing')
    a=p.parse_args()
    if a.repeats<1:p.error('repeats must be >=1')
    a.out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for i in range(a.repeats):
        if a.reference_ledger:
            assert a.repeats==1,'Saved reference applies to one accepted comparison'
            reference=json.loads(a.reference_ledger.read_text())
            assert sha(a.baseline.read_bytes())==reference['binaries']['stage_a']['sha256'],'Stage A binary identity mismatch'
            previous=next(r for r in reference['runs'] if r['label']=='500ms_stage_a_1')
            q=previous['report']
            baseline={'wall_seconds':previous['completion_wall_seconds'],'measurement':previous,'report':q,
                      **{k:q[k] for k in ('transactions','root_queries','mode_compilations','original_equation_cache')},
                      'sections':pevt_sections(Path(previous['output_path'])/'out.pevt'),
                      'reference':'saved Stage A single run, not a fresh contemporaneous benchmark'}
        else:baseline=run(a.baseline.resolve(),a.netlist.resolve(),a.duration,a.out/f'A_{i}',a.wall_limit)
        candidate=run(a.candidate.resolve(),a.netlist.resolve(),a.duration,a.out/f'B_{i}',a.wall_limit)
        assert [(x[0],x[1],x[2]) for x in baseline['sections'] if x[0]!=1] == [
               (x[0],x[1],x[2]) for x in candidate['sections'] if x[0]!=1],\
               'Stage B changed PEVT content: inspect first divergent section'
        for field in ('transactions','root_queries','mode_compilations','original_equation_cache'):
            assert baseline[field]==candidate[field], f'Stage B changed {field}'
        rows.append({'baseline':baseline,'candidate':candidate,
                     'speedup':baseline['wall_seconds']/candidate['wall_seconds']})
    result={'duration':a.duration,'repeats':a.repeats,'rows':rows,
            'baseline_median_wall_s':statistics.median(x['baseline']['wall_seconds'] for x in rows),
            'candidate_median_wall_s':statistics.median(x['candidate']['wall_seconds'] for x in rows),
            'median_speedup':statistics.median(x['speedup'] for x in rows),
            'validation':'PEVT sections 2–10 SHA256 and critical counters identical'}
    (a.out/'stage_b_evidence.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'baseline_s':result['baseline_median_wall_s'],
                      'candidate_s':result['candidate_median_wall_s'],
                      'speedup':result['median_speedup']},indent=2))

if __name__=='__main__':main()
