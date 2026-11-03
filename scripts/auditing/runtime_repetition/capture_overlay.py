#!/usr/bin/env python3
"""Save reviewable final instrumentation diffs and final counter calibration."""
from pathlib import Path
import argparse,difflib,json,os,subprocess
p=argparse.ArgumentParser();p.add_argument('--work',type=Path,required=True);a=p.parse_args()
for v in ['C','D']:
 r=a.work/v;base=Path('/root/pulse-stage-'+v.lower()+'-2026110'+('3' if v=='C' else '4'));diff=[]
 names=['CMakeLists.txt']+[p.relative_to(r/'source').as_posix() for folder in ['include','src','apps'] for p in (r/'source'/folder).rglob('*') if p.is_file()]
 names+=['third_party/eigen-3.4.0/Eigen/src/Core/util/Memory.h']
 for name in sorted(names):
  before=(base/name).read_text();after=(r/'source'/name).read_text()
  if before!=after:diff.extend(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='pinned/'+name,tofile='count-only/'+name))
 (r/'overlay-final.diff').write_text(''.join(diff))
 env=os.environ.copy();env.update(LD_PRELOAD=str(r/'libcounts.so'),PULSE_COUNT_OUTPUT=str(r/'self-test-final.json'))
 subprocess.run([str(r/'self-test')],env=env,check=True)
 j=json.loads((r/'self-test-final.json').read_text());row=next(q for q in j['paths'] if q['path']=='outside_scopes/cli')
 assert [q['calls'] for q in row['apis']]==[1,1,1] and [q['bytes'] for q in row['apis']]==[17,21,33]
 assert row['free_calls']==3 and row['free_null']==1
 assert j['keys']['bind_input_A']['distinct']==2 and j['keys']['bind_input_A']['repeats']==1
 print(v,'final calibration and source diff captured')
