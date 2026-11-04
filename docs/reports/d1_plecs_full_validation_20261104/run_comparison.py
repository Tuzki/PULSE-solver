import csv,hashlib,json,os,pathlib,resource,signal,subprocess,sys,time
import numpy as np
ROOT=pathlib.Path('/workspace/PULSE-case-set'); SOLVER=pathlib.Path('/workspace/PULSE-solver'); OUT=pathlib.Path('/workspace/pulse-d1-validation'); BUILD=pathlib.Path('/workspace/pulse-d1-build')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def limits():resource.setrlimit(resource.RLIMIT_AS,(8*1024**3,8*1024**3))
def run(cmd,dest,budget,env=None):
 dest.mkdir(parents=True,exist_ok=True);start=time.perf_counter()
 with (dest/'stdout.txt').open('w') as out,(dest/'stderr.txt').open('w') as err:
  p=subprocess.Popen(cmd,stdout=out,stderr=err,env=env,start_new_session=True,preexec_fn=limits)
  try:code=p.wait(timeout=budget);timeout=False
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait();code=p.returncode;timeout=True
 return {'command':cmd,'wall_seconds':time.perf_counter()-start,'exit_code':code,'external_timeout':timeout,'budget_seconds':budget}
def csvfile(name,rows):
 if not rows:return
 fields=list(dict.fromkeys(k for r in rows for k in r))
 with (OUT/name).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def accuracy(case,meta,wave):
 files=[case/e['file'] for e in meta['csv_exports']]
 names=files[0].open().readline().strip().split(',')
 arrays=[]
 for p,e in zip(files,meta['csv_exports']):
  if sha(p)!=e['sha256']:raise RuntimeError('PLECS checksum mismatch: '+str(p))
  arrays.append(np.loadtxt(p,delimiter=',',skiprows=1,ndmin=2))
 ref=np.concatenate(arrays);rt=ref[:,0]
 if not np.isfinite(ref).all() or len(rt)!=meta['csv_samples'] or np.any(np.diff(rt)<=0) or rt[0]!=0 or rt[-1]!=meta['original_end_seconds']:raise RuntimeError('incomplete/invalid reference')
 with np.load(wave,allow_pickle=False) as z:
  md=json.loads(str(z['metadata_json']));t=z['time'];signals={s['name']:z[s['id']].astype(float) for s in md['signals']}
 if len(t)==len(rt)+1 and abs(t[-1]-rt[-1])<1e-12 and np.max(np.abs(t[:len(rt)]-rt))<1e-12:
  signals={n:np.concatenate((v[:len(rt)-1],v[-1:])) for n,v in signals.items()};t=np.concatenate((t[:len(rt)-1],t[-1:]))
 if len(t)!=len(rt) or np.max(np.abs(t-rt))>1e-12:raise RuntimeError('replay/reference grids do not align')
 ix=np.rint(np.linspace(0,len(rt)-1,20)).astype(int);points=[];stats=[];channels=[]
 for ch in meta['channels']:
  name=ch['pulse']
  if name not in names:raise RuntimeError('reference channel absent: '+name)
  if name not in signals:channels.append({'case':meta['rohm_id'],'channel':name,'status':'MISSING_PULSE_CHANNEL'});continue
  r=ref[:,names.index(name)];a=signals[name]
  if not np.isfinite(a).all():raise RuntimeError('nonfinite replay')
  denom=float(np.mean(np.abs(r)));delta=a-r
  def pct(x):return float(abs(x)/denom*100) if denom>0 else None
  for n,i in enumerate(ix):points.append({'case':meta['rohm_id'],'channel':name,'unit':ch['unit'],'point':n+1,'time_s':float(rt[i]),'plecs':float(r[i]),'pulse':float(a[i]),'signed_delta':float(delta[i]),'abs_delta':float(abs(delta[i])),'plecs_full_mean_abs':denom,'error_pct_mean_abs':pct(delta[i])})
  for metric,func in [('mean',np.mean),('rms',lambda x:np.sqrt(np.mean(x*x))),('min',np.min),('max',np.max)]:
   expected=float(func(r));actual=float(func(a));stats.append({'case':meta['rohm_id'],'channel':name,'unit':ch['unit'],'metric':metric,'plecs':expected,'pulse':actual,'signed_delta':actual-expected,'abs_delta':abs(actual-expected),'plecs_full_mean_abs':denom,'error_pct_mean_abs':pct(actual-expected)})
  channels.append({'case':meta['rohm_id'],'channel':name,'unit':ch['unit'],'status':'COMPARED','samples':len(rt),'plecs_full_mean_abs':denom,'points20_mean_error_pct':pct(np.mean(np.abs(delta[ix]))),'points20_max_error_pct':pct(np.max(np.abs(delta[ix]))),'full_grid_rmse':float(np.sqrt(np.mean(delta**2))),'full_grid_max_abs':float(np.max(np.abs(delta)))})
  import matplotlib;matplotlib.use('Agg')
  import matplotlib.pyplot as plt
  import re
  safe=re.sub(r'[^A-Za-z0-9_.-]+','_',name); plotdir=OUT/case.name/'plots';plotdir.mkdir(parents=True,exist_ok=True)
  for label,select in [('full',np.arange(0,len(rt),max(1,len(rt)//30000))),('last_1ms',np.flatnonzero(rt>=rt[-1]-.001-1e-12))]:
   fig,ax=plt.subplots(figsize=(11,4));ax.plot(rt[select],r[select],label='PLECS',lw=.8);ax.plot(rt[select],a[select],label='PULSE D1',lw=.65,alpha=.75);ax.set(xlabel='Time (s)',ylabel=name+' ('+ch['unit']+')',title=meta['rohm_id']+' — '+name+' — '+label);ax.grid(alpha=.2);ax.legend();fig.tight_layout();fig.savefig(plotdir/(safe+'_'+label+'.png'),dpi=120);plt.close(fig)
 return channels,stats,points
manifest={'solver_branch':'fix/stage-d1-runtime-repair-20261104','solver_commit':subprocess.check_output(['git','-C',str(SOLVER),'rev-parse','HEAD'],text=True).strip(),'solver_binary_sha256':sha(BUILD/'pulse-solver'),'replay_binary_sha256':sha(BUILD/'pulse-replay'),'case_set_commit':subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),'comparison_note':'Current cloud PULSE timing versus case-set historical PLECS RPC timing; different hardware/session, not a controlled same-machine speed benchmark. PULSE wall time includes CLI startup, parsing, solving and complete archive writing; excludes C compilation and replay.','accuracy_note':'20 approximately equally spaced existing PLECS grid points including endpoints. Denominator = arithmetic mean(abs(PLECS)) across full 1us grid including endpoints; zero denominators yield null. Full-grid mean/RMS/min/max compared separately. Replay at 1us, no solver output/physics overrides except full original T_END.','archive_note':'Self-contained D1 trajectory directory bytes = out.pevt + simulation_report.json; PEVT bytes and components reported separately. Comparison size is original uncompressed PLECS waveform CSV total.','resource_note':'Serial runs; per-process address-space cap 8 GiB; generation wall budget max(120,min(600,10*historical PLECS RPC)); replay budget 600s. No duration/tolerance shortening; incomplete runs excluded from completed timing/size/accuracy ratios.','cases':[]}
assert manifest['solver_commit']=='9f49f733863b90d8356aee22595e71e72fcc2c2b'
manifest=json.loads((OUT/'evidence.json').read_text()) if (OUT/'evidence.json').exists() else manifest
manifest['resource_note']='Serial runs; 8 GiB address-space cap; generation wall timeout exactly 5*historical PLECS RPC seconds. Timeout labelled TIMEOUT_5X_PLECS, excluded from completion/accuracy ratios. Replay separate, 600s budget.'
def readcsv(name):
 p=OUT/name
 return list(csv.DictReader(p.open())) if p.exists() else []
allchannels=readcsv('CHANNEL_ACCURACY.csv');allstats=readcsv('STATISTICS.csv');allpoints=readcsv('POINTS20.csv')
ps=sorted(ROOT.glob('*/provenance.json'),key=lambda p:(p.parent.name not in ['rohm-c002-d-boost','rohm-c006-d-buck'],p.parent.name))
for prov in ps:
 meta=json.loads(prov.read_text());
 if any(r['case']==meta['rohm_id'] for r in manifest['cases']):continue
 case=prov.parent;model=case/'pulse/netlist.md';dest=OUT/case.name;dest.mkdir(exist_ok=True)
 row={'case':meta['rohm_id'],'folder':case.name,'target_seconds':meta['original_end_seconds'],'historical_pulse_status':meta['pulse_status'],'plecs_rpc_seconds':meta['plecs_simulate_rpc_seconds'],'plecs_csv_bytes':sum(e['bytes'] for e in meta['csv_exports']),'status':'NO_NETLIST','input_hashes':{str(p.relative_to(case)):sha(p) for p in (case/'pulse').glob('*') if p.is_file()}}
 print('START',row['case'],flush=True)
 if model.exists():
  row['module_build']=run([sys.executable,str(SOLVER/'scripts/build_software.py'),str(model),'--cc','gcc'],dest/'module-build',60)
  if row['module_build']['exit_code']!=0:row['status']='MODULE_BUILD_FAILED'
  else:
   budget=5*meta['plecs_simulate_rpc_seconds'];env=os.environ.copy();env.pop('PULSE_WALL_SECONDS',None)
   row['generation']=run([str(BUILD/'pulse-solver'),str(model),'--t-end',str(meta['original_end_seconds']),'--output-format','trajectory','--out',str(dest/'trajectory')],dest/'generation-log',budget,env)
   report=dest/'trajectory/simulation_report.json'
   if report.exists():
    r=json.loads(report.read_text());row.update(status=r['status'],simulated_seconds=r.get('simulated_seconds'),diagnostic=r.get('diagnostic'),source_sha256=r.get('source_sha256'))
   else:row.update(status='EXTERNAL_TIMEOUT' if row['generation']['external_timeout'] else 'NO_GENERATION_REPORT',stderr=(dest/'generation-log/stderr.txt').read_text()[-8000:])
   if row['generation']['external_timeout']:
    row['status']='TIMEOUT_5X_PLECS';row['timeout_label']='超时（>5×PLECS）';row['timeout_limit_seconds']=budget
   complete=row['generation']['exit_code']==0 and row['status']=='COMPLETED' and abs(row.get('simulated_seconds',-1)-meta['original_end_seconds'])<1e-12
   row['full_trajectory_completed']=complete
   row['archive_components']={p.name:p.stat().st_size for p in (dest/'trajectory').glob('*') if p.is_file()}
   if complete:
    row['trajectory_generation_seconds']=row['generation']['wall_seconds'];row['trajectory_archive_bytes']=sum(row['archive_components'].values());row['segments_bytes']=row['archive_components'].get('out.pevt');row['historical_plecs_over_pulse_time_ratio']=meta['plecs_simulate_rpc_seconds']/row['trajectory_generation_seconds'];row['plecs_csv_over_trajectory_size_ratio']=row['plecs_csv_bytes']/row['trajectory_archive_bytes']
    row['replay']=run([str(BUILD/'pulse-replay'),str(dest/'trajectory'),'--save-dt','1u','--out',str(dest/'replay')],dest/'replay-log',600)
    if row['replay']['exit_code']==0:
     try:
      ch,st,pt=accuracy(case,meta,dest/'replay/out.pewave.npz');allchannels+=ch;allstats+=st;allpoints+=pt;row['accuracy_status']='COMPARED';row['compared_channels']=sum(c['status']=='COMPARED' for c in ch);row['missing_channels']=[c['channel'] for c in ch if c['status']!='COMPARED'];row['points20_max_error_pct']=max((c['points20_max_error_pct'] for c in ch if c.get('points20_max_error_pct') is not None),default=None)
     except Exception as e:row['accuracy_status']='FAILED';row['accuracy_error']=repr(e)
    else:row['accuracy_status']='REPLAY_FAILED'
 before=row['input_hashes'];after={str(p.relative_to(case)):sha(p) for p in (case/'pulse').glob('*') if p.is_file()};row['inputs_unchanged']=before==after
 manifest['cases'].append(row);dump(OUT/'evidence.json',manifest)
 summary=[{k:r.get(k) for k in ['case','target_seconds','status','simulated_seconds','plecs_rpc_seconds','trajectory_generation_seconds','historical_plecs_over_pulse_time_ratio','plecs_csv_bytes','trajectory_archive_bytes','segments_bytes','plecs_csv_over_trajectory_size_ratio','accuracy_status','compared_channels','points20_max_error_pct']} for r in manifest['cases']]
 csvfile('SUMMARY.csv',summary);csvfile('CHANNEL_ACCURACY.csv',allchannels);csvfile('STATISTICS.csv',allstats);csvfile('POINTS20.csv',allpoints)
 print('DONE',row['case'],row['status'],row.get('diagnostic'),row.get('trajectory_generation_seconds'),row.get('accuracy_status'),flush=True)
print('ALL_FINISHED',flush=True)
