import collections,csv,hashlib,json,math,pathlib,re,zipfile
import numpy as np
from PIL import Image
P=pathlib.Path('/workspace/pulse-d1-validation');ROOT=pathlib.Path('/workspace/PULSE-case-set');d=json.loads((P/'evidence.json').read_text());expected={r['path']:r['sha256'] for r in json.loads((ROOT/'SHA256SUMS.json').read_text())};plots=json.loads((P/'PLOT_MANIFEST.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(pathlib.Path('/workspace/pulse-d1-build/pulse-solver'))==d['solver_binary_sha256']
assert len(d['cases'])==20 and len({r['case'] for r in d['cases']})==20
with (P/'POINTS20.csv').open(newline='') as f: pts=list(csv.DictReader(f))
with (P/'STATISTICS.csv').open(newline='') as f: stats=list(csv.DictReader(f))
pg=collections.defaultdict(list);sg={}
for x in pts:pg[x['case'],x['channel']].append(x)
for x in stats:
 k=(x['case'],x['channel'],x['metric']);assert k not in sg;sg[k]=x
compared=0
for r in d['cases']:
 src=ROOT/r['folder']
 for path,digest in r['input_hashes'].items():assert sha(src/path)==digest==expected[r['folder']+'/'+path]
 if r.get('accuracy_status')!='COMPARED':continue
 assert r['full_trajectory_completed'] and r['generation']['exit_code']==0 and r['replay']['exit_code']==0 and math.isclose(r['simulated_seconds'],r['target_seconds'],abs_tol=1e-12)
 meta=json.loads((src/'provenance.json').read_text());names=(src/meta['csv_exports'][0]['file']).open().readline().strip().split(',');parts=[]
 for e in meta['csv_exports']:
  fp=src/e['file'];assert sha(fp)==e['sha256'];parts.append(np.loadtxt(fp,delimiter=',',skiprows=1,ndmin=2))
 ref=np.concatenate(parts);rt=ref[:,0]
 with np.load(P/r['folder']/'replay/out.pewave.npz',allow_pickle=False) as z:
  info=json.loads(str(z['metadata_json']));t=z['time'];signals={v['name']:z[v['id']].astype(float) for v in info['signals']}
 if len(t)==len(rt)+1 and abs(t[-1]-rt[-1])<1e-12 and np.max(np.abs(t[:len(rt)]-rt))<1e-12:
  signals={n:np.concatenate((v[:len(rt)-1],v[-1:])) for n,v in signals.items()};t=np.concatenate((t[:len(rt)-1],t[-1:]))
 assert len(t)==len(rt) and np.max(np.abs(t-rt))<1e-12
 for ch in meta['channels']:
  name=ch['pulse'];entries=pg.get((r['case'],name),[])
  if name not in signals:assert not entries;continue
  rv=ref[:,names.index(name)];av=signals[name];den=float(np.mean(np.abs(rv)));assert len(entries)==20
  assert [int(p['point']) for p in entries]==list(range(1,21))
  for p in entries:
   i=int(round(float(p['time_s'])/1e-6));assert 0<=i<len(rt) and abs(rt[i]-float(p['time_s']))<1e-12
   assert math.isclose(float(p['plecs']),float(rv[i]),rel_tol=1e-12,abs_tol=1e-12)
   assert math.isclose(float(p['pulse']),float(av[i]),rel_tol=1e-12,abs_tol=1e-12)
   assert math.isclose(float(p['plecs_full_mean_abs']),den,rel_tol=1e-12,abs_tol=1e-12)
   delta=abs(float(av[i])-float(rv[i]));assert math.isclose(float(p['abs_delta']),delta,rel_tol=1e-12,abs_tol=1e-12)
   if den>0:assert math.isclose(float(p['error_pct_mean_abs']),100*delta/den,rel_tol=1e-11,abs_tol=1e-12)
   else:assert not p['error_pct_mean_abs']
  assert abs(float(entries[0]['time_s']))<1e-12 and abs(float(entries[-1]['time_s'])-r['target_seconds'])<1e-12
  for metric,fn in [('mean',np.mean),('rms',lambda x:np.sqrt(np.mean(x*x))),('min',np.min),('max',np.max)]:
   q=sg[r['case'],name,metric];assert math.isclose(float(q['plecs']),float(fn(rv)),rel_tol=1e-12,abs_tol=1e-12);assert math.isclose(float(q['pulse']),float(fn(av)),rel_tol=1e-12,abs_tol=1e-12)
  images=[p for p in plots if p['case']==r['case'] and p['channel']==name];assert len(images)==2
  for p in images:
   assert p['pulse_present'];assert p['plecs_samples']==(len(rt) if p['window']=='full' else int(np.count_nonzero(rt>=rt[-1]-.001-1e-12)))
   with Image.open(P/p['file']) as im:assert im.width>=1000 and im.height>=400;im.verify()
  compared+=1
assert len(sg)==4*len(pg) and compared==len(pg)
report=(P/'REPORT.md').read_text();links=re.findall(r'\]\(([^)]+)\)',report)
for link in links:
 if not link.startswith(('https://','http://','#')):assert (P/link).is_file(),link
with zipfile.ZipFile(P/'comparison-results.zip') as z:assert z.testzip() is None
print('PASS:',len(d['cases']),'cases,',compared,'channels,',len(pts),'point rows,',len(stats),'statistics rows,',len(plots),'plots; source/input hashes, report links and ZIP checked')
