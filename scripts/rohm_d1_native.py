#!/usr/bin/env python3
"""Native Linux case worker; simulation measurements exclude all replay work."""
import argparse,hashlib,json,os,shutil,signal,subprocess,threading,time
from pathlib import Path
def fp(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return {'bytes':Path(p).stat().st_size,'sha256':h.hexdigest()}
def main():
 p=argparse.ArgumentParser();p.add_argument('--case',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--limit',type=float,required=True)
 p.add_argument('--binary',type=Path,default=Path('/root/pulse-stage-d1-20261104/build-linux/pulse-solver'));a=p.parse_args()
 a.out.mkdir(parents=True,exist_ok=False)
 meta=json.loads((a.case/'provenance.json').read_text())
 model=a.out/'model';shutil.copytree(a.case/'pulse',model,ignore=shutil.ignore_patterns('.pulse_modules','__pycache__'))
 checks={}
 for row in meta['pulse_inputs']:
  name=Path(row['file']).relative_to('pulse');q=fp(model/name);assert q['sha256']==row['sha256'];checks[str(name)]=q
 row={'status':'PREPARING','target_seconds':meta['original_end_seconds'],'limit_seconds':a.limit,'inputs':checks,'binary':fp(a.binary)}
 result=a.out/'result.json'
 def save():result.write_text(json.dumps(row,indent=2)+'\n')
 save()
 build=[os.sys.executable,str(Path(__file__).parent/'build_software.py'),str(model/'netlist.md')]
 with (a.out/'module-build.txt').open('w') as f:r=subprocess.run(build,stdout=f,stderr=subprocess.STDOUT)
 if r.returncode:row.update(status='PREPARATION_FAILED',returncode=r.returncode);save();return
 row['modules']={q.name:fp(q) for q in (model/'.pulse_modules').glob('*') if q.is_file()}
 output=a.out/'simulation';output.mkdir()
 cmd=['/usr/bin/time','-v','-o',str(a.out/'resource.txt'),str(a.binary),str(model/'netlist.md'),'--t-end',str(meta['original_end_seconds']),'--output-format','trajectory','--out',str(output)]
 env=os.environ.copy()
 for k in ['LD_PRELOAD','PULSE_COUNT_OUTPUT','PULSE_ALLOC_REPORT','PULSE_PROFILE_PHASES']:env.pop(k,None)
 # Existing engine budget stops calculation with a committed prefix. A hard
 # watchdog grants only diagnostic/archive cleanup; late results cannot pass.
 env['PULSE_WALL_SECONDS']=str(a.limit)
 row.update(status='RUNNING',command=cmd,watchdog_grace_seconds=30);save()
 notified=None;hard_timeout=threading.Event();start=time.perf_counter()
 with (a.out/'stdout.txt').open('w') as log,(a.out/'stderr.txt').open('w') as err:
  proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=err,text=True,env=env,start_new_session=True)
  def stop():
   if proc.poll() is None:
    hard_timeout.set()
    try:os.killpg(proc.pid,signal.SIGKILL)
    except ProcessLookupError:pass
  timer=threading.Timer(a.limit+30,stop);timer.start()
  try:
   for line in proc.stdout:
    log.write(line)
    if line.startswith('  "status":') and '"COMPLETED"' in line:notified=time.perf_counter()-start
   rc=proc.wait()
  finally:timer.cancel()
 elapsed=time.perf_counter()-start
 report={}
 if (output/'simulation_report.json').exists():report=json.loads((output/'simulation_report.json').read_text())
 diag=report.get('diagnostic')
 if not diag:
  try:diag=json.loads((a.out/'stderr.txt').read_text())
  except Exception:diag={'stderr':(a.out/'stderr.txt').read_text()[-8000:]}
 budget=(diag or {}).get('subcode')=='WALL_BUDGET'
 if rc==0 and report.get('status')=='COMPLETED' and notified is not None:
  status='COMPLETED'
 elif report.get('status')=='COMPLETED':
  # The calculation report can precede archive serialization. A nonzero
  # process exit or absent completion notification is not a delivered result.
  status='OUTPUT_FAILED'
 else:
  status=report.get('status','OUTPUT_FAILED')
 if hard_timeout.is_set() or budget or (notified is not None and notified>a.limit):status='TIME_LIMIT_EXCEEDED'
 row.update(status=status,solver_status=report.get('status'),completion_wall_seconds=notified,exit_wall_seconds=elapsed,returncode=rc,simulated_seconds=report.get('simulated_seconds'),diagnostic=diag,report=report,hard_timeout=hard_timeout.is_set())
 row['files']={q.name:fp(q) for q in output.iterdir() if q.is_file()}
 row['generation_output_bytes']=sum(v['bytes'] for v in row['files'].values())
 row['pevt_bytes']=row['files'].get('out.pevt',{}).get('bytes')
 for line in (a.out/'resource.txt').read_text().splitlines():
  for label,key,typ in [('User time (seconds):','CPU_user_seconds',float),('System time (seconds):','CPU_system_seconds',float),('Maximum resident set size (kbytes):','peak_RSS_KiB',int)]:
   if line.strip().startswith(label):row[key]=typ(line.strip()[len(label):].strip())
 save();print(json.dumps({k:row.get(k) for k in ['status','completion_wall_seconds','exit_wall_seconds','simulated_seconds','pevt_bytes','diagnostic']}),flush=True)
if __name__=='__main__':main()
