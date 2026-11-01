#!/usr/bin/env python3
"""Compare complete PULSE C002 output with unmodified case-set PLECS CSVs.

Statistics are computed over the full reference grid (0..0.3 s). Point errors
are diagnostic: a 1 us capture grid cannot resolve every switching edge.
This does not replace the historical windowed acceptance procedure.
"""
import argparse
import hashlib
import json
import pathlib
import numpy as np

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case-set', type=pathlib.Path, required=True)
    p.add_argument('--run', type=pathlib.Path, required=True, help='run_c002_linux.py output directory')
    p.add_argument('--out', type=pathlib.Path, required=True)
    a = p.parse_args()
    case = a.case_set/'rohm-c002-d-boost'
    provenance = json.loads((case/'provenance.json').read_text(encoding='utf-8'))
    report = json.loads((a.run/'pulse/simulation_report.json').read_text(encoding='utf-8'))
    if report['status'] != 'COMPLETED' or report['simulated_seconds'] != 0.3:
        p.error('complete 0.3 s PULSE output required; prefix comparison cannot pass')
    segments = []
    hashes = {}
    for entry in provenance['csv_exports']:
        source = case/entry['file']
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if digest != entry['sha256']:
            p.error('reference SHA256 mismatch: '+str(source))
        hashes[entry['file']] = digest
        segments.append(np.atleast_1d(np.genfromtxt(source, delimiter=',', names=True)))
    reference = np.concatenate(segments)
    rt = reference['time_s']
    if rt[0] != 0 or rt[-1] != 0.3 or not np.all(np.diff(rt)>0):
        p.error('reference must cover full 0..0.3 s in increasing time order')
    checks = []
    errors = {}
    with np.load(a.run/'pulse/out.pewave.npz', allow_pickle=False) as wave:
        t = wave['time']
        if not np.all(np.isfinite(t)) or t[0] != 0 or t[-1] != 0.3 or not np.all(np.diff(t)>0):
            p.error('PULSE waveform does not cover the full interval')
        metadata = json.loads(str(wave['metadata_json']))
        channels = {s['name']: s['id'] for s in metadata['signals']}
        for channel in provenance['channels']:
            name = channel['pulse']
            raw = wave[channels[name]].astype(float)
            ref = reference[name]
            if not np.all(np.isfinite(raw)) or not np.all(np.isfinite(ref)):
                p.error('nonfinite samples in '+name)
            actual = np.interp(rt, t, raw)  # no time shift, scaling or reference rewriting
            delta = actual-ref
            errors[name] = {'rmse': float(np.sqrt(np.mean(delta**2))),
                            'max_abs': float(np.max(np.abs(delta)))}
            for metric, calculate in [('mean', np.mean), ('rms', lambda x: np.sqrt(np.mean(x*x))), ('max', np.max)]:
                expected, measured = float(calculate(ref)), float(calculate(actual))
                tolerance = channel['atol']+0.01*abs(expected)
                checks.append({'channel': name, 'metric': metric, 'reference': expected,
                               'actual': measured, 'tolerance': tolerance,
                               'passed': abs(measured-expected)<=tolerance})
    summary = {'method': 'full reference-grid mean/rms/max; original channel atol + 1%; no alignment shifts',
               'limitation': 'distinct from historical windowed acceptance; point errors diagnostic only',
               'reference_sha256': hashes, 'checks': checks, 'waveform_errors': errors,
               'statistics_passed': sum(c['passed'] for c in checks), 'statistics_total': len(checks),
               'passed': all(c['passed'] for c in checks)}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open('x', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, allow_nan=False);f.write('\n')
    print(json.dumps(summary, indent=2))
    return 0 if summary['passed'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
