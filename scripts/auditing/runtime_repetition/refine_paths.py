#!/usr/bin/env python3
"""Additional exact context scopes for an observed COW allocation increase."""
import json,re
from pathlib import Path
def refine(source):
 entries=[
 ('src/solver_strategy.cpp',r'Mode portfolio_compile\([\s\S]*?int algorithm,CompilePurpose purpose\)\{','portfolio_compile'),
 ('src/state_coordinates.cpp',r'void publish_physical_state\(const Model&m,RunState&s\)\{','publish_physical'),
 ('src/state_coordinates.cpp',r'std::vector<double> state_signals_prepared\([^\n]*\)\{','state_signals_prepared'),
 ('src/engineering_flow.cpp',r'auto same=\[\]\(const Matrix&a,const Matrix&b\)\{','flow_same_matrix')]
 sites=[]
 for file,pattern,name in entries:
  p=source/file;s=p.read_text()
  assert 'audit_named_scope_'+name not in s
  hits=list(re.finditer(pattern,s));assert len(hits)==1,(file,pattern,len(hits))
  m=hits[0];s=s[:m.end()]+'audit::Scope audit_named_scope_'+name+'(pa_named_id("'+name+'"));'+s[m.end():]
  if 'extern "C" unsigned pa_named_id' not in s:s='extern "C" unsigned pa_named_id(const char*);\n'+s
  p.write_text(s);sites.append({'file':file,'name':name,'anchor':m[0]})
 p=source/'src/engineering_flow.cpp';s=p.read_text()
 a='  d.basis = basis(mode);'
 assert s.count(a)==1
 s=s.replace(a,a+' const void* audit_common_basis=d.basis.get();pa_blob(pa_named_id("flow_common_anchor_inputs"),&audit_common_basis,sizeof(audit_common_basis),initial.data(),size_t(initial.size())*sizeof(double),nullptr,0);')
 a='    Flow projection(view,data_->initial);'
 assert s.count(a)==1
 s=s.replace(a,'const void* audit_row_basis=data_->basis.get();pa_blob(pa_named_id("observe_basis_row_inputs"),&audit_row_basis,sizeof(audit_row_basis),row.data(),size_t(row.size())*sizeof(double),nullptr,0);'+a)
 p.write_text(s)
 return sites
if __name__=='__main__':
 import argparse,subprocess
 p=argparse.ArgumentParser();p.add_argument('--work',type=Path,required=True);a=p.parse_args()
 for v in ['C','D']:
  r=a.work/v
  subprocess.run(['g++','-std=c++20','-O2','-fPIC','-shared',str(Path(__file__).parent/'counters.cpp'),'-I'+str(r),'-I'+str(r/'source/third_party'),'-ldl','-o',str(r/'libcounts.so')],check=True)
  (r/'refined-paths.json').write_text(json.dumps(refine(r/'source'),indent=2)+'\n')
  with (r/'refined-build.log').open('w') as f:subprocess.run(['cmake','--build',str(r/'build'),'--target','pulse-solver','--parallel','2'],stdout=f,stderr=subprocess.STDOUT,check=True)
  (r/'50ms-count').rename(r/'50ms-count-initial')
 print('Extra path scopes built; initial count evidence retained.')
