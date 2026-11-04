import csv,hashlib,json,pathlib,collections,zipfile,subprocess,math
P=pathlib.Path('/workspace/pulse-d1-validation');d=json.loads((P/'evidence.json').read_text());d['archive_note']='D1 trajectory bytes cover out.pevt and simulation_report.json; out.pevt bytes are separately reported. PLECS comparison uses original uncompressed waveform CSV chunks.';((P/'evidence_raw.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n') if not (P/'evidence_raw.json').exists() else None)
for r in d['cases']:
 if r.get('generation',{}).get('exit_code') not in (None,0):
  error=P/r['folder']/'generation-log/stderr.txt'
  if error.exists():
   try:
    r['archive_or_process_diagnostic']=json.loads(error.read_text())
    if r['status']=='NO_GENERATION_REPORT':r['diagnostic']=r['archive_or_process_diagnostic'];r['status']='PROCESS_ERROR'
   except ValueError:r['process_stderr_tail']=error.read_text()[-4000:]
  if r['status']=='COMPLETED':
   r['simulation_status']='COMPLETED';r['status']='ARCHIVE_WRITE_FAILED';r['diagnostic']=r.get('archive_or_process_diagnostic',{});r['accuracy_status']='NOT_COMPARED_ARCHIVE_FAILED'
 if r['status'].startswith('TIMEOUT'):r['timeout_label']='超时（>5×PLECS）';r['accuracy_status']='NOT_COMPARED_TIMEOUT'
 if not r.get('full_trajectory_completed') and not r.get('accuracy_status'):r['accuracy_status']='NOT_COMPARED_INCOMPLETE'
 if 'generation' in r:r['diagnostic_process_seconds']=r['generation']['wall_seconds'];r['timeout_limit_seconds']=5*r['plecs_rpc_seconds']
 case=pathlib.Path('/workspace/PULSE-case-set')/r['folder'];now={str(p.relative_to(case)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (case/'pulse').glob('*') if p.is_file()}
 if now!=r['input_hashes']:raise RuntimeError('Original input modified: '+r['case'])
 r['inputs_unchanged']=True
assert len(d['cases'])==20
assert d['solver_commit']=='9f49f733863b90d8356aee22595e71e72fcc2c2b'
assert len({r['case'] for r in d['cases']})==20
(P/'evidence.json').write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
keys=['case','target_seconds','status','simulated_seconds','plecs_rpc_seconds','trajectory_generation_seconds','historical_plecs_over_pulse_time_ratio','plecs_csv_bytes','trajectory_archive_bytes','segments_bytes','plecs_csv_over_trajectory_size_ratio','accuracy_status','compared_channels','points20_max_error_pct','diagnostic_process_seconds','timeout_limit_seconds','timeout_label']
with (P/'SUMMARY.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');w.writeheader();w.writerows(sorted(d['cases'],key=lambda r:r['case']))
subprocess.run(['/workspace/pulse-tools/bin/python',str(P/'make_report.py')],check=True)
points=list(csv.DictReader((P/'POINTS20.csv').open()));group=collections.Counter((r['case'],r['channel']) for r in points);assert all(v==20 for v in group.values())
for point in points:
 delta=abs(float(point['pulse'])-float(point['plecs']));den=float(point['plecs_full_mean_abs'])
 assert math.isclose(delta,float(point['abs_delta']),rel_tol=1e-11,abs_tol=1e-12)
 if den>0:assert math.isclose(100*delta/den,float(point['error_pct_mean_abs']),rel_tol=1e-11,abs_tol=1e-12)
 else:assert not point['error_pct_mean_abs']
assert len(list(csv.DictReader((P/'STATISTICS.csv').open())))==4*len(group)
with zipfile.ZipFile(P/'comparison-results.zip','w',zipfile.ZIP_DEFLATED) as z:
 for p in sorted(P.iterdir()):
  if p.is_file() and p.suffix in ['.md','.csv','.json','.py','.log'] and p.stat().st_size<10*1024**2:z.write(p,p.name)
 for plot in sorted(P.glob('*/plots/*.png')):z.write(plot,plot.relative_to(P))
 for name in ('POINTS20.csv','STATISTICS.csv'):
  for table in sorted(P.glob('*/'+name)):z.write(table,table.relative_to(P))

plots=json.loads((P/'PLOT_MANIFEST.json').read_text())
for r in d['cases']:
 if r.get('accuracy_status')!='COMPARED': continue
 meta=json.loads((pathlib.Path('/workspace/PULSE-case-set')/r['folder']/'provenance.json').read_text())
 actual=[p for p in plots if p['case']==r['case']]
 assert len(actual)==2*len(meta['channels']), (r['case'],len(actual),len(meta['channels']))
 assert all((P/x['file']).is_file() and (P/x['file']).stat().st_size>1000 for x in actual)
print('PLOTS',len(plots))
print('FINAL',collections.Counter(r['status'] for r in d['cases']))
print('POINTS',len(points),'CHANNELS',len(group))
