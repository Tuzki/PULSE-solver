import csv,json,pathlib
P=pathlib.Path('/workspace/pulse-d1-validation');e=json.loads((P/'evidence.json').read_text());lookup={r['case']:r['folder'] for r in e['cases']}
for source,name in [('POINTS20.csv','POINTS20.csv'),('STATISTICS.csv','STATISTICS.csv')]:
 with (P/source).open(newline='') as f:
  rd=csv.DictReader(f);fields=rd.fieldnames;group={}
  for row in rd:group.setdefault(row['case'],[]).append(row)
 for case,rows in group.items():
  dest=P/lookup[case]/name
  with dest.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
  print(case,name,len(rows))
