#!/usr/bin/env python3
"""Run the original full C002 case; never rewrite netlist or controller bytes."""
import argparse
import hashlib
import json
import pathlib
import platform
import shutil
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
CASE_REVISION = '13660577132de41c37c1c47576c02941d21c532a'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case-set', type=pathlib.Path, required=True)
    p.add_argument('--binary', type=pathlib.Path, default=ROOT/'build-linux/pulse-solver')
    p.add_argument('--cc', default='gcc')
    p.add_argument('--out', type=pathlib.Path, required=True)
    a = p.parse_args()
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        p.error('native Linux x86-64 is required')
    binary = a.binary.resolve()
    if binary.read_bytes()[:5] != b'\x7fELF\x02':
        p.error('solver must be a native ELF64 binary')
    cases = a.case_set.resolve()
    revision = subprocess.check_output(['git', '-C', str(cases), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != CASE_REVISION:
        p.error('case-set revision must be '+CASE_REVISION)
    case = cases/'rohm-c002-d-boost'
    provenance = json.loads((case/'provenance.json').read_text(encoding='utf-8'))
    originals = {}
    for entry in provenance['pulse_inputs']:
        source = case/entry['file']
        committed = subprocess.check_output(['git', '-C', str(cases), 'show', revision+':rohm-c002-d-boost/'+entry['file']])
        if sha(source) != entry['sha256'] or source.read_bytes() != committed:
            p.error('original input integrity failure: '+str(source))
        originals[entry['file']] = sha(source)
    text = (case/'pulse/netlist.md').read_text(encoding='utf-8-sig')
    if '.TRAN T_END=0.29999999999999999 SAVE_DT=1.9999999999999999e-07' not in text:
        p.error('unexpected original simulation parameters')
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)  # preserve all previous runs
    model = out/'model'
    shutil.copytree(case/'pulse', model, ignore=shutil.ignore_patterns('.pulse_modules'))
    ledger = {'platform': platform.platform(), 'machine': platform.machine(),
              'timing_environment': 'GitHub Actions' if 'GITHUB_ACTIONS' in __import__('os').environ else 'local Linux',
              'case_set_revision': revision, 'input_sha256': originals,
              'solver_sha256': sha(binary), 'target_seconds': 0.3, 'save_dt': 2e-7,
              'status': 'NOT_RUN'}
    def save():
        (out/'benchmark.json').write_text(json.dumps(ledger, indent=2)+'\n', encoding='utf-8')
    save()
    build = [sys.executable, str(ROOT/'scripts/build_software.py'), str(model/'netlist.md'), '--cc', a.cc]
    with (out/'controller_build.log').open('w', encoding='utf-8') as log:
        result = subprocess.run(build, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        ledger.update(status='CONTROLLER_BUILD_FAILED', returncode=result.returncode);save();return 1
    if (model/'.pulse_modules/CTRL.so').read_bytes()[:5] != b'\x7fELF\x02':
        raise RuntimeError('controller is not ELF64')
    command = [str(binary), str(model/'netlist.md'), '--out', str(out/'pulse')]
    ledger.update(command=command, status='RUNNING');save()
    start = time.perf_counter()
    with (out/'stdout.txt').open('w', encoding='utf-8') as stdout, (out/'stderr.txt').open('w', encoding='utf-8') as stderr:
        result = subprocess.run(command, stdout=stdout, stderr=stderr)
    ledger.update(wall_seconds=time.perf_counter()-start, returncode=result.returncode)
    report_path = out/'pulse/simulation_report.json'
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding='utf-8'))
        for key in ('status', 'simulated_seconds', 'effective_T_END', 'effective_SAVE_DT',
                    'transactions', 'diagnostic', 'T_atom', 'software_modules', 'software_states'):
            ledger[key] = report.get(key)
    else:
        ledger['status'] = 'NO_RUN_REPORT'
    ledger['inputs_unchanged'] = all(sha(model/pathlib.Path(f).name)==h for f,h in originals.items())
    ledger['passed'] = (result.returncode == 0 and ledger['status'] == 'COMPLETED'
                        and ledger.get('simulated_seconds') == 0.3 and ledger['inputs_unchanged'])
    save()
    print(json.dumps(ledger, indent=2))
    return 0 if ledger['passed'] else 1

if __name__ == '__main__':
    sys.exit(main())
