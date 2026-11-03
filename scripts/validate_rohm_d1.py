#!/usr/bin/env python3
"""Full ROHM library: fresh PLECS, D1 Linux event generation, offline accuracy."""
import argparse,hashlib,io,json,pathlib,subprocess,sys,time,xmlrpc.client
import numpy as np
from scipy.io import loadmat
from benchmark_c002_end_to_end import Transport
def fp(p):
 p=pathlib.Path(p);h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return {'bytes':p.stat().st_size,'sha256':h.hexdigest()}
def save(p,j):p.write_text(json.dumps(j,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def compare(wave,rt,rv,channels):
 with np.load(wave,allow_pickle=False) as z:
  md=json.loads(str(z['metadata_json']));signals={x['name']:x['id'] for x in md['signals']};t=z['time']
  if not (t[0]==0 and t[-1]==rt[-1] and np.all(np.diff(t)>0)):raise ValueError('Incomplete reconstructed interval')
  rows=[];checks=[];missing=[]
  for i,c in enumerate(channels):
   name=c['pulse']
   if name not in signals:missing.append(name);continue
   ref=rv[:,i];actual=np.interp(rt,t,z[signals[name]].astype(float))
   if not np.isfinite(actual).all() or not np.isfinite(ref).all():raise ValueError('nonfinite accuracy input')
   delta=actual-ref;absolute=np.abs(delta);bound=c['atol']+.01*np.abs(ref);worst=int(np.argmax(absolute))
   stats={}
   for metric,fn in [('mean',np.mean),('rms',lambda x:np.sqrt(np.mean(x*x))),('max',np.max)]:
    expected,observed=float(fn(ref)),float(fn(actual));tol=c['atol']+.01*abs(expected);ok=abs(observed-expected)<=tol
    checks.append({'channel':name,'metric':metric,'reference':expected,'D1':observed,'tolerance':tol,'passed':bool(ok)})
    stats[metric]={'reference':expected,'D1':observed}
   rows.append({'channel':name,'unit':c['unit'],'atol':c['atol'],'samples':len(rt),'RMSE':float(np.sqrt(np.mean(delta*delta))),'MAE':float(np.mean(absolute)),
    'max_abs_error':float(absolute[worst]),'worst_time':float(rt[worst]),'reference_at_worst':float(ref[worst]),'D1_at_worst':float(actual[worst]),
    'pointwise_outside_tolerance':int(np.count_nonzero(absolute>bound)),'pointwise_pass_fraction':float(np.mean(absolute<=bound)),'statistics':stats})
 return {'method':'full original 1us reference grid, channel atol + 1%, no time shifts or edge exclusion','missing_channels':missing,
  'statistics_passed':sum(x['passed'] for x in checks),'statistics_total':len(checks),'checks':checks,'channels':rows,
  'pointwise_outliers':sum(x['pointwise_outside_tolerance'] for x in rows),'reference_channels':len(channels),
  'all_statistics_passed':bool(checks) and all(x['passed'] for x in checks) and not missing}
def main():
 p=argparse.ArgumentParser();p.add_argument('--case-set',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True)
 p.add_argument('--native-out',default='/root/rohm-d1-20261104');p.add_argument('--only',nargs='*');a=p.parse_args()
 root=pathlib.Path(__file__).resolve().parents[1];a.out.mkdir(parents=True,exist_ok=True)
 prefix=['wsl.exe','-d','Ubuntu-24.04','-u','root','--exec']
 def linux(*args,**kw):return subprocess.run(prefix+list(map(str,args)),check=True,**kw)
 def native(path):return subprocess.check_output(prefix+['wslpath','-u',str(path.resolve())],text=True).strip()
 ledger_path=a.out/'ledger.json'
 if ledger_path.exists():ledger=json.loads(ledger_path.read_text(encoding='utf-8'))
 else:
  ledger={'solver_code_commit':'05fb315f8126561a74b45fb06bf2654b0d138800','case_set_commit':subprocess.check_output(['git','-C',str(a.case_set),'rev-parse','HEAD'],text=True).strip(),
   'platforms':{'PLECS':'Windows PLECS 4.8.2','D1':'WSL2 Ubuntu native Linux Release'},
   'timing':'start simulation command to COMPLETED notification; PLECS simulate RPC includes MAT return; load, module build and offline replay excluded',
   'storage':'fresh PLECS MAT export and fixed CSV bytes; D1 PEVT and all generation files; offline wave files excluded',
   'wall_limit_multiplier':10,'cases':{}}
 save(ledger_path,ledger)
 order=['rohm-c002-d-boost','rohm-c006-d-buck','rohm-c010-d-flyback','rohm-c011-d-forward','rohm-a010-dot-totem-pole-pfc-sync']
 cases=sorted([q for q in a.case_set.iterdir() if (q/'provenance.json').exists()],key=lambda q:(order.index(q.name) if q.name in order else 100,q.name))
 for case in cases:
  name=case.name
  if a.only and name not in a.only:continue
  row=ledger['cases'].setdefault(name,{})
  if row.get('finished'):continue
  dest=a.out/name;dest.mkdir(exist_ok=True);meta=json.loads((case/'provenance.json').read_text(encoding='utf-8'))
  row.update(target_seconds=meta['original_end_seconds'],history=meta.get('historical_acceptance'),conditions_note=meta.get('conditions_note'),metadata_channels=meta['channels'])
  def checkpoint():save(ledger_path,ledger);save(dest/'result.json',row)
  checkpoint();print('CASE',name,flush=True)
  try:
   integrity={}
   for item in meta['pulse_inputs']+meta['csv_exports']+[{'file':meta['capture_model'],'sha256':meta['capture_sha256']}]:
    f=case/item['file'];actual=fp(f)
    if actual['sha256']!=item['sha256']:raise ValueError('Original SHA mismatch: '+str(f))
    integrity[item['file']]=actual
   row['original_files']=integrity;checkpoint()
   if 'PLECS' not in row:
    rpc=xmlrpc.client.ServerProxy('http://127.0.0.1:1080',transport=Transport(),allow_none=True)
    try:
     rpc.plecs.load((case/meta['capture_model']).resolve().as_posix())
     n=round(meta['original_end_seconds']/meta['csv_grid_seconds'])+1
     opts={'OutputFormat':'MatFile','SolverOpts':{'TimeSpan':meta['original_end_seconds'],'OutputTimesOption':'specified','OutputTimes':np.linspace(0,meta['original_end_seconds'],n).tolist(),'Timeout':900}}
     print('PLECS',name,flush=True);start=time.perf_counter();data=rpc.plecs.simulate(meta['capture_name'],opts);wall=time.perf_counter()-start
     (dest/'plecs.mat').write_bytes(data.data);m=loadmat(io.BytesIO(data.data));rt=m['Time'].ravel();rv=m['Values']
     if rv.shape==(len(meta['channels']),len(rt)):rv=rv.T
     if rv.shape!=(len(rt),len(meta['channels'])) or len(rt)!=n or rt[-1]!=meta['original_end_seconds'] or not np.isfinite(rv).all():raise ValueError('Incomplete/invalid PLECS capture')
     np.savez(dest/'reference.npz',time=rt,values=rv)
     row['PLECS']={'status':'COMPLETED','wall_seconds':wall,'MAT':fp(dest/'plecs.mat'),'samples':len(rt),'channels':rv.shape[1],'fresh':True}
    except Exception as e:
     row['PLECS']={'status':'FAILED','error':repr(e)}
    finally:
     try:rpc.plecs.close(meta['capture_name'])
     except Exception:pass
    checkpoint()
   if not (case/'pulse/netlist.md').exists():
    row['D1']={'status':'NOT_CONVERTED','reason':'No PULSE netlist in original case library'};row['finished']=True;checkpoint();continue
   if row['PLECS']['status']!='COMPLETED':
    row['D1']={'status':'NOT_RUN','reason':'No fresh PLECS timing for tenfold limit'};row['finished']=True;checkpoint();continue
   nr=a.native_out+'/'+name
   if 'D1' not in row:
    cmd=prefix+['python3',native(root/'scripts/rohm_d1_native.py'),'--case',native(case),'--out',nr,'--limit',str(10*row['PLECS']['wall_seconds'])]
    print('D1',name,flush=True)
    with (dest/'native-worker.txt').open('w',encoding='utf-8') as f:worker=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
    if worker.returncode:
     raise RuntimeError('Native worker failed; inspect native-worker.txt before resuming: '+str(worker.returncode))
    local=dest/'native-result.json'
    linux('cp',nr+'/result.json',native(local))
    row['D1']=json.loads(local.read_text(encoding='utf-8'));row['worker_returncode']=worker.returncode;checkpoint()
    if row['D1']['status'] in ('PREPARING','RUNNING'):
     raise RuntimeError('Native worker returned an unfinished result')
   if row['D1']['status']=='COMPLETED' and 'accuracy' not in row:
    print('ACCURACY',name,flush=True)
    replay=nr+'/accuracy-replay'
    # Original simulation SAVE_DT is untouched. Evaluate the event archive at
    # every original reference point, rather than materializing excess samples.
    cmd=prefix+['/root/pulse-stage-d1-20261104/build-linux/pulse-replay',nr+'/simulation','--save-dt',str(meta['csv_grid_seconds']),'--out',replay]
    with (dest/'replay-validation.txt').open('w',encoding='utf-8') as f:r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
    if r.returncode:row['accuracy']={'status':'RECONSTRUCTION_FAILED','returncode':r.returncode}
    else:
     wave=dest/'accuracy-wave.npz';linux('cp',replay+'/out.pewave.npz',native(wave))
     with np.load(dest/'reference.npz',allow_pickle=False) as z:rt=z['time'];rv=z['values']
     acc=compare(wave,rt,rv,meta['channels']);acc['status']='COMPARED';acc['reference']='fresh full-duration PLECS'
     pieces=[]
     for item in meta['csv_exports']:pieces.append(np.loadtxt(case/item['file'],delimiter=',',skiprows=1,ndmin=2))
     fixed=np.concatenate(pieces);fixed_result=compare(wave,fixed[:,0],fixed[:,1:],meta['channels'])
     save(dest/'accuracy-fixed-csv.json',fixed_result)
     acc['fixed_CSV_statistics_passed']=fixed_result['statistics_passed'];acc['fixed_CSV_statistics_total']=fixed_result['statistics_total']
     acc['fixed_CSV_pointwise_outliers']=fixed_result['pointwise_outliers']
     acc['fresh_vs_CSV']={'time_bytes_equal':np.array_equal(rt,fixed[:,0]),'max_abs_by_channel':{c['pulse']:float(np.max(np.abs(rv[:,i]-fixed[:,i+1]))) for i,c in enumerate(meta['channels'])}}
     save(dest/'accuracy.json',acc);row['accuracy']=acc
    checkpoint()
   row['finished']=True;checkpoint()
   print('DONE',name,row['D1']['status'],row['D1'].get('completion_wall_seconds'),row.get('accuracy',{}).get('statistics_passed'),flush=True)
  except Exception as e:
   row['harness_error']=repr(e);row['finished']=True;checkpoint();print('CASE ERROR',name,repr(e),flush=True)
 print('ALL CASES FINISHED',flush=True)
if __name__=='__main__':main()
