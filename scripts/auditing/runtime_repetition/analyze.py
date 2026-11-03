#!/usr/bin/env python3
"""Export count/byte-only CSV and JSON; no CPU/time estimates."""
import argparse,csv,hashlib,json,subprocess,struct
from pathlib import Path

def fp(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return {'path':str(p),'bytes':p.stat().st_size,'sha256':h.hexdigest()}
def group(path):
 p=path.split('/')
 if 'bind' in p:return 'Mode_Binding'
 if any(x.startswith('pevt_') for x in p):return 'PEVT'
 if any(x.startswith(('flow_','basis_','taylor_')) for x in p):return 'Flow'
 if 'cow_binding_detach' in p:return 'COW_binding_outside_bind'
 if 'mode_compile' in p:return 'Mode_other'
 if 'original_check' in p:return 'Original_checks_other'
 if 'simulate' in p:return 'Runtime_other'
 if 'cli' in p:return 'CLI_compile_write_cleanup'
 return 'Outside_scopes'
def ratio(c,d):return None if c==0 else 100*(c-d)/c
def csvfile(out,name,header,rows):
 with (out/name).open('w',newline='') as f:w=csv.writer(f);w.writerow(header);w.writerows(rows)
def metadata(p):
 with p.open('rb') as f:
  _,_,n,_=struct.unpack('<8sHHI',f.read(16))
  for _ in range(n):
   kind,codec,size,raw,records,h=struct.unpack('<IIQQQ32s',f.read(64))
   b=f.read(size)
   if kind==1:return json.loads(b)
def main():
 p=argparse.ArgumentParser();p.add_argument('--work',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--pins',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 runs=json.loads((a.work/'RUNS.json').read_text());pins=json.loads(a.pins.read_text())
 counts={v:json.loads((a.work/v/'50ms-count/counts.json').read_text()) for v in ['C','D']}
 primary={v:json.loads((a.work/v/'50ms-allocation-only/counts.json').read_text()) for v in ['C','D']}
 tx={v:runs['runs'][v+'-count']['transactions'] for v in counts}
 assert tx['C']==tx['D']
 alloc={};groups={};eigen={};archive={}
 for v,j in counts.items():
  assert j['threads']==1 and j['overflow_errors']==0
  base=json.loads((a.work/v/'base-source-hashes.json').read_text())
  assert all(base.get(k)==h for k,h in pins[v]['files'].items())
  alloc[v]={k:{'calls':0,'bytes':0,'failures':0} for k in ['malloc','calloc','realloc']};alloc[v].update(free=0,free_null=0)
  groups[v]={};eigen[v]={}
  for row in j['paths']:
   g=group(row['path']);q=groups[v].setdefault(g,{'calls':0,'bytes':0,'frees':0,'std_hash_calls':0,'std_hash_bytes':0})
   for api in row['apis']:
    for k in ['calls','bytes','failures']:alloc[v][api['name']][k]+=api[k]
    q['calls']+=api['calls'];q['bytes']+=api['bytes']
   alloc[v]['free']+=row['free_calls'];alloc[v]['free_null']+=row['free_null'];q['frees']+=row['free_calls'];q['std_hash_calls']+=row['std_hash_calls'];q['std_hash_bytes']+=row['std_hash_bytes']
   if '/eigen_allocate' in row['path'] or '/eigen_reallocate' in row['path']:
    z=eigen[v].setdefault(g,{'requests':0,'bytes':0})
    z['requests']+=sum(x['calls'] for x in row['apis']);z['bytes']+=sum(x['bytes'] for x in row['apis'])
  total=sum(alloc[v][k]['calls'] for k in ['malloc','calloc','realloc'])
  assert sum(x['calls'] for x in j['exact_sizes'])==total
  assert sum(x['bytes'] for x in j['exact_sizes'])==sum(alloc[v][k]['bytes'] for k in ['malloc','calloc','realloc'])
  archive[v]=metadata(a.work/v/'50ms-count/out.pevt')['provenance']['archive_counts']
  assert archive[v]['equation_calls']==j['metrics']['pevt_equation']
  assert archive[v]['definition_candidate_checks']==j['metrics']['pevt_definition_compare']
  report=json.loads((a.work/v/'50ms-count/simulation_report.json').read_text())
  assert report['flow_statistics']['constructions']==j['metrics']['flow_construct']
  assert report['original_equation_cache']['checks']==j['metrics']['original_check']
  assert report['flow_statistics']['basis_hits']==j['metrics']['basis_reuse']
 # all exact counters, including zero-valued operations, with per-transaction normalization
 rows=[]
 for k in sorted(set(counts['C']['metrics'])|set(counts['D']['metrics'])):
  if k in counts['C']['keys'] or k in counts['D']['keys']:continue
  c=counts['C']['metrics'].get(k,0);d=counts['D']['metrics'].get(k,0)
  rows.append([k,c,d,c/tx['C'],d/tx['D'],c-d,ratio(c,d)])
 csvfile(a.out,'COUNTS.csv',['metric','C','D','C_per_transaction','D_per_transaction','removed','reduction_percent'],rows)
 instrumented_alloc=json.loads(json.dumps(alloc))
 for v,j in primary.items():
  assert j['threads']==1 and j['overflow_errors']==0
  alloc[v]={k:{'calls':0,'bytes':0,'failures':0} for k in ['malloc','calloc','realloc']};alloc[v].update(free=0,free_null=0)
  for row in j['paths']:
   for api in row['apis']:
    for k in ['calls','bytes','failures']:alloc[v][api['name']][k]+=api[k]
   alloc[v]['free']+=row['free_calls'];alloc[v]['free_null']+=row['free_null']
 rows=[]
 for k in sorted(set(counts['C']['keys'])|set(counts['D']['keys'])):
  for v in counts:
   q=counts[v]['keys'].get(k)
   if q:rows.append([v,k,q['requests'],q['distinct'],q['repeats'],q['repeats']/q['requests'],q['repeats']/tx[v],q['bytes_examined']])
 csvfile(a.out,'EXACT_REPEATS.csv',['version','input_operation','requests','distinct_full_inputs','exact_repeated_inputs','repeat_fraction','repeats_per_transaction','input_bytes_compared'],rows)
 rows=[]
 for api in ['malloc','calloc','realloc']:
  for metric in ['calls','bytes','failures']:
   c=alloc['C'][api][metric];d=alloc['D'][api][metric];rows.append([api,metric,c,d,c/tx['C'],d/tx['D'],ratio(c,d)])
 for key in ['free','free_null']:
  c=alloc['C'][key];d=alloc['D'][key];rows.append([key,'calls',c,d,c/tx['C'],d/tx['D'],ratio(c,d)])
 csvfile(a.out,'ALLOCATIONS.csv',['API','metric','C','D','C_per_transaction','D_per_transaction','reduction_percent'],rows)
 csvfile(a.out,'ALLOC_PATHS.csv',['version','logical_call_path','entries','malloc_calls','calloc_calls','realloc_calls','requested_bytes','free_calls','free_null','std_hash_calls','std_hash_bytes'],[
  [v,r['path'],r['entries'],*[q['calls'] for q in r['apis']],sum(q['bytes'] for q in r['apis']),r['free_calls'],r['free_null'],r['std_hash_calls'],r['std_hash_bytes']] for v,j in counts.items() for r in j['paths']])
 csvfile(a.out,'ALLOCATION_EXACT_SIZES.csv',['version','requested_size','calls','requested_bytes'],[[v,r['size'],r['calls'],r['bytes']] for v,j in primary.items() for r in sorted(j['exact_sizes'],key=lambda q:q['size'])])
 csvfile(a.out,'ALLOCATION_RECONCILIATION.csv',['version','metric','unchanged_Release','source_count_build','difference'],[
  [v,k,sum(alloc[v][api][k] for api in ['malloc','calloc','realloc']),sum(instrumented_alloc[v][api][k] for api in ['malloc','calloc','realloc']),sum(instrumented_alloc[v][api][k]-alloc[v][api][k] for api in ['malloc','calloc','realloc'])] for v in counts for k in ['calls','bytes']])
 csvfile(a.out,'ALLOCATION_PATH_SIZE_BINS.csv',['version','path','minimum_size','maximum_size','calls','requested_bytes'],[[v,r['path'],0 if b['bin']==0 else 1<<(b['bin']-1),0 if b['bin']==0 else (1<<b['bin'])-1,b['calls'],b['bytes']] for v,j in counts.items() for r in j['paths'] for b in r['sizes']])
 csvfile(a.out,'ALLOCATION_GROUPS.csv',['group','C_calls','D_calls','C_bytes','D_bytes','calls_reduction_percent','bytes_reduction_percent'],[
  [g,groups['C'].get(g,{}).get('calls',0),groups['D'].get(g,{}).get('calls',0),groups['C'].get(g,{}).get('bytes',0),groups['D'].get(g,{}).get('bytes',0),ratio(groups['C'].get(g,{}).get('calls',0),groups['D'].get(g,{}).get('calls',0)),ratio(groups['C'].get(g,{}).get('bytes',0),groups['D'].get(g,{}).get('bytes',0))] for g in sorted(set(groups['C'])|set(groups['D']))])
 csvfile(a.out,'EIGEN_ALLOCATIONS.csv',['version','group','actual_allocation_API_calls','requested_bytes','per_transaction'],[[v,g,q['requests'],q['bytes'],q['requests']/tx[v]] for v in counts for g,q in eigen[v].items()])
 reuse=[]
 for v,j in counts.items():
  m=j['metrics'];r=json.loads((a.work/v/'50ms-count/simulation_report.json').read_text());ac=archive[v]
  cases={'mode_template':(r['mode_cache_hits'],r['mode_cache_misses']),
   'basis':(m['basis_reuse'],m['basis_build']),
   'observe_row_projection_cache':(m['flow_observe']-m['flow_observe_guard_hit']-m['flow_observe_guard_negative_hit']-m['flow_observe_projection_miss'],m['flow_observe_projection_miss']),
   'taylor_projection_ready':(m['taylor_ready_hit'],m['taylor_projection_build']),
   'taylor_shared_anchor_state':(m['taylor_projection_build']-m['taylor_recurrence_build'],m['taylor_recurrence_build']),
   'PEVT_definition':(ac['definition_hits'],ac['definition_encodes']),
   'PEVT_values':(m['pevt_value_set']-m['pevt_value_new'],m['pevt_value_new']),
   'PEVT_states':(m['pevt_state']-m['pevt_state_new'],m['pevt_state_new']),
   'PEVT_instances':(m['pevt_instance']-m['pevt_instance_new'],m['pevt_instance_new'])}
  if 'stage_d_rebound_cache' in r:
   q=r['stage_d_rebound_cache'];cases['bound_mode']=(q['hits'],q['misses'])
  for k,(hit,miss) in cases.items():assert hit>=0;reuse.append([v,k,hit,miss,hit/(hit+miss) if hit+miss else None])
 csvfile(a.out,'REUSE.csv',['version','cache_or_dedup','hits','misses','reuse_fraction'],reuse)
 evidence={'scope':'A010 full 50ms; exact counts/bytes only, no time or CPU profiling','pins':pins,'runs':runs,'transactions':tx,'allocations':alloc,'allocation_source':'unchanged accepted Release ELF with allocation-only interposition','source_instrumented_allocations':instrumented_alloc,'allocation_groups':groups,'eigen_allocations':eigen,'archive_counters':archive,'counts':counts,'allocation_only_counts':primary,'raw_artifacts':{}}
 for pth in sorted(a.work.rglob('*')):
  if pth.is_file() and 'build' not in pth.relative_to(a.work).parts and 'source' not in pth.relative_to(a.work).parts:
   evidence['raw_artifacts'][pth.relative_to(a.work).as_posix()]=fp(pth)
 evidence['environment']={}
 evidence['compile_commands']={v:json.loads((a.work/v/'build/compile_commands.json').read_text()) for v in counts}
 evidence['allocation_only_comparisons']={v:json.loads((a.work/v/'allocation-only-comparison.json').read_text()) for v in counts}
 assert all(x['status']=='PASS_SCOPED_COMPARISON' for x in evidence['allocation_only_comparisons'].values())
 evidence['input_files']={p.relative_to(a.work.parent).as_posix() if p.is_relative_to(a.work.parent) else str(p):fp(p) for p in Path('/root/stage-a-regression-20261103/model').rglob('*') if p.is_file()}
 for cmd in [['uname','-a'],['gcc','--version'],['cmake','--version']]:
  q=subprocess.run(cmd,capture_output=True,text=True);evidence['environment'][' '.join(cmd)]=q.stdout
 (a.out/'EVIDENCE.json').write_text(json.dumps(evidence,indent=2)+'\n')
 for v in counts:(a.out/('COUNTS_'+v+'.json')).write_text(json.dumps(counts[v],indent=2)+'\n')
 print(json.dumps({'transactions':tx,'allocations':alloc,'groups':groups,'keys':{v:counts[v]['keys'] for v in counts},'counts':{v:counts[v]['metrics'] for v in counts},'reuse':reuse,'archive':archive},indent=2))
if __name__=='__main__':main()
