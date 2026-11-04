import json,pathlib,re,os
os.environ['MPLCONFIGDIR']='/tmp/pulse-d1-matplotlib'
import numpy as np
import matplotlib
matplotlib.use('Agg')
matplotlib.rcParams['path.simplify']=False
import matplotlib.pyplot as plt
ROOT=pathlib.Path('/workspace/PULSE-case-set');OUT=pathlib.Path('/workspace/pulse-d1-validation')
d=json.loads((OUT/'evidence.json').read_text());manifest=[]
for case in d['cases']:
 if case.get('accuracy_status')!='COMPARED':continue
 src=ROOT/case['folder'];meta=json.loads((src/'provenance.json').read_text());files=[src/e['file'] for e in meta['csv_exports']];names=files[0].open().readline().strip().split(',');ref=np.concatenate([np.loadtxt(f,delimiter=',',skiprows=1,ndmin=2) for f in files]);rt=ref[:,0]
 with np.load(OUT/case['folder']/'replay/out.pewave.npz',allow_pickle=False) as z:
  md=json.loads(str(z['metadata_json']));t=z['time'];signals={s['name']:z[s['id']].astype(float) for s in md['signals']}
 if len(t)==len(rt)+1 and abs(t[-1]-rt[-1])<1e-12 and np.max(np.abs(t[:len(rt)]-rt))<1e-12:
  signals={n:np.concatenate((v[:len(rt)-1],v[-1:])) for n,v in signals.items()};t=np.concatenate((t[:len(rt)-1],t[-1:]))
 if len(t)!=len(rt) or np.max(np.abs(t-rt))>1e-12:raise RuntimeError('time grids differ: '+case['case'])
 plotdir=OUT/case['folder']/'plots';plotdir.mkdir(parents=True,exist_ok=True)
 for ch in meta['channels']:
  name=ch['pulse'];r=ref[:,names.index(name)];a=signals.get(name);safe=re.sub(r'[^A-Za-z0-9_.-]+','_',name)
  for label,select in [('full',slice(None)),('last_1ms',rt>=rt[-1]-.001-1e-12)]:
   fig,ax=plt.subplots(figsize=(11,4));ax.plot(rt[select],r[select],label='PLECS',lw=.7,color='#2459a6');ax.plot(rt[select],a[select],label='PULSE D1',lw=.7,alpha=.8,color='#d2691e',linestyle='--') if a is not None else None
   ax.set(xlabel='Time (s)',ylabel=name+' ('+ch['unit']+')',title=case['case']+' — '+name+' — '+label+(' — D1 channel absent' if a is None else ''));ax.grid(alpha=.2);ax.legend();fig.tight_layout();dest=plotdir/(safe+'_'+label+'.png');fig.savefig(dest,dpi=120);plt.close(fig);manifest.append({'case':case['case'],'channel':name,'window':label,'plecs_samples':int(len(rt[select])),'pulse_present':a is not None,'file':str(dest.relative_to(OUT))})
 print('PLOTS',case['case'],flush=True)
(OUT/'PLOT_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
