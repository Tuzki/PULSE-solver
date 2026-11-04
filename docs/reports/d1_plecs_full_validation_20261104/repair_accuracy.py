import ast,csv,hashlib,json,os,pathlib,sys
import numpy as np
OUT=pathlib.Path('/workspace/pulse-d1-validation');ROOT=pathlib.Path('/workspace/PULSE-case-set')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
source=(OUT/'run_comparison.py').read_text();tree=ast.parse(source);node=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='accuracy');exec(ast.get_source_segment(source,node),globals())
def readcsv(name):
 p=OUT/name
 return list(csv.DictReader(p.open())) if p.exists() else []
def writecsv(name,rows):
 if not rows:return
 keys=list(dict.fromkeys(k for r in rows for k in r))
 with (OUT/name).open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
e=json.loads((OUT/'evidence.json').read_text());channels=readcsv('CHANNEL_ACCURACY.csv');stats=readcsv('STATISTICS.csv');points=readcsv('POINTS20.csv')
for r in e['cases']:
 if r.get('accuracy_status')!='FAILED' or 'replay/reference grids do not align' not in r.get('accuracy_error',''):continue
 case=ROOT/r['folder'];meta=json.loads((case/'provenance.json').read_text());ch,st,pt=accuracy(case,meta,OUT/r['folder']/'replay/out.pewave.npz');channels+=ch;stats+=st;points+=pt
 r['accuracy_initial_error']=r.pop('accuracy_error');r['accuracy_status']='COMPARED';r['accuracy_repair']='Keep final committed endpoint where replay provides a duplicate endpoint less than 1 ps apart';r['compared_channels']=sum(c['status']=='COMPARED' for c in ch);r['missing_channels']=[c['channel'] for c in ch if c['status']!='COMPARED'];r['points20_max_error_pct']=max((c['points20_max_error_pct'] for c in ch if c.get('points20_max_error_pct') is not None),default=None);print('REPAIRED',r['case'],flush=True)
(OUT/'evidence.json').write_text(json.dumps(e,ensure_ascii=False,indent=2,allow_nan=False)+'\n');writecsv('CHANNEL_ACCURACY.csv',channels);writecsv('STATISTICS.csv',stats);writecsv('POINTS20.csv',points)
