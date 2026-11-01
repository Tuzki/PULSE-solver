#!/usr/bin/env python3
"""Read-only C002 trajectory accuracy audit against baseline and PLECS.

Keep the existing compare_c002.py acceptance criteria unchanged. Additional
edge-distance metrics are diagnostic and never replace its full-grid verdict.
"""
import argparse
import hashlib
import json
import shutil
import pathlib
import subprocess
import sys
import numpy as np
from scipy.io import loadmat


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_wave(path):
    with np.load(path,allow_pickle=False) as z:
        metadata=json.loads(str(z['metadata_json']))
        return z['time'],{s['name']:z[s['id']] for s in metadata['signals']}


def compare_reference(t,signals,rt,reference,channels,away):
    checks=[];errors={}
    for channel in channels:
        name=channel['pulse'];ref=reference[name]
        actual=np.interp(rt,t,signals[name].astype(float))
        delta=actual-ref
        if not np.isfinite(delta).all():raise RuntimeError('nonfinite comparison values')
        errors[name]={'unit':channel['unit'],
            'full_rmse':float(np.sqrt(np.mean(delta**2))),
            'full_max_abs':float(np.max(np.abs(delta))),
            'away_from_events_rmse':float(np.sqrt(np.mean(delta[away]**2))),
            'away_from_events_max_abs':float(np.max(np.abs(delta[away])))}
        for metric,calculate in [('mean',np.mean),('rms',lambda x:np.sqrt(np.mean(x*x))),('max',np.max)]:
            expected,measured=float(calculate(ref)),float(calculate(actual))
            tolerance=channel['atol']+.01*abs(expected)
            checks.append({'channel':name,'metric':metric,'reference':expected,'actual':measured,
                           'tolerance':tolerance,'passed':abs(measured-expected)<=tolerance})
    return {'checks':checks,'statistics_passed':sum(c['passed'] for c in checks),
            'statistics_total':len(checks),'waveform_errors':errors,'passed':all(c['passed'] for c in checks)}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case-set',type=pathlib.Path,required=True)
    p.add_argument('--benchmark',type=pathlib.Path,required=True)
    p.add_argument('--out',type=pathlib.Path,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    root=pathlib.Path(__file__).resolve().parents[1]
    case=a.case_set.resolve()/'rohm-c002-d-boost'
    provenance=json.loads((case/'provenance.json').read_text(encoding='utf-8'))
    native=a.benchmark.resolve()/'native-results'
    protected=[native/n/'out.pewave.npz' for n in ('original','replay')]
    protected += [native/n/'event_log.jsonl' for n in ('original','trajectory','replay')]
    protected += [a.benchmark.resolve()/'plecs.mat']
    protected += [case/e['file'] for e in provenance['csv_exports']]
    before={str(f):sha(f) for f in protected}
    trajectory=native/'trajectory'
    metadata=json.loads((trajectory/'metadata.json').read_text(encoding='utf-8'))
    for filename,expected in metadata['sha256'].items():
        if sha(trajectory/filename)!=expected:raise RuntimeError('trajectory hash mismatch: '+filename)
    t,original=load_wave(native/'original/out.pewave.npz')
    tt,replay=load_wave(native/'replay/out.pewave.npz')
    equality={'time':{'bytes_equal':t.dtype==tt.dtype and t.tobytes()==tt.tobytes(),'max_abs':float(np.max(np.abs(t-tt)))}}
    if original.keys()!=replay.keys():raise RuntimeError('channel set differs')
    for name in original:
        x,y=original[name],replay[name]
        equality[name]={'bytes_equal':x.dtype==y.dtype and x.shape==y.shape and x.tobytes()==y.tobytes(),
                        'different_samples':int(np.count_nonzero(x!=y)),
                        'max_abs':float(np.max(np.abs(x.astype(float)-y.astype(float))))}
    # Run the unmodified acceptance script against separate comparison copies.
    script_results={}
    for name in ('original','replay'):
        alias=a.out/name/'pulse';alias.mkdir(parents=True)
        for filename in ('out.pewave.npz','simulation_report.json'):
            shutil.copyfile(native/name/filename,alias/filename)
        result=subprocess.run([sys.executable,str(root/'scripts/compare_c002.py'),
            '--case-set',str(a.case_set),'--run',str(alias.parent),
            '--out',str(a.out/(name+'-fixed-reference.json'))],capture_output=True,text=True,encoding='utf-8')
        (a.out/(name+'-comparison-stdout.txt')).write_text(result.stdout,encoding='utf-8')
        if result.stderr:raise RuntimeError(result.stderr)
        script_results[name]={'returncode':result.returncode,
            'result':json.loads((a.out/(name+'-fixed-reference.json')).read_text(encoding='utf-8'))}
    reference=np.concatenate([np.atleast_1d(np.genfromtxt(case/e['file'],delimiter=',',names=True)) for e in provenance['csv_exports']])
    rt=reference['time_s']
    mat=loadmat(a.benchmark.resolve()/'plecs.mat');mt=mat['Time'].ravel();mv=mat['Values']
    channels=provenance['channels']
    if mv.shape==(len(channels),len(mt)):mv=mv.T
    if mv.shape!=(len(mt),len(channels)) or mt[-1]!=.3 or not np.all(np.diff(mt)>0):raise RuntimeError('invalid PLECS capture')
    fresh={c['pulse']:mv[:,i] for i,c in enumerate(channels)}
    reference_match={'time_equal':bool(np.array_equal(rt,mt)),
        'channels':{n:bool(np.array_equal(reference[n],fresh[n])) for n in fresh}}
    events=[json.loads(line) for line in (trajectory/'event_log.jsonl').read_text(encoding='utf-8').splitlines() if line]
    et=np.unique([e['time_seconds_display'] for e in events if 'time_seconds_display' in e])
    positions=np.searchsorted(et,mt)
    distance=np.minimum(np.abs(mt-et[np.minimum(positions,len(et)-1)]),
                        np.abs(mt-et[np.maximum(positions-1,0)]))
    # Supplemental diagnosis only: do not use this mask for acceptance.
    away=distance>provenance['csv_grid_seconds']+1e-12
    fresh_comparison=compare_reference(tt,replay,mt,fresh,channels,away)
    reports={n:json.loads((native/n/'simulation_report.json').read_text(encoding='utf-8')) for n in ('original','trajectory','replay')}
    state_fields=['status','simulated_seconds','transactions','T_atom','internal_state','physical_state_view',
                  'software_states','software_final_outputs','root_queries','root_failures','rollbacks','matrix_exponentials']
    state_difference=[k for k in state_fields if reports['original'].get(k)!=reports['trajectory'].get(k)]
    hashes={n:sha(native/n/'event_log.jsonl') for n in ('original','trajectory','replay')}
    unchanged=all(sha(pathlib.Path(path))==digest for path,digest in before.items())
    summary={'samples':len(tt),'channels':list(replay),'baseline_equivalence':equality,
        'changed_solver_fields':state_difference,'event_sha256':hashes,
        'fixed_reference':script_results,'fresh_plecs_comparison':fresh_comparison,
        'fresh_vs_fixed_reference':reference_match,
        'edge_diagnostic':{'rule':'distance > one original 1 us reference interval + 1 ps; diagnostic only, never an acceptance mask',
                           'samples_all':len(mt),'samples_away':int(np.count_nonzero(away))},
        'inputs_and_references_unchanged':unchanged,'source_files_sha256':before,
        'no_accuracy_regression':all(v['bytes_equal'] for v in equality.values()) and not state_difference and len(set(hashes.values()))==1 and unchanged,
        'plecs_all_statistics_passed':fresh_comparison['passed'] and script_results['replay']['result']['passed']}
    summary['overall_accuracy_passed']=summary['no_accuracy_regression'] and summary['plecs_all_statistics_passed']
    (a.out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'no_accuracy_regression':summary['no_accuracy_regression'],
        'overall_accuracy_passed':summary['overall_accuracy_passed'],
        'fixed_statistics_passed':script_results['replay']['result']['statistics_passed'],
        'fresh_statistics_passed':fresh_comparison['statistics_passed'],
        'failed_statistics':[c for c in fresh_comparison['checks'] if not c['passed']],
        'reference_match':reference_match,'waveform_errors':fresh_comparison['waveform_errors'],
        'edge_diagnostic':summary['edge_diagnostic']},ensure_ascii=False,indent=2))
    return 0 if summary['overall_accuracy_passed'] else 1


if __name__=='__main__':raise SystemExit(main())
