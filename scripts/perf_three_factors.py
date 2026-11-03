#!/usr/bin/env python3
"""Real perf physical-stack attribution for three mutually exclusive hot buckets.

CPU-clock sampling, no LD_PRELOAD, no uprobes/uretprobes. This intentionally
measures profiles separately from unprofiled speed benchmarks.
"""
import argparse, collections, json, os, pathlib, re, resource, shutil, subprocess, time

ALLOC=re.compile(r'^(?:__)?(?:libc_)?(?:malloc|calloc|realloc|free|cfree|_int_malloc|_int_free|malloc_consolidate|unlink_chunk|sysmalloc|alloc_new_heap|new_heap|tcache)')

def category(frames):
    leaf=frames[0]
    if ALLOC.match(leaf):return 'memory_allocator'
    for f in frames:
        if 'bind_observations(' in f or '::Assembler::' in f:return 'mode_binding'
        if 'PevtArchive::' in f or 'pulse::Trajectory::' in f:return 'pevt_archive'
    return 'other'

def parse_perf(text):
    rows=[];current=None
    for line in text.splitlines():
        if re.match(r'^\s*\S+\s+\d+\s+(?:\[\d+\]\s+)?[0-9.]+:\s+\d+\s+cpu-clock[^:]*:',line):
            if current:rows.append(current)
            current=[];continue
        if not current and current is not None:
            m=re.match(r'^\s*[0-9a-f]+\s+(.+)\s+\(([^()]*)\)\s*$',line)
            if m:current.append(m[1].split(' +0x')[0]);continue
        elif current:
            m=re.match(r'^\s*[0-9a-f]+\s+(.+)\s+\(([^()]*)\)\s*$',line)
            if m:current.append(m[1].split(' +0x')[0]);continue
        if not line.strip() and current:
            rows.append(current);current=None
    if current:rows.append(current)
    return rows

def main():
    p=argparse.ArgumentParser();p.add_argument('--binary',type=pathlib.Path,required=True)
    p.add_argument('--netlist',type=pathlib.Path,required=True)
    p.add_argument('--out',type=pathlib.Path,required=True)
    p.add_argument('--seconds',type=float,default=0.05)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    perf=shutil.which('perf')
    if not perf:raise SystemExit('perf missing; cannot claim per-module CPU data')
    data=a.out/'perf.data'; dest=a.out/'run';
    cmd=[perf,'record','--quiet','-e','cpu-clock','-F','999','--call-graph','dwarf,32768',
         '-o',str(data),'--',str(a.binary),str(a.netlist),'--t-end',str(a.seconds),
         '--output-format','trajectory','--out',str(dest)]
    with (a.out/'perf-run.log').open('w') as log:
        proc=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=300)
    if proc.returncode!=0:
        raise SystemExit(f'perf failed ({proc.returncode}); inspect {a.out}/perf-run.log')
    report=json.loads((dest/'simulation_report.json').read_text())
    if report['status']!='COMPLETED':raise RuntimeError('perf test did not complete')
    with (a.out/'perf-script.txt').open('w') as f:
        subprocess.run([perf,'script','-i',data],stdout=f,stderr=subprocess.PIPE,check=True,text=True)
    stacks=parse_perf((a.out/'perf-script.txt').read_text(errors='replace'))
    if len(stacks)<1000:raise RuntimeError(f'Only {len(stacks)} physical stacks, insufficient attribution')
    counts=collections.Counter(category(r) for r in stacks)
    total=sum(counts.values());rows={k:{'samples':v,'exclusive_percent':100*v/total,
                      'sampled_cpu_seconds_approx':v/999.0} for k,v in counts.items()}
    for k in ['memory_allocator','mode_binding','pevt_archive','other']:
        rows.setdefault(k,{'samples':0,'exclusive_percent':0.0,'sampled_cpu_seconds_approx':0.0})
    result={'samples':total,'sampled_total_cpu_seconds_approx':total/999.0,'categories':rows,'scope':'999Hz cpu-clock; physical stacks; no probes',
        'warning':'Sampled CPU category estimates, NOT exact function timing; excludes perf process setup. '
                  'Allocation overhead is classified into allocator, not bind or archive.'}
    (a.out/'three_factors.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
