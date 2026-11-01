#!/usr/bin/env python3
"""Measure start-command to completion-notification wall time for C002.

PLECS is driven by its simulation API; PULSE is a native ELF CLI, optionally
launched from Windows through WSL2. No mouse/UI latency is claimed to be measured.
PLECS document loading, controller compilation and package setup precede the
timed runs. PULSE CLI startup and model parsing remain inside its timed command.
"""
import argparse
import hashlib
import io
import json
import pathlib
import subprocess
import time
import xmlrpc.client

import numpy as np
from scipy.io import loadmat


class Transport(xmlrpc.client.Transport):
    def make_connection(self, host):
        connection = super().make_connection(host)
        connection.timeout = 960
        return connection


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case-set', type=pathlib.Path, required=True)
    parser.add_argument('--pulse-binary', required=True)
    parser.add_argument('--pulse-model', required=True, help='Already prepared original netlist; controller must be built')
    parser.add_argument('--pulse-out', required=True, help='Fresh output directory in the native Linux environment')
    parser.add_argument('--wsl-distro')
    parser.add_argument('--wsl-user', default='root')
    parser.add_argument('--plecs-url', default='http://127.0.0.1:1080')
    parser.add_argument('--out', type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    case = args.case_set.resolve()/'rohm-c002-d-boost'
    provenance = json.loads((case/'provenance.json').read_text(encoding='utf-8'))
    for entry in provenance['pulse_inputs']:
        if sha(case/entry['file']) != entry['sha256']:
            raise RuntimeError('Original case input hash mismatch')
    capture = case/provenance['capture_model']
    if sha(capture) != provenance['capture_sha256']:
        raise RuntimeError('Original PLECS observation model hash mismatch')
    if provenance['original_end_seconds'] != 0.3:
        raise RuntimeError('Full original 0.3 s case required')
    prefix = (['wsl.exe', '-d', args.wsl_distro, '-u', args.wsl_user, '--exec']
              if args.wsl_distro else [])
    native_model = pathlib.PurePosixPath(args.pulse_model)
    native_hashes = {}
    for entry in provenance['pulse_inputs']:
        path = str(native_model.parent/pathlib.PurePosixPath(entry['file']).name)
        content = subprocess.check_output(prefix+['/bin/cat', path])
        digest = hashlib.sha256(content).hexdigest()
        if digest != entry['sha256']:
            raise RuntimeError('Native PULSE input differs from original case: '+path)
        native_hashes[path] = digest
    elf = subprocess.check_output(prefix+['/usr/bin/file', args.pulse_binary], text=True)
    if 'ELF 64-bit' not in elf or 'x86-64' not in elf:
        raise RuntimeError('Native Linux x86-64 ELF solver required')
    # Refuse to reuse output from any earlier native run.
    if subprocess.run(prefix+['/usr/bin/test', '-e', args.pulse_out]).returncode == 0:
        raise RuntimeError('Native output directory already exists')
    ledger = {'timing_standard': 'start-command issued to completion notification received',
              'clock': 'same host Python time.perf_counter for both engines',
              'trigger': 'PLECS simulation API / PULSE CLI command; no literal GUI click latency measured',
              'native_inputs_sha256': native_hashes, 'pulse_elf': elf.strip(),
              'plecs_model_sha256': sha(capture), 'target_seconds': 0.3,
              'run_order': ['PLECS', 'PULSE'], 'runs': {}}
    def save():
        (args.out/'timing.json').write_text(json.dumps(ledger, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    save()
    proxy = xmlrpc.client.ServerProxy(args.plecs_url, allow_none=True, transport=Transport())
    name = provenance['capture_name']
    loaded = False
    try:
        proxy.plecs.load(capture.as_posix())
        loaded = True
        grid = np.linspace(0, 0.3, round(0.3/provenance['csv_grid_seconds'])+1)
        options = {'OutputFormat': 'MatFile', 'SolverOpts': {
            'TimeSpan': 0.3, 'OutputTimesOption': 'specified',
            'OutputTimes': grid.tolist(), 'Timeout': 900}}
        print('PLECS START: simulation command issued', flush=True)
        start = time.perf_counter()
        returned = proxy.plecs.simulate(name, options)
        elapsed = time.perf_counter()-start
        print(f'PLECS FINISHED notification received: {elapsed:.9f} s', flush=True)
        # Validate and save after stopping the notification timer.
        payload = returned.data
        (args.out/'plecs-output.mat').write_bytes(payload)
        data = loadmat(io.BytesIO(payload))
        times = data['Time'].ravel()
        values = data['Values']
        expected_shapes = {(len(provenance['channels']), times.size),
                           (times.size, len(provenance['channels']))}
        if (times.size != grid.size or times[-1] != 0.3 or
                np.max(np.abs(times-grid)) > 1e-12 or values.shape not in expected_shapes or
                not np.isfinite(values).all() or not np.any(values != 0)):
            raise RuntimeError('PLECS did not return complete finite 0.3 s results')
        ledger['runs']['PLECS'] = {'completion_wall_seconds': elapsed,
            'status': 'COMPLETED', 'actual_end_seconds': float(times[-1]),
            'samples': int(times.size), 'output_dt': provenance['csv_grid_seconds'],
            'completion_event': 'synchronous simulate API returned full results'}
        save()
    finally:
        if loaded:
            proxy.plecs.close(name)

    command = prefix+[args.pulse_binary, args.pulse_model, '--out', args.pulse_out]
    print('PULSE START: simulation command issued', flush=True)
    start = time.perf_counter()
    stderr_file = (args.out/'pulse-stderr.txt').open('w', encoding='utf-8')
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=stderr_file,
                               text=True, encoding='utf-8', errors='strict')
    # CLI writes its report only after all simulation files are finalized.
    # Redirect stderr to a file to avoid pipe-buffer deadlock on an error path.
    lines = []
    notification_elapsed = None
    for line in process.stdout:
        lines.append(line)
        if line.startswith('  "status":') and '"COMPLETED"' in line:
            notification_elapsed = time.perf_counter()-start
            print(f'PULSE FINISHED notification received: {notification_elapsed:.9f} s', flush=True)
    returncode = process.wait()
    process_elapsed = time.perf_counter()-start
    stderr_file.close()
    (args.out/'pulse-stdout.json').write_text(''.join(lines), encoding='utf-8')
    report = json.loads(''.join(lines))
    if returncode != 0 or notification_elapsed is None or report.get('simulated_seconds') != 0.3:
        ledger['runs']['PULSE'] = {'status': 'FAILED', 'returncode': returncode,
                                  'process_wall_seconds': process_elapsed, 'diagnostic': report}
        save()
        raise RuntimeError('PULSE failed full-duration notification verification')
    ledger['runs']['PULSE'] = {'status': 'COMPLETED', 'completion_wall_seconds': notification_elapsed,
        'process_exit_wall_seconds': process_elapsed, 'actual_end_seconds': report['simulated_seconds'],
        'transactions': report['transactions'], 'save_dt': report['effective_SAVE_DT'],
        'command': command, 'completion_event': 'CLI root status COMPLETED line received'}
    ledger['pulse_to_plecs_time_ratio'] = notification_elapsed/ledger['runs']['PLECS']['completion_wall_seconds']
    ledger['passed'] = True
    save()
    print(json.dumps(ledger, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
