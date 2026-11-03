from pathlib import Path
import re,gzip,json,csv,collections
import argparse
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('/root/stage-c-cpu-profile-20261103'));w=p.parse_args().root
m=json.loads((w/'cpu-sampling-500ms/measurement.json').read_text());cpu=m['cpu_total_seconds'];rows=[];cur=None
with gzip.open(w/'cpu-sampling-500ms/perf-script.txt.gz','rt',errors='replace') as f:
 for line in f:
  z=re.match(r'^\s*\S+\s+(\d+)\s+([0-9.]+):\s+(\d+)\s+cpu-clock[^:]*:',line)
  if z:
   if cur and cur[1]:rows.append(cur)
   cur=[int(z[3]),[]] if int(z[1])==m['pid'] else None;continue
  if re.match(r'^\s*\S+\s+\d+\s+(?:\[\d+\]\s+)?[0-9.]+:',line):
   if cur and cur[1]:rows.append(cur)
   cur=None;continue
  if cur is not None:
   z=re.match(r'\s+[0-9a-f]+\s+(.+)\s+\(([^()]*)\)\s*$',line)
   if z:cur[1].append(re.sub(r'\+0x[0-9a-f]+$','',z[1]))
if cur and cur[1]:rows.append(cur)
total=sum(x[0] for x in rows);parts=collections.Counter();groups=collections.Counter()
for weight,names in rows:
 text='\n'.join(names)
 if 'Flow::observe(' in text:
  if 'Flow::Flow(' in text:key='temporary_Flow_constructor'
  elif 'CowValue<pulse::ModeBinding>::edit' in text:key='view_binding_COW_clone'
  elif 'prepare_local(' in text:key='local_polynomial_preparation'
  elif 'Mode::Mode(' in text:key='view_Mode_copy'
  elif re.match(r'^(?:__)?(?:libc_)?(?:malloc|calloc|realloc|free|cfree|_int_malloc|_int_free|malloc_consolidate|unlink_chunk|sysmalloc)',names[0]):key='other_allocator_work'
  else:key='guard_matching_cache_lookup_and_evaluation'
  parts[key]+=weight
 if 'bind_observations(' in text and '::Assembler::Assembler(' in text:groups['bind_Assembler_constructor']+=weight
 if 'bind_observations(' in text and '::Assembler::held(' in text:groups['bind_held_resolution']+=weight
 if 'Flow::compatible(' in text and 'memcmp' in names[0]:groups['compatible_memcmp_leaf']+=weight
 if 'bind_observations(' in text and 'memcmp' in names[0]:groups['bind_memcmp_leaf']+=weight
 if 'PevtArchive::' in text and 'memcmp' in names[0]:groups['archive_memcmp_leaf']+=weight
out=w/'analysis-final'
def write(name,values):
 data=[{'component':k,'cpu_seconds_estimate':cpu*v/total,'percent_of_process':100*v/total} for k,v in values.most_common()]
 with (out/name).open('w',newline='') as f:
  q=csv.DictWriter(f,fieldnames=list(data[0]));q.writeheader();q.writerows(data)
 return data
print('observe parts',write('OBSERVE_BREAKDOWN.csv',parts));print('selected nested groups',write('REPEAT_COST_CONTEXTS.csv',groups))
