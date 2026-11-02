#!/usr/bin/env python3
"""Bounded A010 event-generation benchmark, followed by separate replay checks.

Abort the batch as soon as event generation exceeds 5x freshly measured PLECS.
Historical original-PULSE output is read-only and explicitly marked as reused.
"""
import argparse
import io
import json
import pathlib
import shutil
import subprocess
import time
import xmlrpc.client
import numpy as np
from scipy.io import loadmat
from benchmark_all_platforms import sha, compare_arrays, statistics
from benchmark_c002_end_to_end import Transport
from read_pevt import read, summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case-set', type=pathlib.Path, required=True)
    p.add_argument('--out', type=pathlib.Path, required=True)
    p.add_argument('--baseline', type=pathlib.Path, required=True)
    p.add_argument('--native-out', default='/root/pulse-pevt-a010-20261102')
    a = p.parse_args()
    root = pathlib.Path(__file__).resolve().parents[1]
    case_name = 'rohm-a010-dot-totem-pole-pfc-sync'
    case = a.case_set.resolve()/case_name
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    meta = json.loads((case/'provenance.json').read_text(encoding='utf-8'))
    previous = json.loads((a.baseline/'ledger.json').read_text(encoding='utf-8'))
    prefix = ['wsl.exe', '-d', 'Ubuntu-24.04', '-u', 'root', '--exec']
    native_root = a.native_out
    binaries = {'linux': '/root/pulse-pevt/build-linux/pulse-solver',
                'win': str(root/'build-event-windows/pulse-solver.exe')}
    ledger = {'case': case_name, 'target_seconds': meta['original_end_seconds'],
              'policy': 'Stop the entire batch if event generation exceeds 5x fresh PLECS; replay excluded.',
              'runs': {}, 'validation': {}, 'input_sha256': {}, 'binaries': {}, 'finished': False}
    def save():
        (out/'ledger.json').write_text(json.dumps(ledger, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    for entry in meta['pulse_inputs']+meta['csv_exports']+[{'file':meta['capture_model'], 'sha256':meta['capture_sha256']}]:
        digest = sha(case/entry['file'])
        if digest != entry['sha256']: raise ValueError('input integrity failed: '+entry['file'])
        ledger['input_sha256'][entry['file']] = digest
    for platform, binary in binaries.items():
        if platform == 'linux':
            description = subprocess.check_output(prefix+['file', binary], text=True).strip()
            if 'ELF 64-bit' not in description or 'x86-64' not in description: raise ValueError('native ELF required')
            digest = subprocess.check_output(prefix+['sha256sum', binary], text=True).split()[0]
        else: description, digest = 'Windows native x86-64', sha(binary)
        ledger['binaries'][platform] = {'path':binary, 'sha256':digest, 'description':description}
        old = previous['binaries'][platform+'_original']
        actual = subprocess.check_output(prefix+['sha256sum', old['path']], text=True).split()[0] if platform=='linux' else sha(old['path'])
        if actual != old['sha256']: raise ValueError('original binary changed')
        baseline_dir = a.baseline.resolve()/case_name/(platform+'_original')
        result = previous['cases'][case_name]['runs'][platform+'_original']
        if result['status'] != 'COMPLETED' or result['simulated_seconds'] != meta['original_end_seconds']: raise ValueError('incomplete baseline')
        for name, identity in result['files'].items():
            if sha(baseline_dir/name) != identity['sha256']: raise ValueError('baseline artifact changed')
        ledger['runs'][platform+'_original'] = {**result, 'reused_from':str(baseline_dir), 'measured_in_this_session':False}
    save()
    rpc = xmlrpc.client.ServerProxy('http://127.0.0.1:1080', transport=Transport(), allow_none=True)
    try:
        rpc.plecs.load((case/meta['capture_model']).as_posix())
        count = round(meta['original_end_seconds']/meta['csv_grid_seconds'])+1
        opts = {'OutputFormat':'MatFile', 'SolverOpts':{'TimeSpan':meta['original_end_seconds'],
                'OutputTimesOption':'specified', 'OutputTimes':np.linspace(0,meta['original_end_seconds'],count).tolist(), 'Timeout':900}}
        print('START PLECS', flush=True)
        start = time.perf_counter()
        data = rpc.plecs.simulate(meta['capture_name'], opts)
        seconds = time.perf_counter()-start
        (out/'plecs.mat').write_bytes(data.data)
        fresh = loadmat(io.BytesIO(data.data))
        if fresh['Time'].size != count or fresh['Time'].ravel()[-1] != meta['original_end_seconds'] or not np.isfinite(fresh['Values']).all(): raise ValueError('incomplete PLECS')
        ledger['runs']['PLECS'] = {'seconds':seconds, 'status':'COMPLETED', 'simulated_seconds':meta['original_end_seconds'], 'bytes':len(data.data)}
    except Exception as e:
        ledger['runs']['PLECS'] = {'status':'FAILED','error':str(e)}
        ledger['stopped_reason'] = 'No valid fresh PLECS timing; event generation not started.'
        save()
        raise
    finally:
        try: rpc.plecs.close(meta['capture_name'])
        except Exception: pass
    limit = 5*seconds
    ledger['event_generation_limit_seconds'] = limit
    save()
    print(f'DONE PLECS {seconds:.6f}s; generation deadline {limit:.6f}s', flush=True)
    for platform in ('linux','win'):
        model = out/('model-'+platform)
        shutil.copytree(case/'pulse', model, ignore=shutil.ignore_patterns('.pulse_modules'))
        if platform == 'linux':
            native_model = native_root+'/model-linux'
            mapped = subprocess.check_output(prefix+['wslpath','-u',str(model)], text=True).strip()
            subprocess.run(prefix+['mkdir','-p',native_model], check=True)
            subprocess.run(prefix+['cp','-a',mapped+'/.',native_model], check=True)
            prepare = prefix+['python3','/root/pulse-pevt/scripts/build_software.py',native_model+'/netlist.md']
            output = native_root+'/linux_event'
            solver = [binaries[platform],native_model+'/netlist.md','--t-end',str(meta['original_end_seconds']),'--output-format','trajectory','--out',output]
            # timeout owns and kills the native ELF, including if the WSL launcher exits.
            command = prefix+['timeout','--signal=KILL',f'{limit:.9f}s']+solver
        else:
            prepare = [__import__('sys').executable,str(root/'scripts/build_software.py'),str(model/'netlist.md')]
            output = str(out/'win_event')
            command = [binaries[platform],str(model/'netlist.md'),'--t-end',str(meta['original_end_seconds']),'--output-format','trajectory','--out',output]
        prepared = subprocess.run(prepare,capture_output=True,text=True,encoding='utf-8')
        (out/(platform+'-module-build.txt')).write_text(prepared.stdout+prepared.stderr,encoding='utf-8')
        if prepared.returncode: raise RuntimeError('controller compilation failed')
        print('START',platform,'event generation',flush=True)
        start = time.perf_counter()
        with (out/(platform+'-stdout.txt')).open('w',encoding='utf-8') as stdout, (out/(platform+'-stderr.txt')).open('w',encoding='utf-8') as stderr:
            proc = subprocess.Popen(command,stdout=stdout,stderr=stderr)
            timed_out = False
            try: rc = proc.wait(timeout=limit if platform=='win' else limit+5)
            except subprocess.TimeoutExpired:
                proc.kill(); rc = proc.wait(); timed_out = True
        elapsed = time.perf_counter()-start
        # wsl.exe can expose SIGKILL as exit code 9 rather than shell code 137.
        timed_out = timed_out or (platform=='linux' and (rc in (124,137) or (rc==9 and elapsed>=limit)))
        result = {'seconds':elapsed,'returncode':rc,'status':'TIME_LIMIT_EXCEEDED' if timed_out else 'UNKNOWN','limit_seconds':limit}
        local = out/(platform+'_event')
        local.mkdir(exist_ok=True)
        if platform=='linux':
            mapped = subprocess.check_output(prefix+['wslpath','-u',str(local)],text=True).strip()
            subprocess.run(prefix+['cp','-a',output+'/.',mapped],capture_output=True)
        if (local/'simulation_report.json').exists():
            report = json.loads((local/'simulation_report.json').read_text(encoding='utf-8'))
            result['report'] = report
            if not timed_out: result['status'] = report['status'] if rc==0 else 'OUTPUT_FAILED'
        result['files'] = {f.name:{'bytes':f.stat().st_size,'sha256':sha(f)} for f in local.iterdir() if f.is_file()}
        result['total_bytes'] = sum(f['bytes'] for f in result['files'].values())
        ledger['runs'][platform+'_event'] = result
        save()
        print('DONE',platform,result['status'],f'{elapsed:.6f}s',flush=True)
        if timed_out:
            ledger['stopped_reason'] = platform+' event generation exceeded 5x fresh PLECS; remaining runs and replay not started.'
            save()
            print('BATCH STOPPED: 5x limit',flush=True)
            return 2
        if result['status']!='COMPLETED': raise RuntimeError('event generation failed')
    # Reconstruction is deliberately outside the event-generation timer and limit.
    for platform in ('linux','win'):
        local = out/(platform+'_event')
        ledger['validation'][platform+'_protocol'] = summary(read(local))
        replay = str(pathlib.PurePosixPath(binaries[platform]).parent/'pulse-replay') if platform=='linux' else str(pathlib.Path(binaries[platform]).parent/'pulse-replay.exe')
        replay_out = native_root+'/linux_replay' if platform=='linux' else str(out/'win_replay')
        source = native_root+'/linux_event' if platform=='linux' else str(local)
        print('START',platform,'separate reconstruction',flush=True)
        start = time.perf_counter()
        replay_run = subprocess.run((prefix if platform=='linux' else [])+[replay,source,'--out',replay_out],capture_output=True,text=True,encoding='utf-8')
        elapsed = time.perf_counter()-start
        (out/(platform+'-replay-stdout.txt')).write_text(replay_run.stdout,encoding='utf-8')
        (out/(platform+'-replay-stderr.txt')).write_text(replay_run.stderr,encoding='utf-8')
        if replay_run.returncode: raise RuntimeError('reconstruction failed')
        destination = out/(platform+'_replay')
        if platform=='linux':
            destination.mkdir(exist_ok=True)
            mapped = subprocess.check_output(prefix+['wslpath','-u',str(destination)],text=True).strip()
            subprocess.run(prefix+['cp','-a',replay_out+'/.',mapped],check=True)
        ledger['runs'][platform+'_replay'] = {'status':'COMPLETED','seconds':elapsed}
        old = a.baseline.resolve()/case_name/(platform+'_original')
        equivalence = compare_arrays(old,destination)
        equivalence['event_logs_equal'] = sha(old/'event_log.jsonl')==sha(destination/'event_log.jsonl')
        ledger['validation'][platform+'_equivalence'] = equivalence
        chunks = [np.loadtxt(case/e['file'],delimiter=',',skiprows=1,ndmin=2) for e in meta['csv_exports']]
        csv = np.concatenate(chunks)
        reference = {'Time':csv[:,0].reshape(1,-1),'Values':csv[:,1:].T}
        ledger['validation']['fresh_PLECS_matches_original_CSV'] = bool(np.array_equal(fresh['Time'].ravel(),csv[:,0]) and np.array_equal(fresh['Values'],csv[:,1:].T))
        ledger['validation'][platform+'_vs_PLECS'] = statistics(destination,reference,meta)
        save()
    ledger['finished'] = True
    save()
    print('BENCHMARK FINISHED',flush=True)
    return 0


if __name__=='__main__': raise SystemExit(main())
