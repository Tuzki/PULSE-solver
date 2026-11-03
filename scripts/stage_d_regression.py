#!/usr/bin/env python3
"""One full Linux Stage-D A010 run, strict Stage-C payload regression and rollback.

Wave reconstruction and profiler runs are deliberately outside this benchmark.
Requires preserved Stage-C native evidence on the same machine.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from remaining_b_regression import fingerprint, run


def rollback(source, build, model, baseline, out):
    out.mkdir(parents=True,exist_ok=False)
    command=['c++','-std=c++20','-O3','-DNDEBUG','-ffp-contract=off','-fno-fast-math',
             '-DEIGEN_MPL2_ONLY','-DEIGEN_DONT_PARALLELIZE','-I'+str(source/'include'),
             '-isystem',str(source/'third_party'),'-isystem',str(source/'third_party/eigen-3.4.0'),
             str(source/'tests/rollback_snapshot_probe.cpp'),str(build/'libpulse_core.a'),
             '-lcrypto','-ldl','-o',str(out/'probe')]
    with (out/'build.log').open('w') as log:
        subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    with (out/'snapshot.json').open('w') as log,(out/'stderr.txt').open('w') as err:
        subprocess.run([str(out/'probe'),str(model)],stdout=log,stderr=err,check=True)
    a=json.loads(baseline.read_text());b=json.loads((out/'snapshot.json').read_text())
    result={'baseline':fingerprint(baseline),'candidate':fingerprint(out/'snapshot.json'),
            'command':command,'all_equal':a==b,'points':{k:a[k]==b.get(k) for k in a}}
    (out/'comparison.json').write_text(json.dumps(result,indent=2)+'\n')
    if a!=b:raise RuntimeError('Stage D rollback snapshot differs from accepted Stage C')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--model',type=Path,required=True)
    p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--rollback-reference',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--wall-limit',type=float,default=132.8290989997913)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    build=a.source/'build-linux'
    evidence={'baseline_commit':'fa2bc5ee4aab588ee91fb5b0513c692493799f7e',
              'repetitions':1,'baseline_reused':True,
              'baseline_measurement':json.loads((a.reference/'measurement.json').read_text()),
              'baseline_archive':fingerprint(a.reference/'out.pevt'),
              'binary':fingerprint(build/'pulse-solver'),'netlist':fingerprint(a.model),
              'timing':'command start through archive write and COMPLETED; replay excluded'}
    if evidence['baseline_archive']['sha256']!='4430815d2bf95a1d9a6f86535b5de1371d0c54fd86d34ed086c810c959dc22cf':
        raise RuntimeError('Wrong accepted Stage C archive')
    def save():(a.out/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    save()
    evidence['rollback']=rollback(a.source,build,a.model,a.rollback_reference,a.out/'rollback')
    save()
    evidence['measurement']=run(build/'pulse-solver',a.model,.5,a.out/'500ms-stage-d',a.wall_limit)
    save()
    candidate=a.out/'500ms-stage-d'
    command=[sys.executable,str(a.source/'scripts/stage_c_verify.py'),
             '--baseline',str(a.reference/'out.pevt'),'--candidate',str(candidate/'out.pevt'),
             '--baseline-report',str(a.reference/'simulation_report.json'),
             '--candidate-report',str(candidate/'simulation_report.json'),
             '--out',str(a.out/'strict-comparison.json')]
    with (a.out/'comparison-stdout.json').open('w') as log:
        comparison=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
    evidence['comparison_command']=command
    evidence['comparison']=json.loads((a.out/'strict-comparison.json').read_text())
    evidence['report']=json.loads((candidate/'simulation_report.json').read_text())
    evidence['candidate_archive']=fingerprint(candidate/'out.pevt')
    b,d=evidence['baseline_measurement'],evidence['measurement']
    evidence['wall_reduction_percent']=100*(1-d['completion_wall_seconds']/b['completion_wall_seconds'])
    evidence['speedup']=b['completion_wall_seconds']/d['completion_wall_seconds']
    save()
    print(json.dumps({'measurement':d,'strict_status':evidence['comparison']['status'],
                      'wall_reduction_percent':evidence['wall_reduction_percent']},indent=2))
    return comparison.returncode


if __name__=='__main__':sys.exit(main())
