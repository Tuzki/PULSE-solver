import json,pathlib,shutil,re,subprocess
P=pathlib.Path('/workspace/pulse-d1-validation');repo=pathlib.Path('/workspace/PULSE-solver');target=repo/'docs/reports/d1_plecs_full_validation_20261104'
e=json.loads((P/'evidence.json').read_text());assert len(e['cases'])==20
plots=json.loads((P/'PLOT_MANIFEST.json').read_text());report=(P/'REPORT.md').read_text()
paths=re.findall(r'!\[[^]]*\]\(([^)]+\.png)\)',report);assert len(paths)==len(plots),(len(paths),len(plots))
assert all((P/x).is_file() for x in paths)
if target.exists():raise RuntimeError('Report destination already exists; refusing to overwrite: '+str(target))
target.mkdir(parents=True)
for name in ['REPORT.md','SUMMARY.csv','CHANNEL_ACCURACY.csv','STATISTICS.csv','POINTS20.csv','PLOT_MANIFEST.json','MACHINE.json','evidence.json','evidence_raw.json','RUN.log','CTEST.log','AUDIT.log','audit_results.py','prepare_github.py','run_comparison.py','repair_accuracy.py','split_case_tables.py','full_overlays.py','make_report.py','finalize_results.py']:
 src=P/name
 if not src.is_file():raise RuntimeError('Missing report file: '+name)
 shutil.copy2(src,target/name)
for item in plots:
 path=pathlib.Path(item['file']);src=P/path;dst=target/path;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
for row in e['cases']:
 if row.get('accuracy_status')!='COMPARED':continue
 for name in ['POINTS20.csv','STATISTICS.csv']:
  src=P/row['folder']/name;dst=target/row['folder']/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
for path in target.rglob('*'):
 if path.is_file():
  if path.stat().st_size>=95*1024**2:raise RuntimeError('File too large for GitHub: '+str(path))
  if path.suffix.lower() in ('.pevt','.npz'):raise RuntimeError('Raw data must remain in the cloud workspace: '+str(path))
files=[p for p in target.rglob('*') if p.is_file()];print('REPORT_DIRECTORY',target,'FILES',len(files),'BYTES',sum(p.stat().st_size for p in files),'PLOTS',len(plots))
