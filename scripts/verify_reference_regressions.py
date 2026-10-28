from pathlib import Path
import hashlib
import json
import sys
sys.path.insert(0,r'D:\codex\tool\pulse-win\python')
import numpy as np
root=Path(r'D:\codex\pulse-solver-v1.15win')
out=root/'reports/island_reference_fix_20261027'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def wave_compare(a,b):
    with np.load(next(a.glob('*.npz')),allow_pickle=False) as za, np.load(next(b.glob('*.npz')),allow_pickle=False) as zb:
        ma=json.loads(str(za['metadata_json']));mb=json.loads(str(zb['metadata_json']))
        sa={x['name']:x['id'] for x in ma['signals']};sb={x['name']:x['id'] for x in mb['signals']}
        common=sorted(sa.keys()&sb.keys())
        result={'same_channels':sa.keys()==sb.keys(),'time_bitwise_equal':np.array_equal(za['time'],zb['time']),
                'samples':len(za['time']),'channels':len(sa),'signals':{}}
        for name in common:
            aa,bb=za[sa[name]],zb[sb[name]]
            result['signals'][name]={'bitwise_equal':aa.dtype==bb.dtype and aa.shape==bb.shape and aa.tobytes()==bb.tobytes(),
                'max_abs_difference':float(np.max(np.abs(aa.astype(float)-bb.astype(float)))) if aa.shape==bb.shape and aa.size else 0.0}
        result['event_log_bitwise_equal']=sha(a/'event_log.jsonl')==sha(b/'event_log.jsonl')
        result['passed']=result['same_channels'] and result['time_bitwise_equal'] and all(x['bitwise_equal'] for x in result['signals'].values()) and result['event_log_bitwise_equal']
        return result

mode=sys.argv[1]
if mode=='native':
    old=root/'reports/windows_native_validation';new=out/'native_validation'
    before=json.loads((old/'all_ledger.json').read_text(encoding='utf-8'))
    after=json.loads((new/'all_ledger.json').read_text(encoding='utf-8'))
    indexed={x['case']:x for x in before['cases']};result={}
    for entry in after['cases']:
        name=entry['case'];prev=indexed[name]
        row=wave_compare(old/name,new/name)
        row.update(same_status=prev['status']==entry['status'],same_effective_end=prev['simulated_seconds']==entry['simulated_seconds'],status=entry['status'])
        row['passed']=row['passed'] and row['same_status'] and row['same_effective_end']
        result[name]=row
else:
    result={}
    for name in ['rohm-c006-d-buck-v001','rohm-c002-d-boost-v002']:
        result[name]=wave_compare(root/'reports/windows_compare_20261027_final'/name/'pulse',out/'buck_boost_live'/name/'pulse')
summary={'all_passed':all(x['passed'] for x in result.values()),'cases':result}
(out/(mode+'_bitwise_regression.json')).write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps({'all_passed':summary['all_passed'],'cases':{k:{key:value for key,value in v.items() if key!='signals'} for k,v in result.items()}},indent=2))
if not summary['all_passed']:raise SystemExit(1)
