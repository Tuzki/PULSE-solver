#!/usr/bin/env python3
"""External measurement harness; never edits solver/model/controller inputs."""
import argparse
import ctypes
import datetime
import hashlib
import json
import os
import pathlib
import platform
import shutil
import statistics
import subprocess
import sys
import time


def sha(path):
    h = hashlib.sha256()
    with pathlib.Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary', type=pathlib.Path, required=True)
    p.add_argument('--case', type=pathlib.Path, required=True)
    p.add_argument('--build-software', type=pathlib.Path, required=True)
    p.add_argument('--out', type=pathlib.Path, required=True)
    p.add_argument('--campaign', action='store_true')
    p.add_argument('--single', type=float)
    p.add_argument('--profile', action='store_true')
    p.add_argument('--sampler', type=pathlib.Path)
    p.add_argument('--replay', type=pathlib.Path)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    a.binary = a.binary.resolve()
    a.case = a.case.resolve()
    windows = platform.system() == 'Windows'
    ledger = {'platform': platform.platform(), 'machine': platform.machine(),
              'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'binary': str(a.binary), 'binary_sha256': sha(a.binary),
              'python': sys.version, 'command': sys.argv, 'runs': [],
              'scope': 'trajectory; original full 17 public channels; unchanged SAVE_DT=0.1us',
              'timing': 'wall to COMPLETED after archive write; process exit separately; process user/system CPU via OS; replay separate'}
    meta = json.loads((a.case / 'provenance.json').read_text(encoding='utf8'))
    ledger['input_sha256'] = {}
    for item in meta['pulse_inputs']:
        digest = sha(a.case / item['file'])
        assert digest == item['sha256'], item['file']
        ledger['input_sha256'][item['file']] = digest
    model = a.out / 'model'
    if not model.exists():
        shutil.copytree(a.case / 'pulse', model, ignore=shutil.ignore_patterns('.pulse_modules'))
    prep = subprocess.run([sys.executable, str(a.build_software), str(model / 'netlist.md')],
                          text=True, capture_output=True, encoding='utf8')
    (a.out / 'controller-build.txt').write_text(prep.stdout + prep.stderr, encoding='utf8')
    prep.check_returncode()

    def save():
        (a.out / 'ledger.json').write_text(json.dumps(ledger, indent=2) + '\n', encoding='utf8')

    def execute(label, command, profile, destination, sampling=False):
        destination.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env.pop('PULSE_PROFILE_PHASES', None)
        env.pop('PULSE_WALL_SECONDS', None)
        if profile:
            env['PULSE_PROFILE_PHASES'] = '1'
        if not windows:
            import resource
            before = resource.getrusage(resource.RUSAGE_CHILDREN)
        started = datetime.datetime.now(datetime.timezone.utc).isoformat()
        lines = []; notified = None; sampler = None
        start = time.perf_counter()
        with (destination / 'stderr.txt').open('w', encoding='utf8') as err:
            proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=err, text=True,
                                    encoding='utf8', env=env)
            if sampling and a.sampler:
                sampler = subprocess.Popen([str(a.sampler), str(proc.pid),
                                            str(destination / 'windows-samples.tsv'), '5'],
                                           stdout=(destination / 'sampler-stdout.txt').open('w'),
                                           stderr=(destination / 'sampler-stderr.txt').open('w'))
            for line in proc.stdout:
                lines.append(line)
                if line.startswith('  "status":') and '"COMPLETED"' in line:
                    notified = time.perf_counter() - start
            rc = proc.wait()
            exited = time.perf_counter() - start
            if windows:
                from ctypes import wintypes
                kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
                kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
                times = [wintypes.FILETIME() for _ in range(4)]
                if not kernel32.GetProcessTimes(int(proc._handle), *[ctypes.byref(t) for t in times]):
                    raise ctypes.WinError(ctypes.get_last_error())
                cpu = [(t.dwHighDateTime * 2**32 + t.dwLowDateTime) / 1e7 for t in times[2:]]
                system, user = cpu
            else:
                after = resource.getrusage(resource.RUSAGE_CHILDREN)
                user = after.ru_utime - before.ru_utime
                system = after.ru_stime - before.ru_stime
        (destination / 'stdout.txt').write_text(''.join(lines), encoding='utf8')
        if sampler:
            sampler_rc = sampler.wait(timeout=30)
            assert sampler_rc == 0, 'Windows external sampling failed'
        entry = {'label': label, 'profile_enabled': profile, 'sampling': sampling,
                 'started_utc': started, 'command': command, 'pid': proc.pid, 'returncode': rc,
                 'completion_wall_seconds': notified, 'exit_wall_seconds': exited,
                 'cpu_user_seconds': user, 'cpu_system_seconds': system, 'cpu_total_seconds': user + system,
                 'output_path': str(destination)}
        report_path = destination / 'simulation_report.json'
        if report_path.exists():
            entry['report'] = json.loads(report_path.read_text(encoding='utf8'))
            report = entry['report']
            assert len(report['analog_channels']) == 13 and len(report['digital_channels']) == 4
            assert report['performance_phases']['enabled'] == profile
            assert report['source_sha256'] == 'e820d1dcb9a84707d6f2333ee965ef188e7be78f5a55511cb963f8e71601ab60'
        entry['files'] = {f.name: {'bytes': f.stat().st_size, 'sha256': sha(f)}
                          for f in destination.iterdir() if f.is_file() and f.suffix in ('.pevt', '.json', '.npz')}
        ledger['runs'].append(entry); save()
        assert rc == 0, label
        print(label, 'wall', notified or exited, 'CPU', user + system, flush=True)
        return entry

    plan = [(a.single, a.profile, 'single')] if a.single is not None else []
    if a.campaign:
        plan = [(.002, True, '2ms_on'), (.005, True, '5ms_on')]
        # Interleave to limit slow drift bias while retaining 3 independent runs.
        plan += [(.020, on, f'20ms_{"on" if on else "off"}_{i}') for i in range(1, 4) for on in (False, True)]
        plan += [(.5, False, '500ms_off'), (.5, True, '500ms_on')]
    assert plan
    save()
    for end, profile, label in plan:
        dest = a.out / label
        if (dest / 'simulation_report.json').exists():
            raise RuntimeError('Use a fresh output directory: ' + str(dest))
        command = [str(a.binary), str(model / 'netlist.md'), '--t-end', str(end),
                   '--output-format', 'trajectory', '--out', str(dest)]
        print('START', label, flush=True)
        result = execute(label, command, profile, dest, sampling=a.sampler is not None)
        assert result['report']['status'] == 'COMPLETED' and result['report']['simulated_seconds'] == end
        if a.replay and label == '500ms_off':
            dest = a.out / 'reconstruction_500ms_off'
            execute('reconstruction_500ms_off', [str(a.replay), result['output_path'], '--out', str(dest)], False, dest)
    if a.campaign:
        medians = {v: statistics.median(e['completion_wall_seconds'] for e in ledger['runs']
                                      if e['label'].startswith('20ms_' + v)) for v in ('off', 'on')}
        ledger['20ms_overhead'] = {'median_seconds': medians,
                                   'percent': 100 * (medians['on'] / medians['off'] - 1)}
    ledger['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save()


if __name__ == '__main__':
    main()
