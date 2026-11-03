#!/usr/bin/env python3
"""Anchor-checked count overlay for isolated C/D Release trees; never edits repo."""
import json,re
from pathlib import Path

class Overlay:
 def __init__(self,root):self.root=Path(root);self.labels=['unused','hash_std','hash_std_bytes'];self.sites=[]
 def id(self,name):
  label=name.replace('.','_')
  if label not in self.labels:self.labels.append(label)
  return 'audit::'+label
 def count(self,name,n='1'):return 'pa_count('+self.id(name)+','+str(n)+');'
 def scope(self,name):return 'audit::Scope audit_scope_'+str(len(self.sites))+'('+self.id(name)+');'
 def load(self,p):return (self.root/p).read_text()
 def save(self,p,s):(self.root/p).write_text(s)
 def replace(self,p,a,b,expected=1):
  s=self.load(p);n=s.count(a)
  if n!=expected:raise ValueError((p,a[:100],n,expected))
  self.sites.append({'file':p,'original_line':s[:s.index(a)].count('\n')+1,'anchor':a[:180]})
  self.save(p,s.replace(a,b))
 def function(self,p,pattern,name):
  s=self.load(p);hits=list(re.finditer(pattern,s,re.M));assert len(hits)==1,(p,pattern,len(hits))
  m=hits[0];self.replace(p,m[0],m[0]+'\n'+self.scope(name))
 def before(self,p,a,name,n='1'):self.replace(p,a,self.count(name,n)+a)
 def apply(self,version):
  core='include/pulse/core.hpp';cow='include/pulse/cow_value.hpp';desc='src/descriptor.cpp';flow='src/engineering_flow.cpp';pevt='src/pevt.cpp'
  self.replace(core,'#pragma once','#pragma once\n#include "audit.hpp"')
  self.replace(cow,'#pragma once','#pragma once\n#include "audit.hpp"\n#include <type_traits>\nnamespace pulse { struct ModeBinding; struct ModeDefinition; }')
  typ='(std::is_same_v<T,pulse::ModeBinding>?'+self.id('cow.binding.copy')+':'+self.id('cow.other.copy')+')'
  self.replace(cow,'CowValue(const CowValue&) noexcept = default;',f'CowValue(const CowValue& x) noexcept :value_(x.value_) {{pa_count({typ},1);}}')
  self.replace(cow,'CowValue& operator=(const CowValue&) noexcept = default;',f'CowValue& operator=(const CowValue& x) noexcept {{value_=x.value_;pa_count({typ},1);return *this;}}')
  edit='(std::is_same_v<T,pulse::ModeBinding>?'+self.id('cow.binding.edit')+':'+self.id('cow.other.edit')+')'
  deep='(std::is_same_v<T,pulse::ModeBinding>?'+self.id('cow.binding.detach')+':'+self.id('cow.other.detach')+')'
  self.replace(cow,'T& edit() {','T& edit() { audit::Scope audit_edit('+edit+');')
  self.replace(cow,'if (!value_.unique()) value_ = std::make_shared<T>(*value_);','if (!value_.unique()) {audit::Scope audit_detach('+deep+');value_ = std::make_shared<T>(*value_);}')
  self.function('apps/cli.cpp',r'int main\(int argc, char \*\*argv\) \{','cli')
  self.function('src/runtime.cpp',r'Result simulate\(const Model &original, const Options &o\) \{','simulate')
  for pattern,name in [(r'std::string candidate_key\([\s\S]*?\) \{','mode.key'),(r'Mode instantiate_cached\([\s\S]*?bool classification_only\) \{','mode.instantiate'),(r'Mode compile_specified\([\s\S]*?CompilePurpose purpose\) \{','mode.compile'),(r'Mode bind_observations\([\s\S]*?\)\{','bind'),(r'void portfolio_original_check\([^\n]*\)\{','original.check')]:self.function(desc,pattern,name)
  anchor='partidx(mm.compiled_part_index) {' if version=='D' else ': m(mm), regs(rr), bits(std::move(bb)), segments(std::move(ss)) {'
  self.replace(desc,anchor,anchor+'\n'+self.scope('assembler'))
  if version=='C':
   self.replace(desc,'if(!equations){for(size_t i=0;i<m.parts.size();++i)partidx[m.parts[i].raw.id]=int(i);return;}',
    'if(!equations){'+self.count('index.rebuild')+'for(size_t i=0;i<m.parts.size();++i){'+self.count('index.insert')+'partidx[m.parts[i].raw.id]=int(i);}return;}')
   self.replace(desc,'for (size_t i = 0; i < m.parts.size(); ++i)\n            partidx[m.parts[i].raw.id] = int(i);',self.count('index.rebuild')+'for (size_t i = 0; i < m.parts.size(); ++i){'+self.count('index.insert')+'partidx[m.parts[i].raw.id] = int(i);}')
  else:
   self.id('index.rebuild');self.id('index.insert')
   self.replace('src/semantics.cpp','for (size_t i = 0; i < m.parts.size(); ++i)\n            m.compiled_part_index.emplace(m.parts[i].raw.id, int(i));',self.count('index.frozen.build')+'for (size_t i = 0; i < m.parts.size(); ++i){'+self.count('index.frozen.insert')+'m.compiled_part_index.emplace(m.parts[i].raw.id, int(i));}')
  snapshot='\n auto audit_A=audit::matrix('+self.id('bind.input.A')+',binding.A);auto audit_N=audit::matrix('+self.id('bind.input.N')+',N);auto audit_B=audit::matrix('+self.id('bind.input.B')+',B);unsigned long long audit_inputs[]={audit_A,audit_N,audit_B};\n'
  self.replace(desc,'    int na=int(N.rows());','    '+snapshot+'int na=int(N.rows());')
  for a,name in [('mode.binding.edit().residual_map.topRows(na)=binding.A*N-B;','bind.matrix.residual'),('scale.topRows(na)=binding.A.cwiseAbs()*N.cwiseAbs()+B.cwiseAbs();','bind.matrix.scale')]:
   self.replace(desc,a,'{'+self.scope(name)+'pa_blob('+self.id(name+'.inputs')+',audit_inputs,sizeof(audit_inputs),nullptr,0,nullptr,0);'+a+'}')
  self.before(desc,'    for(int i=0;i<na;++i){','bind.norm.rows','na')
  self.before(desc,'    for(int j=0;j<=m.ns;++j)','bind.norm.columns','m.ns+1')
  self.before(desc,'    for(int i=0;i<na;++i)for(int j=0;j<=m.ns;++j){','bind.scale.cells','na*(m.ns+1)')
  for pattern,name in [(r'std::shared_ptr<Basis> basis\(const Mode &mode\) \{','basis.lookup'),(r'void prepare_local\(FlowData &d\) \{','taylor.prepare'),(r'Flow::Flow\(const Mode &mode, const Vector &initial\)[\s\S]*?: data_\(std::make_shared<FlowData>\(\)\) \{','flow.construct'),(r'bool Flow::compatible\(const Mode &m\) const \{','flow.compatible'),(r'Flow Flow::continued\([^\n]*\) const \{','flow.continued'),(r'std::optional<Flow> Flow::continue_if_compatible\([^\n]*\) const \{','flow.continue_if'),(r'Flow Flow::continued_after_check\([^\n]*\) const \{','flow.continue_after'),(r'double Flow::observe\([^\n]*\) const \{','flow.observe'),(r'Vector Flow::state\(double t\) const \{','flow.state'),(r'double Flow::value\([^\n]*\) const \{','flow.value')]:self.function(flow,pattern,name)
  self.replace(flow,'if (d.local_ready) return;','if (d.local_ready) {'+self.count('taylor.ready.hit')+'return;}'+self.count('taylor.projection.build'))
  a='  if(!anchor.ready) {' if version=='D' else '  WVector z = WVector::Ones(n + 1);'
  ins=self.count('taylor.recurrence.build')+'\n const void* audit_basis=d.basis.get();double audit_rate=d.local_rate;pa_blob('+self.id('taylor.recurrence.inputs')+',&audit_basis,sizeof(audit_basis),d.initial.data(),size_t(d.initial.size())*sizeof(double),&audit_rate,sizeof(audit_rate));\n'
  self.replace(flow,a,(a+ins) if version=='D' else (ins+a))
  a='for (int j=1;j<=FlowData::local_degree;++j) {' if version=='D' else 'for (int j = 1; j <= FlowData::local_degree; ++j) {'
  self.replace(flow,a,a+self.count('taylor.recurrence.steps'))
  self.replace(flow,'++flow_counts.basis_misses;','++flow_counts.basis_misses;'+self.count('basis.build'))
  self.replace(flow,'++flow_counts.basis_hits;','++flow_counts.basis_hits;'+self.count('basis.reuse'),expected=2)
  self.before(flow,'    Flow projection(view,data_->initial);','flow.observe.projection.miss')
  self.replace(flow,'if(same_guards){++flow_counts.reused;','if(same_guards){'+self.count('flow.continue.shared')+'++flow_counts.reused;')
  self.before(flow,'  ++flow_counts.reprojected;','flow.continue.reprojected')
  self.replace(flow,'return value(k,t,derivative);','{'+self.count('flow.observe.guard.hit')+'return value(k,t,derivative);}')
  self.replace(flow,'return -value(k,t,derivative);','{'+self.count('flow.observe.guard.negative.hit')+'return -value(k,t,derivative);}')
  for pattern,name in [(r'uint32_t equation\(const Mode&m\) \{','pevt.equation'),(r'bool same_archive_definition\(const Mode&a,const Mode&b\) const \{','pevt.definition.compare'),(r'bool same_reference\(const Mode&a,const Mode&b\) const \{','pevt.reference.compare'),(r'uint32_t value_set\(const Mode&m\) \{','pevt.value_set'),(r'uint32_t block\([^\n]*\) \{','pevt.block'),(r'uint32_t state\([^\n]*\) \{','pevt.state'),(r'uint32_t bind_instance\([^\n]*\)\{','pevt.instance'),(r'uint32_t flow\([^\n]*\) \{','pevt.flow'),(r'void PevtArchive::append\([^\n]*\)\{','pevt.append'),(r'void PevtArchive::write\([^\n]*\)const \{','pevt.write'),(r'void put\([^\n]*\)\{','pevt.serialize.word'),(r'void real\([^\n]*\)\{','pevt.serialize.real'),(r'void time\([^\n]*\)\{','pevt.serialize.time'),(r'Bytes text\([^\n]*\)\{','pevt.serialize.json'),(r'std::string key\([^\n]*\)\{','pevt.serialize.key'),(r'uint64_t discrete_signature\([^\n]*\)\s*\{','pevt.signature')]:self.function(pevt,pattern,name)
  self.before(pevt,'    ++definition_encodes;','pevt.definition.encode')
  self.before(pevt,'definitions.push_back(std::move(definition));','pevt.definition.new')
  self.before(pevt,'values.push_back(std::move(v));return id;','pevt.value.new')
  self.before(pevt,'states.push_back({x,vs});','pevt.state.new')
  self.before(pevt,'instances.push_back({definition,values_id});','pevt.instance.new')
  self.function('src/trajectory.cpp',r'Json archive_encode_mode\(const Mode&m\)\{','pevt.encode_mode')
  for p in [pevt,flow]:
   label=self.id('pevt.memcmp' if p==pevt else 'flow.memcmp')
   s=self.load(p);s=s.replace('std::memcmp(',f'audit::memcmp({label},');self.save(p,s)
  if version=='D':
   self.function('include/pulse/stage_d_runtime.hpp',r'inline std::uint64_t hash_bytes\([^\n]*\) noexcept \{','hash.fnv')
   self.before('include/pulse/stage_d_runtime.hpp','  std::uint64_t hash = fnv_offset;','hash.fnv.bytes','size')
  mem='third_party/eigen-3.4.0/Eigen/src/Core/util/Memory.h'
  self.save(mem,'#include "audit.hpp"\n'+self.load(mem))
  for pattern,name in [(r'inline void\* aligned_malloc\(std::size_t size\)\n\{','eigen.allocate'),(r'inline void\* conditional_aligned_malloc<false>\(std::size_t size\)\n\{','eigen.allocate.unaligned'),(r'inline void\* aligned_realloc\([^\n]*\)\n\{','eigen.reallocate'),(r'inline void\* conditional_aligned_realloc<false>\([^\n]*\)\n\{','eigen.reallocate.unaligned')]:self.function(mem,pattern,name)
  self.header()
  cmake=self.load('CMakeLists.txt');cmake+='\nadd_library(count_runtime SHARED IMPORTED)\nset_target_properties(count_runtime PROPERTIES IMPORTED_LOCATION "'+str(self.root.parent/'libcounts.so')+'")\ntarget_include_directories(pulse_core PUBLIC "'+str(self.root.parent)+'")\ntarget_link_libraries(pulse_core PUBLIC count_runtime)\n'
  self.save('CMakeLists.txt',cmake)
  return {'version':version,'labels':self.labels,'sites':self.sites}
 def header(self):
  labels=',\n'.join(self.labels)+',label_count'
  names=',\n'.join(json.dumps(x) for x in self.labels)
  s='''#pragma once
#include <cstddef>
#include <cstring>
extern "C" unsigned pa_enter(unsigned);
extern "C" void pa_leave(unsigned);
extern "C" void pa_count(unsigned,unsigned long long);
extern "C" unsigned long long pa_blob(unsigned,const void*,size_t,const void*,size_t,const void*,size_t);
namespace audit {
enum Id {LABELS};
inline constexpr const char* names[]={NAMES};
struct Scope {unsigned old; explicit Scope(unsigned id):old(pa_enter(id)){} ~Scope(){pa_leave(old);}};
template<class T> unsigned long long matrix(unsigned id,const T&m){long long shape[]={m.rows(),m.cols()};return pa_blob(id,shape,sizeof(shape),m.data(),size_t(m.size())*sizeof(typename T::Scalar),nullptr,0);}
inline int memcmp(unsigned id,const void*a,const void*b,size_t n){pa_count(id,1);return std::memcmp(a,b,n);}
}
'''.replace('LABELS',labels).replace('NAMES',names)
  (self.root.parent/'audit.hpp').write_text(s)

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('version',choices=['C','D']);a=p.parse_args()
 print(json.dumps(Overlay(a.root).apply(a.version),indent=2))
