#!/usr/bin/env python3
"""Exact-count C/D full 50ms audit. Deliberately contains no timing/profiling."""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path

def fp(p):
 p=Path(p);h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return {'path':str(p),'bytes':p.stat().st_size,'sha256':h.hexdigest()}

def execute(command,out,env=None):
 out.mkdir(parents=True,exist_ok=False)
 with (out/'stdout.txt').open('w') as f,(out/'stderr.txt').open('w') as e:
  p=subprocess.run(command,env=env,stdout=f,stderr=e)
 if p.returncode:raise RuntimeError((command,p.returncode,(out/'stderr.txt').read_text()[-2000:]))
 return p.returncode

def verify(tool,a,b,out):
 cmd=[sys.executable,str(tool),'--baseline',str(a/'out.pevt'),'--candidate',str(b/'out.pevt'),
      '--baseline-report',str(a/'simulation_report.json'),'--candidate-report',str(b/'simulation_report.json'),'--out',str(out)]
 p=subprocess.run(cmd,capture_output=True,text=True)
 if p.returncode:raise RuntimeError(p.stdout+p.stderr)
 return json.loads(out.read_text())

def main():
 p=argparse.ArgumentParser();p.add_argument('--work',type=Path,required=True);p.add_argument('--model',type=Path,required=True);a=p.parse_args()
 env=os.environ.copy()
 for k in ['PULSE_PROFILE_PHASES','LD_PRELOAD','PULSE_ALLOC_REPORT','PULSE_WALL_SECONDS']:env.pop(k,None)
 evidence={'simulated_seconds':.05,'measurement':'counts only; no clocks, CPU or sampling','model':fp(a.model),'runs':{},'comparisons':{}}
 for v in ['C','D']:
  root=a.work/v
  baseline=Path('/root/pulse-stage-'+v.lower()+'-2026110'+('3' if v=='C' else '4'))
  # Rebuild the observer only; its ABI and instrumented header are unchanged.
  command=['g++','-std=c++20','-O2','-fPIC','-shared',str(Path(__file__).parent/'counters.cpp'),'-I'+str(root),'-I'+str(root/'source/third_party'),'-ldl','-o',str(root/'libcounts.so')]
  subprocess.run(command,check=True)
  for kind,binary in [('clean',baseline/'build-linux/pulse-solver'),('count',root/'build/pulse-solver')]:
   out=root/('50ms-'+kind);cmd=[str(binary),str(a.model),'--t-end','.05','--output-format','trajectory','--out',str(out)]
   if kind=='clean' and out.exists():
    print('reuse existing uninstrumented 50ms evidence',v,flush=True)
    report=json.loads((out/'simulation_report.json').read_text())
    evidence['runs'][v+'-clean']={'command':cmd,'binary':fp(binary),'archive':fp(out/'out.pevt'),'transactions':report['transactions'],'mode_compilations':report['mode_compilations'],'original_equation_cache':report['original_equation_cache'],'mode_cache_hits':report['mode_cache_hits'],'source_sha256':report['source_sha256'],'reused':True}
    continue
   runenv=env.copy()
   if kind=='count':runenv.update(LD_PRELOAD=str(root/'libcounts.so'),PULSE_COUNT_OUTPUT=str(out/'counts.json'))
   print('running',v,kind,flush=True);execute(cmd,out,runenv)
   report=json.loads((out/'simulation_report.json').read_text())
   assert report['status']=='COMPLETED' and report['simulated_seconds']==.05
   assert len(report['analog_channels'])==13 and len(report['digital_channels'])==4
   evidence['runs'][v+'-'+kind]={'command':cmd,'binary':fp(binary),'archive':fp(out/'out.pevt'),
    'transactions':report['transactions'],'mode_compilations':report['mode_compilations'],'original_equation_cache':report['original_equation_cache'],'mode_cache_hits':report['mode_cache_hits'],'source_sha256':report['source_sha256']}
   if kind=='count':
    counts=json.loads((out/'counts.json').read_text());assert counts['threads']==1 and counts['overflow_errors']==0
  tool=baseline/'scripts/stage_c_verify.py'
  evidence['comparisons'][v+'-instrumentation']=verify(tool,root/'50ms-clean',root/'50ms-count',root/'instrumentation-comparison.json')
  (a.work/'RUNS.json').write_text(json.dumps(evidence,indent=2)+'\n')
 evidence['comparisons']['C-D-clean']=verify(tool,a.work/'C/50ms-clean',a.work/'D/50ms-clean',a.work/'CD-clean-comparison.json')
 evidence['comparisons']['C-D-count']=verify(tool,a.work/'C/50ms-count',a.work/'D/50ms-count',a.work/'CD-count-comparison.json')
 (a.work/'RUNS.json').write_text(json.dumps(evidence,indent=2)+'\n')
 print('All full-50ms simulation and strict payload checks passed.',flush=True)
if __name__=='__main__':main()
