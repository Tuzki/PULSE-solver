#!/usr/bin/env python3
"""Allocation-only interposition on unchanged accepted Release binaries."""
import argparse,json,os
from pathlib import Path
from run import execute,verify
p=argparse.ArgumentParser();p.add_argument('--work',type=Path,required=True);p.add_argument('--model',type=Path,required=True);a=p.parse_args()
for v in ['C','D']:
 root=a.work/v;baseline=Path('/root/pulse-stage-'+v.lower()+'-2026110'+('3' if v=='C' else '4'))
 out=root/'50ms-allocation-only'
 env=os.environ.copy()
 for k in ['PULSE_PROFILE_PHASES','PULSE_ALLOC_REPORT','PULSE_WALL_SECONDS']:env.pop(k,None)
 env.update(LD_PRELOAD=str(root/'libcounts.so'),PULSE_COUNT_OUTPUT=str(out/'counts.json'))
 cmd=[str(baseline/'build-linux/pulse-solver'),str(a.model),'--t-end','.05','--output-format','trajectory','--out',str(out)]
 print(v,'unchanged Release allocation count',flush=True);execute(cmd,out,env)
 verify(baseline/'scripts/stage_c_verify.py',root/'50ms-clean',out,root/'allocation-only-comparison.json')
 (root/'allocation-only-command.json').write_text(json.dumps(cmd,indent=2)+'\n')
