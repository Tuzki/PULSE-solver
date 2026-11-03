#!/usr/bin/env python3
"""One Linux Stage C run against pinned B+COW evidence; replay is separate."""
import argparse
import json
from pathlib import Path

from remaining_b_regression import fingerprint, run, compare


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('baseline','candidate','netlist','reference-dir','baseline-evidence','out'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--wall-limit',type=float,default=132.8290989997913)
    a=p.parse_args()
    saved=json.loads(a.baseline_evidence.read_text(encoding='utf-8'))
    old_binary=fingerprint(a.baseline)
    old_archive=fingerprint(a.reference_dir/'out.pevt')
    assert old_binary['sha256']==saved['environment']['binaries']['cow']['sha256'],'Wrong B+COW binary'
    assert old_archive['sha256']==saved['performance']['full_comparison']['whole_files'][1]['sha256'],'Wrong B+COW archive'
    old_measurement=json.loads((a.reference_dir/'measurement.json').read_text())
    assert old_measurement==saved['performance']['full_new'],'Baseline measurement changed'
    a.out.mkdir(parents=True,exist_ok=False)
    result={'baseline_binary':old_binary,'candidate_binary':fingerprint(a.candidate),
            'netlist':fingerprint(a.netlist),'baseline_archive':old_archive,
            'baseline_measurement':old_measurement,'baseline_reused':True,'full_repetitions':1,
            'wall_limit_seconds':a.wall_limit,'baseline_evidence':fingerprint(a.baseline_evidence)}
    def save():
        (a.out/'evidence.json').write_text(json.dumps(result,indent=2)+'\n')
    save()
    result['prefix_baseline']=run(a.baseline,a.netlist,.005,a.out/'5ms-baseline',a.wall_limit)
    result['prefix_stage_c']=run(a.candidate,a.netlist,.005,a.out/'5ms-stage-c',a.wall_limit)
    result['prefix_comparison']=compare(a.out/'5ms-baseline',a.out/'5ms-stage-c')
    save()
    result['stage_c_measurement']=run(a.candidate,a.netlist,.5,a.out/'500ms-stage-c',a.wall_limit)
    result['full_comparison']=compare(a.reference_dir,a.out/'500ms-stage-c')
    b,c=old_measurement,result['stage_c_measurement']
    result['wall_reduction_percent']=100*(b['completion_wall_seconds']-c['completion_wall_seconds'])/b['completion_wall_seconds']
    result['cpu_reduction_percent']=100*(b['cpu_seconds']-c['cpu_seconds'])/b['cpu_seconds']
    result['rss_reduction_percent']=100*(b['peak_rss_kib']-c['peak_rss_kib'])/b['peak_rss_kib']
    save()
    print(json.dumps({k:result[k] for k in ('wall_reduction_percent','cpu_reduction_percent','rss_reduction_percent')},indent=2))


if __name__=='__main__':
    main()
