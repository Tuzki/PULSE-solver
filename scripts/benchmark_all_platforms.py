#!/usr/bin/env python3
"""Sequential, resumable full-duration case-set benchmark on Windows and WSL.

Never changes input bytes or SAVE_DT. --t-end extends short source windows to
the original PLECS duration. A failed prefix is evidence, never a passing run.
Controller compilation/model loading/output copy are outside simulation timing.
"""
import argparse
import hashlib
import io
import json
import pathlib
import shutil
import subprocess
import time
import xmlrpc.client
import numpy as np
from scipy.io import loadmat
from benchmark_c002_end_to_end import Transport


def sha(path):
    h = hashlib.sha256()
    with pathlib.Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def arrays(path):
    with np.load(path / 'out.pewave.npz', allow_pickle=False) as f:
        meta = json.loads(str(f['metadata_json']))
        return {'time': f['time'], **{s['name']: f[s['id']] for s in meta['signals']}}


def compare_arrays(left, right):
    x, y = arrays(left), arrays(right)
    result = {}
    for name in sorted(x.keys() | y.keys()):
        if name not in x or name not in y or x[name].shape != y[name].shape:
            result[name] = {'bytes_equal': False, 'shape_mismatch': True}
        else:
            a, b = x[name], y[name]
            result[name] = {'bytes_equal': a.dtype == b.dtype and a.tobytes() == b.tobytes(),
                            'max_abs': float(np.max(np.abs(a.astype(float) - b.astype(float))))}
    return {'bitwise_equal': all(v['bytes_equal'] for v in result.values()), 'arrays': result}


def statistics(path, reference, meta):
    wave = arrays(path); t = wave['time']; rt = reference['Time'].ravel()
    if t[0] != 0 or t[-1] != rt[-1] or not np.all(np.diff(t) > 0):
        raise ValueError('incomplete waveform')
    checks, errors = [], {}
    for i, c in enumerate(meta['channels']):
        name = c['pulse']; actual = np.interp(rt, t, wave[name].astype(float))
        ref = reference['Values'][i].astype(float)
        if not np.isfinite(actual).all() or not np.isfinite(ref).all(): raise ValueError('nonfinite')
        delta = actual - ref
        errors[name] = {'rmse': float(np.sqrt(np.mean(delta**2))), 'max_abs': float(np.max(np.abs(delta)))}
        for metric, fn in [('mean', np.mean), ('rms', lambda x: np.sqrt(np.mean(x*x))), ('max', np.max)]:
            expected, observed = float(fn(ref)), float(fn(actual))
            tolerance = c['atol'] + .01 * abs(expected)
            checks.append({'channel': name, 'metric': metric, 'reference': expected, 'actual': observed,
                           'tolerance': tolerance, 'passed': abs(expected-observed) <= tolerance})
    return {'method': 'full original reference grid; mean/rms/max; provenance atol + 1%; no time shift',
            'limitation': 'diagnostic, does not replace historical windowed acceptance',
            'passed': sum(c['passed'] for c in checks), 'total': len(checks), 'checks': checks, 'errors': errors}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case-set', type=pathlib.Path, required=True)
    p.add_argument('--out', type=pathlib.Path, required=True)
    p.add_argument('--win-original', type=pathlib.Path, required=True)
    p.add_argument('--win-event', type=pathlib.Path, required=True)
    p.add_argument('--linux-original', required=True)
    p.add_argument('--linux-event', required=True)
    p.add_argument('--native-out', required=True)
    p.add_argument('--linux-source', default='/root/pulse-trajectory-experiment')
    p.add_argument('--distro', default='Ubuntu-24.04')
    p.add_argument('--only', nargs='*', help='case directory names; default all CSV-completed cases')
    a = p.parse_args(); root = pathlib.Path(__file__).resolve().parents[1]
    a.out = a.out.resolve(); a.out.mkdir(parents=True, exist_ok=True)
    prefix = ['wsl.exe', '-d', a.distro, '-u', 'root', '--exec']
    def linux(*cmd, **kw): return subprocess.run(prefix + list(cmd), check=True, **kw)
    def native(path):
        return subprocess.check_output(prefix + ['wslpath', '-u', str(path)], text=True).strip()
    def save(path, obj): path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    binaries = {'win_original': str(a.win_original.resolve()), 'win_event': str(a.win_event.resolve()),
                'linux_original': a.linux_original, 'linux_event': a.linux_event}
    identities = {}
    for label, binary in binaries.items():
        if label.startswith('linux'):
            description = subprocess.check_output(prefix+['file', binary], text=True).strip()
            if 'ELF 64-bit' not in description or 'x86-64' not in description: raise ValueError('native ELF required')
            digest = subprocess.check_output(prefix+['sha256sum', binary], text=True).split()[0]
        else: description, digest = 'Windows native x86-64', sha(binary)
        identities[label] = {'path': binary, 'sha256': digest, 'description': description}
    manifest = {'timing': 'one Windows perf_counter; sequential commands to COMPLETED notification; process exit separately',
                'baseline_output': 'waveform', 'variant_output': 'trajectory; waveform validation deferred to replay',
                'binaries': identities, 'cases': {}}
    ledger_path = a.out/'ledger.json'
    if ledger_path.exists():
        old = json.loads(ledger_path.read_text(encoding='utf-8'))
        if old['binaries'] != identities: raise ValueError('binary changed: use a fresh output directory')
        manifest = old
    save(ledger_path, manifest)
    for case in sorted(a.case_set.resolve().iterdir()):
        if not (case/'provenance.json').exists() or (a.only and case.name not in a.only): continue
        meta = json.loads((case/'provenance.json').read_text(encoding='utf-8'))
        if meta.get('csv_status') != 'COMPLETED': continue
        dest = a.out/case.name; dest.mkdir(exist_ok=True)
        row = manifest['cases'].setdefault(case.name, {'target_seconds': meta['original_end_seconds'],
              'source_tran': meta.get('pulse_default_tran'), 'history': meta.get('historical_acceptance'),
              'conditions_note': meta.get('conditions_note'), 'runs': {}, 'validation': {}})
        def checkpoint(): save(ledger_path, manifest); save(dest/'result.json', row)
        # Hash every original input and reference before preparing platform copies.
        integrity = {}
        for entry in meta['pulse_inputs'] + meta['csv_exports'] + [{'file': meta['capture_model'], 'sha256': meta['capture_sha256']}]:
            digest = sha(case/entry['file'])
            if digest != entry['sha256']: raise ValueError('source integrity failed: '+str(case/entry['file']))
            integrity[entry['file']] = digest
        row['input_sha256'] = integrity; checkpoint()
        print('CASE', case.name, 'target', row['target_seconds'], flush=True)
        rpc = xmlrpc.client.ServerProxy('http://127.0.0.1:1080', transport=Transport(), allow_none=True)
        if 'PLECS' not in row['runs']:
            try:
                rpc.plecs.load((case/meta['capture_model']).as_posix())
                end = row['target_seconds']; count = round(end/meta['csv_grid_seconds'])+1
                opts = {'OutputFormat': 'MatFile', 'SolverOpts': {'TimeSpan': end, 'OutputTimesOption': 'specified',
                        'OutputTimes': np.linspace(0,end,count).tolist(), 'Timeout': 900}}
                print('START PLECS', flush=True); start = time.perf_counter()
                data = rpc.plecs.simulate(meta['capture_name'], opts); seconds = time.perf_counter()-start
                (dest/'plecs.mat').write_bytes(data.data); ref = loadmat(io.BytesIO(data.data))
                complete = ref['Time'].size == count and ref['Time'].ravel()[-1] == end and np.isfinite(ref['Values']).all()
                row['runs']['PLECS'] = {'seconds': seconds, 'status': 'COMPLETED' if complete else 'INCOMPLETE',
                                        'simulated_seconds': float(ref['Time'].ravel()[-1]), 'samples': ref['Time'].size}
            except Exception as e: row['runs']['PLECS'] = {'status': 'FAILED', 'error': str(e)}
            finally:
                try: rpc.plecs.close(meta['capture_name'])
                except Exception: pass
            checkpoint(); print('DONE PLECS', row['runs']['PLECS'], flush=True)
        if not (case/'pulse/netlist.md').exists():
            for label in binaries: row['runs'][label] = {'status': 'NOT_RUN', 'error': 'no converted PULSE netlist'}
            row['finished'] = True
            checkpoint(); continue
        winmodel = dest/'model-windows'; lnmodel = a.native_out+'/'+case.name+'/model-linux'
        if not winmodel.exists(): shutil.copytree(case/'pulse', winmodel, ignore=shutil.ignore_patterns('.pulse_modules'))
        for platform in ('win','linux'):
            labels = [platform+'_original', platform+'_event']
            if all(label in row['runs'] for label in labels): continue
            try:
                if platform == 'win':
                    prepared = subprocess.run([__import__('sys').executable, str(root/'scripts/build_software.py'), str(winmodel/'netlist.md')],
                                              capture_output=True, text=True, encoding='utf-8')
                else:
                    linux('mkdir', '-p', lnmodel)
                    linux('cp', '-a', native(winmodel)+'/.', lnmodel)
                    linux('rm', '-rf', lnmodel+'/.pulse_modules') # fixed isolated generated-module directory
                    prepared = subprocess.run(prefix+['python3',a.linux_source+'/scripts/build_software.py',lnmodel+'/netlist.md'],
                                              capture_output=True, text=True, encoding='utf-8')
                (dest/(platform+'-module-build.txt')).write_text(prepared.stdout+prepared.stderr, encoding='utf-8')
                if prepared.returncode: raise RuntimeError('module compilation failed; see log')
            except Exception as e:
                for label in labels: row['runs'][label] = {'status': 'PREPARATION_FAILED', 'error': str(e)}
                checkpoint(); continue
            def execute(label, command, output, is_linux):
                print('START', case.name, label, flush=True)
                (dest/label).mkdir(exist_ok=True)
                start = time.perf_counter(); notified = None; lines = []
                with (dest/(label+'-stderr.txt')).open('w',encoding='utf-8') as err:
                    proc = subprocess.Popen((prefix if is_linux else [])+command, stdout=subprocess.PIPE, stderr=err, text=True, encoding='utf-8')
                    for line in proc.stdout:
                        lines.append(line)
                        if line.startswith('  "status":') and '"COMPLETED"' in line: notified = time.perf_counter()-start
                    rc = proc.wait()
                total = time.perf_counter()-start
                (dest/(label+'-stdout.txt')).write_text(''.join(lines),encoding='utf-8')
                if is_linux:
                    local = dest/label
                    local.mkdir(exist_ok=True)
                    cp = subprocess.run(prefix+['cp','-a',output+'/.',native(local)], capture_output=True,text=True)
                local = dest/label
                try: report = json.loads((local/'simulation_report.json').read_text(encoding='utf-8'))
                except Exception:
                    try: report = json.loads(''.join(lines))
                    except Exception: report = {'status':'NO_REPORT'}
                status = report.get('status','NO_REPORT')
                # The solver report can precede a failed archive write/hash.
                if status == 'COMPLETED' and (rc != 0 or notified is None): status = 'OUTPUT_FAILED'
                result = {'seconds': notified, 'process_exit_seconds': total, 'returncode':rc, 'status':report.get('status','NO_REPORT'),
                          'simulated_seconds':report.get('simulated_seconds'), 'diagnostic':report.get('diagnostic'), 'report': report,
                          'files': {f.name: {'bytes':f.stat().st_size,'sha256':sha(f)} for f in local.iterdir() if f.is_file()}}
                result['status'] = status
                if rc and not result.get('diagnostic'):
                    error = (dest/(label+'-stderr.txt')).read_text(encoding='utf-8')
                    try: result['diagnostic'] = json.loads(error)
                    except Exception: result['error'] = error
                result['total_bytes'] = sum(f['bytes'] for f in result['files'].values())
                row['runs'][label] = result; checkpoint()
                print('DONE',label,result['status'],result['simulated_seconds'],round(total,3),result['diagnostic'],flush=True)
                return result
            for label in labels:
                if label in row['runs']: continue
                is_linux = platform == 'linux'
                output = a.native_out+'/'+case.name+'/'+label if is_linux else str(dest/label)
                model = lnmodel+'/netlist.md' if is_linux else str(winmodel/'netlist.md')
                cmd = [binaries[label], model, '--t-end', str(row['target_seconds']), '--out', output]
                if label.endswith('_event'): cmd += ['--output-format','trajectory']
                result = execute(label,cmd,output,is_linux)
                if label.endswith('_event') and result['status'] == 'COMPLETED':
                    replay_label = platform+'_replay'
                    replay = str(pathlib.PurePosixPath(binaries[label]).parent/'pulse-replay') if is_linux else str(a.win_event.resolve().parent/'pulse-replay.exe')
                    replay_out = a.native_out+'/'+case.name+'/'+replay_label if is_linux else str(dest/replay_label)
                    execute(replay_label,[replay,output,'--out',replay_out],replay_out,is_linux)
            left, right = dest/(platform+'_original'), dest/(platform+'_replay')
            if (left/'out.pewave.npz').exists() and (right/'out.pewave.npz').exists():
                try:
                    equivalence = compare_arrays(left,right)
                    equivalence['event_logs_equal'] = sha(left/'event_log.jsonl') == sha(right/'event_log.jsonl')
                    fields = ['status','simulated_seconds','effective_T_END','effective_SAVE_DT','T_atom','transactions','internal_state',
                              'physical_state_view','software_states','software_final_outputs','root_queries','root_failures','mode_compilations','microsteps','rollbacks','matrix_exponentials']
                    old, new = row['runs'][platform+'_original']['report'], row['runs'][platform+'_event']['report']
                    equivalence['changed_solver_fields'] = [k for k in fields if old.get(k)!=new.get(k)]
                    row['validation'][platform+'_event_equivalence'] = equivalence
                except Exception as e: row['validation'][platform+'_event_equivalence'] = {'error':str(e)}
            checkpoint()
        for kind in ('original','replay'):
            x,y = dest/('win_'+kind),dest/('linux_'+kind)
            if (x/'out.pewave.npz').exists() and (y/'out.pewave.npz').exists():
                try: row['validation']['cross_platform_'+kind] = compare_arrays(x,y)
                except Exception as e: row['validation']['cross_platform_'+kind] = {'error':str(e)}
        if (dest/'plecs.mat').exists():
            fresh = loadmat(dest/'plecs.mat')
            # Accuracy always uses the immutable, hash-checked case-set CSV.
            # Fresh PLECS output only supplies this session's timing and a drift check.
            chunks = [np.loadtxt(case/e['file'], delimiter=',', skiprows=1, ndmin=2) for e in meta['csv_exports']]
            csv = np.concatenate(chunks)
            ref = {'Time': csv[:,0].reshape(1,-1), 'Values': csv[:,1:].T}
            row['validation']['fresh_PLECS_matches_original_CSV'] = bool(
                np.array_equal(fresh['Time'].ravel(), csv[:,0]) and np.array_equal(fresh['Values'], csv[:,1:].T))
            for label in ('win_original','win_replay','linux_original','linux_replay'):
                if row['runs'].get(label,{}).get('status') != 'COMPLETED': continue
                try: row['validation'][label+'_vs_PLECS'] = statistics(dest/label, ref, meta)
                except Exception as e: row['validation'][label+'_vs_PLECS'] = {'error':str(e)}
        row['finished'] = True
        checkpoint()
    print('BENCHMARK FINISHED',str(ledger_path),flush=True)


if __name__ == '__main__': main()
