#!/usr/bin/env python3
"""Linux-only, one-round old-B/COW regression. Replay is outside simulation timing."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time

from stage_b_regression import pevt_sections


def fingerprint(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return {'path': str(path), 'bytes': Path(path).stat().st_size, 'sha256': h.hexdigest()}


def run(binary, model, duration, out, limit):
    out.mkdir(parents=True, exist_ok=False)
    command = ['/usr/bin/time', '-v', '-o', str(out/'resource.txt'), str(binary),
               str(model), '--t-end', str(duration), '--output-format', 'trajectory', '--out', str(out)]
    env = os.environ.copy()
    for key in ('PULSE_PROFILE_PHASES', 'PULSE_WALL_SECONDS'):
        env.pop(key, None)
    row = {'command': command, 'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    notified = None
    timed_out = threading.Event()
    start = time.perf_counter()
    with (out/'stdout.txt').open('w') as log, (out/'stderr.txt').open('w') as err:
        p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=err, text=True,
                             env=env, start_new_session=True)
        def stop():
            if p.poll() is None:
                timed_out.set()
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        timer = threading.Timer(limit, stop)
        timer.start()
        try:
            for line in p.stdout:
                log.write(line)
                if line.startswith('  "status":') and '"COMPLETED"' in line:
                    notified = time.perf_counter()-start
            code = p.wait()
        finally:
            timer.cancel()
    row.update(returncode=code, timed_out=timed_out.is_set(),
               completion_wall_seconds=notified, exit_wall_seconds=time.perf_counter()-start)
    if (out/'resource.txt').exists():
        for line in (out/'resource.txt').read_text().splitlines():
            for label, key, cast in [('User time (seconds):', 'cpu_user_seconds', float),
                                     ('System time (seconds):', 'cpu_system_seconds', float),
                                     ('Maximum resident set size (kbytes):', 'peak_rss_kib', int)]:
                if line.strip().startswith(label):
                    row[key] = cast(line.strip()[len(label):].strip())
        if 'cpu_user_seconds' in row and 'cpu_system_seconds' in row:
            row['cpu_seconds'] = row['cpu_user_seconds'] + row['cpu_system_seconds']
    (out/'measurement.json').write_text(json.dumps(row, indent=2)+'\n')
    assert code == 0 and not timed_out.is_set() and notified is not None, row
    return row


def compare(old, new):
    left, right = pevt_sections(old/'out.pevt'), pevt_sections(new/'out.pevt')
    a, b = [(k,n,h) for k,n,h in left if k != 1], [(k,n,h) for k,n,h in right if k != 1]
    assert a == b, 'PEVT payload changed: stop and inspect the first divergent section'
    reports = [json.loads((p/'simulation_report.json').read_text()) for p in (old,new)]
    keys = ('transactions', 'root_queries', 'mode_compilations', 'original_equation_cache',
            'analog_channels', 'digital_channels', 'T_atom', 'effective_SAVE_DT', 'effective_T_END')
    for key in keys:
        assert reports[0].get(key) == reports[1].get(key), key
    assert reports[1]['status'] == 'COMPLETED'
    assert reports[0]['simulated_seconds'] == reports[1]['simulated_seconds']
    assert len(reports[1]['analog_channels']) == 13 and len(reports[1]['digital_channels']) == 4
    files = [fingerprint(p/'out.pevt') for p in (old,new)]
    return {'payload_sha256_equal': True, 'whole_file_sha256_equal': files[0]['sha256']==files[1]['sha256'],
            'whole_files': files, 'baseline_sections': left, 'candidate_sections': right,
            'counters': {k: reports[1].get(k) for k in keys}, 'report': reports[1]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--netlist', type=Path, required=True)
    p.add_argument('--reference-dir', type=Path, required=True)
    p.add_argument('--expected-baseline-sha256', required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--wall-limit', type=float, default=132.8290989997913)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    baseline = fingerprint(a.baseline)
    assert baseline['sha256'] == a.expected_baseline_sha256, 'Wrong baseline executable'
    evidence = {'baseline_binary': baseline, 'candidate_binary': fingerprint(a.candidate),
                'netlist': fingerprint(a.netlist), 'wall_limit_seconds': a.wall_limit,
                'timing': 'command start through archive write and root COMPLETED notification; replay excluded',
                'baseline': json.loads((a.reference_dir/'measurement.json').read_text())}
    def save():
        (a.out/'evidence.json').write_text(json.dumps(evidence, indent=2)+'\n')
    save()
    evidence['prefix_old'] = run(a.baseline,a.netlist,.005,a.out/'5ms-old',a.wall_limit)
    evidence['prefix_new'] = run(a.candidate,a.netlist,.005,a.out/'5ms-cow',a.wall_limit)
    evidence['prefix_comparison'] = compare(a.out/'5ms-old',a.out/'5ms-cow')
    save()
    evidence['full_new'] = run(a.candidate,a.netlist,.5,a.out/'500ms-cow',a.wall_limit)
    evidence['full_comparison'] = compare(a.reference_dir,a.out/'500ms-cow')
    old = evidence['baseline']['completion_wall_seconds']
    new = evidence['full_new']['completion_wall_seconds']
    evidence.update(wall_reduction_percent=100*(old-new)/old, baseline_over_candidate=old/new,
                    baseline_reused=True, repetitions=1)
    save()
    print(json.dumps({k:evidence[k] for k in ('wall_reduction_percent','baseline_over_candidate')},indent=2))


if __name__ == '__main__':
    main()
