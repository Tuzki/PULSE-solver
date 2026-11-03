#!/usr/bin/env python3
"""Run real Stage C vs integrated Stage D on identical A010 50ms, no internet.

Requires a complete LOCAL Git repository containing pinned Stage C commit,
local A010 case-set files, gcc/g++, cmake, ninja and Python 3.
Does not infer performance from microbenchmarks or earlier 500ms runs.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, math, os, pathlib, shutil, statistics, subprocess, sys, time

BASE_REF = 'fa2bc5ee4aab588ee91fb5b0513c692493799f7e'

def run(cmd, cwd=None, env=None, stdout=None, timeout=None):
    return subprocess.run([str(x) for x in cmd],cwd=cwd,env=env,stdout=stdout,stderr=subprocess.STDOUT,
                          text=True,check=True,timeout=timeout)

def sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1<<20), b''):h.update(block)
    return h.hexdigest()

def executable(folder, name):
    target=folder/'build-d-bench'/name
    if not target.is_file():raise RuntimeError(f'Missing binary: {target}')
    return target

def build_solver(root, full_tests, logfile):
    build=root/'build-d-bench'
    with logfile.open('w') as log:
        run(['cmake','-S',root,'-B',build,'-G','Ninja','-DCMAKE_BUILD_TYPE=Release',
             f'-DBUILD_TESTING={"ON" if full_tests else "OFF"}'],stdout=log)
        run(['cmake','--build',build,'--parallel','2'],stdout=log,timeout=1200)
        if full_tests:run(['ctest','--test-dir',build,'--output-on-failure'],stdout=log,timeout=1200)
    return build

def isolated_case(case, source, destination):
    shutil.copytree(case/'pulse',destination,
                    ignore=shutil.ignore_patterns('.pulse_modules','*.so','*.dll','*.dylib'),dirs_exist_ok=False)
    with (destination/'controller_build.log').open('w') as log:
        run([sys.executable,source/'scripts/build_software.py',destination/'netlist.md'],stdout=log,timeout=120)
    return destination/'netlist.md'

def run_one(binary, netlist, dest, profile=False, alloc=None, seconds=0.05):
    dest.mkdir(parents=True,exist_ok=False)
    cmd=[str(binary),str(netlist),'--t-end',str(seconds),
         '--output-format','trajectory','--out',str(dest)]
    env=os.environ.copy();env.pop('LD_PRELOAD',None);env.pop('PULSE_ALLOC_REPORT',None)
    env.pop('PULSE_PROFILE_PHASES',None)
    if profile:env['PULSE_PROFILE_PHASES']='1'
    if alloc:
        env['LD_PRELOAD']=str(alloc)
        env['PULSE_ALLOC_REPORT']=str(dest/'allocations.json')
    started=time.perf_counter()
    with (dest/'stdout.log').open('w') as out,(dest/'stderr.log').open('w') as err:
        proc=subprocess.Popen(cmd,env=env,stdout=out,stderr=err)
        try:
            pid,status,usage=os.wait4(proc.pid,0)
            proc.returncode=os.waitstatus_to_exitcode(status)
        except Exception:
            proc.kill();proc.wait();raise
    wall=time.perf_counter()-started
    report_path=dest/'simulation_report.json'
    if proc.returncode!=0 or not report_path.exists():
        raise RuntimeError(f'FAILED {dest}: rc={proc.returncode} (inspect logs)')
    report=json.loads(report_path.read_text())
    if report.get('status')!='COMPLETED' or abs(float(report.get('simulated_seconds',-1))-seconds)>1e-12:
        raise RuntimeError(f'INCOMPLETE {dest}: {report.get("status")} {report.get("simulated_seconds")}')
    if len(report.get('analog_channels',[]))!=13 or len(report.get('digital_channels',[]))!=4:
        raise RuntimeError(f'Wrong A010 channels in {dest}')
    if not (dest/'out.pevt').exists():raise RuntimeError(f'Missing PEVT: {dest}')
    return {'wall_s':wall,'cpu_s':usage.ru_utime+usage.ru_stime,
            'cpu_user_s':usage.ru_utime,'cpu_system_s':usage.ru_stime,
            'rss_kib':usage.ru_maxrss,'pevt_bytes':(dest/'out.pevt').stat().st_size,
            'pevt_sha256':sha(dest/'out.pevt'),
            'transactions':report.get('transactions'),'root_queries':report.get('root_queries'),
            'status':report['status'],'output':str(dest),'report':str(report_path)}

def compile_allocation_observer(source,output):
    observer=source/'scripts/profiling/stage_c/alloc_observer.c'
    if not observer.exists():return None
    lib=output/'libpulse_alloc_observer.so'
    run(['cc','-shared','-fPIC','-O2','-o',lib,observer,'-ldl'])
    return lib

def audit_pair(croot,droot,co,do,out):
    script=croot/'scripts/stage_c_verify.py'
    dest=out/'pevt_comparison.json'
    # Strict regression is optional.  Exploratory validation is done after replay.
    result=subprocess.run([sys.executable,str(script),
          '--baseline',co/'out.pevt','--candidate',do/'out.pevt',
          '--baseline-report',co/'simulation_report.json',
          '--candidate-report',do/'simulation_report.json','--out',dest],capture_output=True,text=True)
    if result.returncode!=0:
        raise RuntimeError(f'PEVT DIFFERENCE: {dest}\n{result.stdout}\n{result.stderr}')
    return dest

def replay_and_compare(croot,droot,co,do,out):
    r=[]
    for label,root,src in [('C',croot,co),('D',droot,do)]:
        dest=out/f'replay-{label}';dest.mkdir(parents=True,exist_ok=False)
        with (dest/'replay.log').open('w') as log:
            run([executable(root,'pulse-replay'),src,'--out',dest],stdout=log,timeout=240)
        wave=dest/'out.pewave.npz'
        if not wave.is_file():raise RuntimeError(f'Replay did not produce {wave}')
        r.append(wave)
    # Hash .npy member payloads rather than zip container metadata, following stage_c_verify.py.
    import zipfile
    def members(f):
        with zipfile.ZipFile(f) as z:
            return {name:hashlib.sha256(z.read(name)).hexdigest() for name in z.namelist() if not name.endswith('/')}
    a,b=map(members,r)
    if a!=b:raise RuntimeError('REPLAY WAVEFORM BYTE DIFFERENCE: 17-channel comparison failed')
    return {'waveform_members':len(a),'byte_identical':True}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=pathlib.Path,required=True)
    p.add_argument('--case',type=pathlib.Path,required=True,help='A010 case directory containing pulse/ and provenance.json')
    p.add_argument('--out',type=pathlib.Path,required=True)
    p.add_argument('--base-ref',default=BASE_REF)
    p.add_argument('--repeats',type=int,default=3)
    p.add_argument('--strict',action='store_true',help='Require Stage C bitwise PEVT and replay, rather than exploratory numerical comparison')
    p.add_argument('--skip-tests',action='store_true')
    p.add_argument('--skip-replay',action='store_true')
    p.add_argument('--skip-alloc-count',action='store_true')
    p.add_argument('--skip-perf',action='store_true')
    args=p.parse_args()
    if os.name!='posix' or not hasattr(os,'wait4'):raise SystemExit('Run on native Linux x86_64')
    if args.repeats<3:raise SystemExit('At least 3 paired timing runs required')
    repo=args.repo.resolve();case=args.case.resolve();out=args.out.resolve()
    if out.exists():raise SystemExit(f'Output directory already exists, refusing overwrite: {out}')
    if not (case/'pulse/netlist.md').is_file():raise SystemExit('A010 input not found')
    out.mkdir(parents=True,exist_ok=False)
    # Both worktrees are local; NO git fetch, clone or network access.
    (out/'checkout.log').write_text('Local git worktree only.\n')
    with (out/'checkout.log').open('a') as log:
        resolved=run(['git','-C',repo,'rev-parse',args.base_ref],stdout=subprocess.PIPE).stdout.strip()
        run(['git','-C',repo,'worktree','add','--detach',out/'stage-c',resolved],stdout=log)
    croot=out/'stage-c';droot=out/'stage-d'
    shutil.copytree(croot,droot,ignore=shutil.ignore_patterns('.git','build-*','build','build-linux','*.o','*.so','*.a'))
    patch=pathlib.Path(__file__).with_name('apply_stage_d.py')
    with (out/'apply.log').open('w') as log:
        run([sys.executable,patch,'--repo',droot,'--manifest',out/'patch-manifest.json'],stdout=log)
    build_solver(croot,not args.skip_tests,out/'build-c.log')
    build_solver(droot,not args.skip_tests,out/'build-d.log')
    binary={'C':executable(croot,'pulse-solver'),'D':executable(droot,'pulse-solver')}
    netlist={}
    for label,root in [('C',croot),('D',droot)]:
        netlist[label]=isolated_case(case,root,out/f'model-{label}')
    # Interleave order to reduce thermal/turbo drift.
    rows=[]
    for i in range(args.repeats):
        order=['C','D'] if i%2==0 else ['D','C']
        for label in order:
            where=out/f'run-{i+1}-{label}'
            row=run_one(binary[label],netlist[label],where)
            rows.append({'pair':i+1,'variant':label,**row})
            (out/'progress.json').write_text(json.dumps(rows,indent=2)+'\n')
        if args.strict:
            audit_dir=out/f'pair-{i+1}-verification'
            audit_dir.mkdir(exist_ok=True)
            audit_pair(croot,droot,out/f'run-{i+1}-C',out/f'run-{i+1}-D',audit_dir)
    wave=None
    if not args.skip_replay:
        if args.strict:
            wave=replay_and_compare(croot,droot,out/'run-1-C',out/'run-1-D',out)
        else:
            for label,root in [('C',croot),('D',droot)]:
                dest=out/f'replay-{label}'
                dest.mkdir(exist_ok=False)
                with (dest/'replay.log').open('w') as log:
                    run([executable(root,'pulse-replay'),out/f'run-1-{label}','--out',dest],stdout=log,timeout=240)
            from validate_exploratory import compare
            wave=compare(croot,out/'run-1-C',out/'run-1-D',out/'replay-C',out/'replay-D')
            (out/'engineering-compare.json').write_text(json.dumps(wave,indent=2)+'\n')
    alloc={}
    if not args.skip_alloc_count:
        lib=compile_allocation_observer(croot,out)
        if lib:
            for label in ['C','D']:
                where=out/f'alloc-{label}'
                run_one(binary[label],netlist[label],where,alloc=lib)
                path=where/'allocations.json'
                if not path.exists():raise RuntimeError(f'Allocation observer did not produce {path}')
                alloc[label]=json.loads(path.read_text())
        else:alloc={'warning':'observer unavailable, not measured'}
    profiles={}
    if not args.skip_perf:
        profiler=pathlib.Path(__file__).with_name('perf_three_factors.py')
        for label in ['C','D']:
            dest=out/f'perf-{label}'
            with (out/f'perf-{label}.log').open('w') as log:
                run([sys.executable,profiler,'--binary',binary[label],
                     '--netlist',netlist[label],'--out',dest],stdout=log,timeout=360)
            profiles[label]=json.loads((dest/'three_factors.json').read_text())
    def allocation_summary(value):
        if not isinstance(value,dict) or 'threads' not in value:return None
        apis=[a for t in value.get('threads',[]) for a in t.get('apis',[])]
        return {'request_calls':sum(int(a.get('calls',0)) for a in apis),
                'requested_bytes':sum(int(a.get('requested_bytes',0)) for a in apis),
                'free_calls':sum(int(t.get('free_calls',0)) for t in value['threads']),
                'slot_overflow':value.get('slot_overflow',0)}
    allocation_change={label:allocation_summary(alloc.get(label)) for label in ('C','D')}
    if allocation_change['C'] and allocation_change['D']:
        a=allocation_change['C']['request_calls'];b=allocation_change['D']['request_calls']
        allocation_change['request_reduction_percent']=100*(a-b)/a if a else None
    profile_deltas={}
    if profiles.get('C') and profiles.get('D'):
        for key in ('memory_allocator','mode_binding','pevt_archive'):
            c=profiles['C']['categories'][key]
            d=profiles['D']['categories'][key]
            cv=c['sampled_cpu_seconds_approx'];dv=d['sampled_cpu_seconds_approx']
            profile_deltas[key]={'C_sampled_cpu_seconds':cv,'D_sampled_cpu_seconds':dv,
                'estimated_reduction_percent':100*(cv-dv)/cv if cv else None,
                'C_exclusive_percent':c['exclusive_percent'],'D_exclusive_percent':d['exclusive_percent']}
    with (out/'timing.csv').open('w',newline='') as f:
        fields=['pair','variant','wall_s','cpu_s','cpu_user_s','cpu_system_s','rss_kib',
                'pevt_bytes','pevt_sha256','transactions','root_queries','status','output','report']
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    median={label:statistics.median(row['wall_s'] for row in rows if row['variant']==label)
            for label in ['C','D']}
    report={'status':('STRICT_PASS' if args.strict else 'EXPLORATORY_PASS' if wave and wave.get('status','').startswith('PASS') else 'EXPLORATORY_FAILED') if wave else 'UNVALIDATED_WAVEFORMS',
        'reference_commit':resolved,'model':str(case),'run_count_each':args.repeats,'verification_mode':'bitwise' if args.strict else 'engineering',
        'median_wall_s':median,'speedup_c_div_d':median['C']/median['D'],
        'profile_cpu_categories':profiles,'profile_three_factor_deltas':profile_deltas,'allocation_summary':allocation_change,
        'per_category_percent_changes':{k:{'C':profiles.get('C',{}).get('categories',{}).get(k,{}).get('exclusive_percent'),
                                            'D':profiles.get('D',{}).get('categories',{}).get(k,{}).get('exclusive_percent')}
                                       for k in ('memory_allocator','mode_binding','pevt_archive')},
        'median_cpu_s':{label:statistics.median(row['cpu_s'] for row in rows if row['variant']==label)
                for label in ['C','D']},'waveform_check':wave,'allocations':alloc,
        'notes':['wall durations include process startup through exit',
                 'exploratory mode requires valid PEVT, complete status, same event sequence and bounded waveform difference; strict is opt-in',
                 '50ms with identical netlist, controls and SAVE_DT',
                 'source hash provenance section 1 can differ; sections 2-10 must match',
                 'allocation observer runs NOT used for wall speed comparison',
                 'profile CPU categories sampled in independent perf runs, not timing runs']}
    (out/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='allocations'},indent=2))

if __name__=='__main__':main()
