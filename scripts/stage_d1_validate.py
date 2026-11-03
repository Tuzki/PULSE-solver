#!/usr/bin/env python3
"""D versus D1: full 50ms strict regression and count-only resource audit."""
import argparse,json,os,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'auditing/runtime_repetition'))
from run import fp,execute,verify
from stage_d_regression import rollback

def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
 p.add_argument('--source',type=Path,default=Path('/root/pulse-stage-d1-20261104'))
 p.add_argument('--model',type=Path,default=Path('/root/stage-a-regression-20261103/model/netlist.md'))
 a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
 baseline=Path('/root/pulse-stage-d-20261104/build-linux/pulse-solver')
 counter=Path('/root/stage-d1-count-20261104/D1')
 saved=Path('/root/cd-repeat-audit-20261104/D')
 env=os.environ.copy()
 for k in ['LD_PRELOAD','PULSE_PROFILE_PHASES','PULSE_ALLOC_REPORT','PULSE_WALL_SECONDS']:env.pop(k,None)
 evidence={'scope':'D1 full 50ms correctness and exact counts; no timing or CPU profiling',
  'model':fp(a.model),'runs':{},'comparisons':{},'rollback':rollback(a.source,a.source/'build-linux',a.model,Path('/root/stage-d-regression-20261104/benchmark/rollback/snapshot.json'),a.out/'rollback')}
 def save():(a.out/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
 save()
 specs=[('D-clean',baseline,None),
        ('D1-clean',a.source/'build-linux/pulse-solver',None),
        ('D-allocation',baseline,counter/'libcounts.so'),
        ('D1-allocation',a.source/'build-linux/pulse-solver',counter/'libcounts.so'),
        ('D-count',saved/'build/pulse-solver',saved/'libcounts.so'),
        ('D1-count',counter/'build/pulse-solver',counter/'libcounts.so')]
 for label,binary,library in specs:
  out=a.out/label;runenv=env.copy()
  if library:runenv.update(LD_PRELOAD=str(library),PULSE_COUNT_OUTPUT=str(out/'counts.json'))
  cmd=[str(binary),str(a.model),'--t-end','.05','--output-format','trajectory','--out',str(out)]
  print(label,flush=True);execute(cmd,out,runenv)
  report=json.loads((out/'simulation_report.json').read_text())
  assert report['status']=='COMPLETED' and report['simulated_seconds']==.05
  assert len(report['analog_channels'])==13 and len(report['digital_channels'])==4
  evidence['runs'][label]={'command':cmd,'binary':fp(binary),'archive':fp(out/'out.pevt'),
    'transactions':report['transactions'],'mode_compilations':report['mode_compilations'],
    'original_checks':report['original_equation_cache'],'flow_statistics':report['flow_statistics'],
    'source_sha256':report['source_sha256'],'counter_library':fp(library) if library else None}
  if library:
   counts=json.loads((out/'counts.json').read_text())
   assert counts['threads']==1 and counts['overflow_errors']==0
  ref=a.out/('D-clean' if label=='D-clean' or label.startswith('D-') else 'D1-clean')
  if label!='D-clean':
   if label=='D1-clean':ref=a.out/'D-clean'
   evidence['comparisons'][label]=verify(a.source/'scripts/stage_c_verify.py',ref,out,a.out/(label+'-comparison.json'))
  save()
 print('All complete 50ms cases, rollback and strict PEVT comparisons passed.',flush=True)
 return 0
if __name__=='__main__':sys.exit(main())
