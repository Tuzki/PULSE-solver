#!/usr/bin/env python3
"""Retest a fixed archive against preserved full-duration original outputs.

Runs native event generation and replay sequentially on Windows and WSL, using
unchanged case inputs. Original/PLECS timings are explicitly reused evidence.
"""
import argparse
import ctypes
import datetime
import json
import pathlib
import re
import shutil
import subprocess
import sys
import time
import numpy as np
from benchmark_all_platforms import sha, compare_arrays, statistics


def windows_peak(proc):
    class Counters(ctypes.Structure):
        _fields_=[('cb',ctypes.c_uint32),('faults',ctypes.c_uint32)]+[(n,ctypes.c_size_t) for n in
                    ('peak','working','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile')]
    try:
        counter=Counters();counter.cb=ctypes.sizeof(counter)
        fn=ctypes.WinDLL('psapi').GetProcessMemoryInfo
        fn.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint32]
        if fn(int(proc._handle),ctypes.byref(counter),counter.cb) and counter.peak:return counter.peak
    except Exception:pass
    return None


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case-set',type=pathlib.Path,required=True)
    p.add_argument('--case',default='rohm-a010-dot-totem-pole-pfc-sync')
    p.add_argument('--baseline',type=pathlib.Path,required=True,help='preserved batch ledger directory')
    p.add_argument('--out',type=pathlib.Path,required=True)
    p.add_argument('--native-out',required=True)
    p.add_argument('--win-build',type=pathlib.Path,required=True)
    p.add_argument('--linux-build',required=True)
    p.add_argument('--linux-source',required=True)
    p.add_argument('--distro',default='Ubuntu-24.04')
    a=p.parse_args();root=pathlib.Path(__file__).resolve().parents[1]
    a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=False)
    case=a.case_set.resolve()/a.case;meta=json.loads((case/'provenance.json').read_text(encoding='utf-8'))
    old=json.loads((a.baseline/'ledger.json').read_text(encoding='utf-8'))
    original=old['cases'][a.case];target=meta['original_end_seconds']
    for label in ('win_original','linux_original'):
        r=original['runs'][label]
        if r['status']!='COMPLETED' or r['returncode'] or r['simulated_seconds']!=target:raise ValueError('full original result required')
        for name,entry in r['files'].items():
            if sha(a.baseline/a.case/label/name)!=entry['sha256']:raise ValueError('preserved baseline output changed')
    prefix=['wsl.exe','-d',a.distro,'-u','root','--exec']
    def call(cmd):return subprocess.check_output(prefix+cmd,text=True,encoding='utf-8').strip()
    def native(path):return call(['wslpath','-u',str(path)])
    if subprocess.run(prefix+['test','-e',a.native_out]).returncode==0:raise ValueError('native output exists')
    ledger={'case':a.case,'date':datetime.datetime.now().astimezone().isoformat(),'target_seconds':target,
            'baseline_source':str(a.baseline.resolve()),'baseline_binaries':old['binaries'],
            'reused_runs':{k:original['runs'][k] for k in ('PLECS','win_original','linux_original')},
            'timing':'sequential command issued to COMPLETED notification; same host perf_counter; original/PLECS from prior preserved pass',
            'inputs':{},'binaries':{},'runs':{},'validation':{}}
    def save(): (a.out/'result.json').write_text(json.dumps(ledger,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    for entry in meta['pulse_inputs']+meta['csv_exports']:
        h=sha(case/entry['file'])
        if h!=entry['sha256']:raise ValueError('original input/reference hash mismatch')
        ledger['inputs'][entry['file']]=h
    winmodel=a.out/'model-windows';shutil.copytree(case/'pulse',winmodel,ignore=shutil.ignore_patterns('.pulse_modules'))
    linuxmodel=a.native_out+'/model-linux'
    subprocess.run([sys.executable,str(root/'scripts/build_software.py'),str(winmodel/'netlist.md')],check=True)
    subprocess.run(prefix+['mkdir','-p',linuxmodel],check=True)
    subprocess.run(prefix+['cp','-a',native(case/'pulse')+'/.',linuxmodel],check=True)
    subprocess.run(prefix+['python3',a.linux_source+'/scripts/build_software.py',linuxmodel+'/netlist.md'],check=True)
    for platform in ('win','linux'):
        for kind in ('solver','replay'):
            binary=str(a.win_build.resolve()/('pulse-'+('solver' if kind=='solver' else 'replay')+'.exe')) if platform=='win' else a.linux_build+'/pulse-'+kind
            digest=sha(binary) if platform=='win' else call(['sha256sum',binary]).split()[0]
            if platform=='linux' and 'ELF 64-bit' not in call(['file',binary]):raise ValueError('native Linux ELF required')
            ledger['binaries'][platform+'_'+kind]={'path':binary,'sha256':digest}
    save()
    def execute(label,command,out,is_linux):
        print('START',label,flush=True);start=time.perf_counter();notified=None;lines=[]
        with (a.out/(label+'-stderr.txt')).open('w',encoding='utf-8') as err:
            proc=subprocess.Popen((prefix+['/usr/bin/time','-v'] if is_linux else [])+command,
                                  stdout=subprocess.PIPE,stderr=err,text=True,encoding='utf-8')
            for line in proc.stdout:
                lines.append(line)
                if line.startswith('  "status":') and '"COMPLETED"' in line:notified=time.perf_counter()-start
            rc=proc.wait();peak=None if is_linux else windows_peak(proc)
        total=time.perf_counter()-start
        (a.out/(label+'-stdout.txt')).write_text(''.join(lines),encoding='utf-8')
        stderr=(a.out/(label+'-stderr.txt')).read_text(encoding='utf-8')
        if is_linux:
            match=re.search(r'Maximum resident set size \(kbytes\): (\d+)',stderr)
            if match:peak=int(match[1])*1024
            (a.out/label).mkdir()
            subprocess.run(prefix+['cp','-a',out+'/.',native(a.out/label)],check=True)
        path=a.out/label
        try:report=json.loads((path/'simulation_report.json').read_text(encoding='utf-8'))
        except Exception:report={}
        completed=rc==0 and notified is not None
        result={'status':'COMPLETED' if completed else 'FAILED','returncode':rc,'seconds':notified,
                'process_exit_seconds':total,'peak_resident_bytes':peak,'report':report,
                'files':{f.name:{'bytes':f.stat().st_size,'sha256':sha(f)} for f in path.iterdir() if f.is_file()} if path.exists() else {}}
        result['total_bytes']=sum(v['bytes'] for v in result['files'].values())
        ledger['runs'][label]=result;save();print('DONE',label,result['status'],total,'peak',peak,flush=True)
        return completed
    fields=['status','simulated_seconds','effective_T_END','effective_SAVE_DT','T_atom','transactions','internal_state',
            'physical_state_view','software_states','software_final_outputs','root_queries','root_failures','mode_compilations','microsteps','rollbacks','matrix_exponentials']
    chunks=[np.loadtxt(case/e['file'],delimiter=',',skiprows=1,ndmin=2) for e in meta['csv_exports']]
    csv=np.concatenate(chunks);reference={'Time':csv[:,0].reshape(1,-1),'Values':csv[:,1:].T}
    for platform in ('win','linux'):
        is_linux=platform=='linux';label=platform+'_event'
        out=a.native_out+'/'+label if is_linux else str(a.out/label)
        model=linuxmodel+'/netlist.md' if is_linux else str(winmodel/'netlist.md')
        command=[ledger['binaries'][platform+'_solver']['path'],model,'--t-end',str(target),'--output-format','trajectory','--out',out]
        if not execute(label,command,out,is_linux):continue
        report=ledger['runs'][label]['report']
        if report['simulated_seconds']!=target or report['effective_SAVE_DT']!=original['runs'][platform+'_original']['report']['effective_SAVE_DT']:raise ValueError('duration or sampling changed')
        replay_label=platform+'_replay';replay_out=a.native_out+'/'+replay_label if is_linux else str(a.out/replay_label)
        if not execute(replay_label,[ledger['binaries'][platform+'_replay']['path'],out,'--out',replay_out],replay_out,is_linux):continue
        baseline=a.baseline/a.case/(platform+'_original')
        check=compare_arrays(baseline,a.out/replay_label)
        check['event_logs_equal']=len({sha(baseline/'event_log.jsonl'),sha(a.out/label/'event_log.jsonl'),sha(a.out/replay_label/'event_log.jsonl')})==1
        prior=original['runs'][platform+'_original']['report']
        check['changed_solver_fields']=[k for k in fields if prior.get(k)!=report.get(k)]
        ledger['validation'][platform+'_equivalence']=check
        ledger['validation'][platform+'_original_vs_PLECS']=statistics(baseline,reference,meta)
        ledger['validation'][platform+'_replay_vs_PLECS']=statistics(a.out/replay_label,reference,meta)
        ledger['validation'][platform+'_trace_plus_replay_seconds']=ledger['runs'][label]['seconds']+ledger['runs'][replay_label]['seconds']
        save()
    if all((a.out/(p+'_replay/out.pewave.npz')).exists() for p in ('win','linux')):
        ledger['validation']['cross_platform_replay']=compare_arrays(a.out/'win_replay',a.out/'linux_replay')
    ledger['passed']=all(ledger['validation'].get(p+'_equivalence',{}).get('bitwise_equal') and ledger['validation'][p+'_equivalence'].get('event_logs_equal') and not ledger['validation'][p+'_equivalence']['changed_solver_fields'] for p in ('win','linux'))
    save();print('FINISHED equivalence_passed',ledger['passed'],flush=True)
    return 0 if ledger['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
