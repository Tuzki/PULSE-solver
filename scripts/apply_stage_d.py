#!/usr/bin/env python3
"""Install the complete Stage-D *proposed integration* over pinned Stage-C sources.

Runtime-wide, topology-independent changes: frozen indices, reusable binding
workspaces, shared modal Taylor anchor, bitwise-key archive dedup, tests.
Requires a complete original Stage-C checkout to apply. Transactional edits:
all anchors are checked in memory before any file is written.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import stage_d_baseline_transforms as foundation

BASE_SHA='fa2bc5ee4aab588ee91fb5b0513c692493799f7e'
OLD_FILES=[
  'include/pulse/core.hpp','src/semantics.cpp','src/descriptor.cpp',
  'src/engineering_flow.cpp','src/pevt.cpp','src/runtime.cpp','CMakeLists.txt'
]
NEW_FILES=['include/pulse/stage_d_runtime.hpp','tests/stage_d_runtime.cpp',
           'tests/stage_d_integration.cpp']

def one(s,before,after,label):
    n=s.count(before)
    if n!=1:
        raise ValueError(f'{label}: anchor occurrence {n}, expected 1')
    return s.replace(before,after,1)

def between(s,start,end,replacement,label):
    n=s.count(start);m=s.count(end)
    if n!=1 or m!=1:
        raise ValueError(f'{label}: start={n} end={m}, expected 1 each')
    a=s.index(start);b=s.index(end,a)+len(end)
    return s[:a]+replacement+s[b:]

def transform(input_files):
    stage_c={name:body for name,body in input_files.items() if name in foundation.REQUIRED_FILES}
    files=foundation.transform(stage_c)
    files['CMakeLists.txt']=input_files['CMakeLists.txt'].replace('\r\n','\n')

    s=files['include/pulse/core.hpp']
    s=one(s,'  uint64_t projections = 0;\n',
          '  uint64_t stage_d_rebound_hits=0, stage_d_rebound_misses=0;\n'
          '  uint64_t projections = 0;\n',
          'bounded dynamic rebound counters')
    files['include/pulse/core.hpp']=s

    # D1: Static index already compiled by foundation; replace transient node
    # tables with lookup-only hash tables (nothing depends on iteration order).
    s=files['src/descriptor.cpp']
    s=one(s,'#include <sstream>\n','#include <sstream>\n#include <unordered_map>\n#include <unordered_set>\n','bind hash-table headers')
    s=one(s,'    std::map<std::string, double> memo;\n    std::set<std::string> visiting;\n',
          '    std::unordered_map<std::string, double> memo;\n    std::unordered_set<std::string> visiting;\n',
          'held-expression runtime hash tables')

    # Classification-only reconstruction bounds are never read on an accepted
    # entry: do not allocate/calculate them for that case. The original matrix
    # expressions are preserved for region classification and fallback paths.
    s=one(s,
        '                       const std::map<int,bool>&bits,const std::map<int,int>&segments){\n'
        '    Mode mode=stored;if(!stored.observer_binding)return mode;',
        '                       const std::map<int,bool>&bits,const std::map<int,int>&segments,\n'
        '                       bool classification_only){\n'
        '    Mode mode=stored;if(!stored.observer_binding)return mode;',
        'bind classify parameter')
    s=one(s,'Mode bound=bind_observations(m,*it->second,regs,bits,segments);',
          'Mode bound=bind_observations(m,*it->second,regs,bits,segments,classification_only);',
          'bind classify call')
    start='    Matrix &scale=scratch.scale;\n'
    stop='    mode.candidate_roundoff_scale=std::make_shared<const Matrix>(std::move(scale));'
    n=s.count(start);m=s.count(stop)
    if n!=1 or m!=1:raise ValueError('bind conditional rounding buffer missing')
    a=s.index(start);b=s.index(stop,a)+len(stop)
    # Retain scratch instead of moving away and reallocating on next call.
    block=s[a:b].replace('std::make_shared<const Matrix>(std::move(scale))',
                           'std::make_shared<const Matrix>(scale)')
    s=s[:a] + '    if(classification_only) {\n' + block + '\n    } else {\n      // Floating reference rows remain checked for accepted entries.\n      for(size_t j=0;j<m.floating_references.size();++j)\n        mode.binding.edit().residual_map.row(na+j)=\n            N.row(m.nodes.at(m.floating_references[j]));\n      mode.candidate_roundoff_scale.reset();\n    }' + s[b:]
    # The original cache keys deliberately omit independent observation-only
    # REG values. Stage C therefore rebinds even when the COMPLETE dynamic
    # input tuple (and all modal conditions) matches a recent bound instance.
    # A second bounded exact-key cache stores immutable bound templates.
    # Entry-dependent checks are still executed by instantiate_cached EVERY
    # time; no previous physical state or acceptance is cached.
    s=one(s,
        '    std::deque<std::string> insertion_order;\n',
        '    std::deque<std::string> insertion_order;\n'
        '    std::map<std::string,std::shared_ptr<const Mode>> rebound_entries;\n'
        '    std::deque<std::string> rebound_order;\n'
        '    size_t rebound_capacity=512;\n',
        'Stage-D bounded rebound cache members')
    source='        if (it != cache->entries.end()) {\n            Mode bound=bind_observations(m,*it->second,regs,bits,segments,classification_only);\n            Mode mode = instantiate_cached(m, std::move(bound), s, classification_only);\n            ++stats.cache_hits;\n            return mode;\n        }'
    replacement='        if (it != cache->entries.end()) {\n            if(it->second->observer_binding) {\n                const std::string full_key=candidate_key(bits,segments,regs);\n                if(auto hit=cache->rebound_entries.find(full_key);\n                   hit!=cache->rebound_entries.end()) {\n                    ++stats.stage_d_rebound_hits;\n                    Mode mode=instantiate_cached(m,*hit->second,s,classification_only);\n                    ++stats.cache_hits;\n                    return mode;\n                }\n                ++stats.stage_d_rebound_misses;\n                // Construct a classification-capable template exactly once\n                // per full dynamic key. Accepted-entry checks still run below.\n                Mode bound=bind_observations(m,*it->second,regs,bits,segments,true);\n                if(cache->rebound_entries.size()>=cache->rebound_capacity) {\n                    cache->rebound_entries.erase(cache->rebound_order.front());\n                    cache->rebound_order.pop_front();\n                }\n                cache->rebound_entries.emplace(full_key,std::make_shared<const Mode>(bound));\n                cache->rebound_order.push_back(full_key);\n                Mode mode=instantiate_cached(m,std::move(bound),s,classification_only);\n                ++stats.cache_hits;\n                return mode;\n            }\n            Mode mode=instantiate_cached(m,*it->second,s,classification_only);\n            ++stats.cache_hits;\n            return mode;\n        }'
    s=one(s,source,replacement,'Stage-D exact dynamic rebound cache')
    files['src/descriptor.cpp']=s

    # D2: Every observable of a continuous trajectory shares one 24th-order
    # long-double Taylor state. Scalar projected coefficients remain per-row.
    # This avoids repeated matrix*vector 24-step recurrences for each projection.
    s=files['src/engineering_flow.cpp']
    s=one(s,'#include "pulse/engineering.hpp"\n',
          '#include "pulse/engineering.hpp"\n#include "pulse/stage_d_runtime.hpp"\n',
          'Flow stage-D helpers include')
    s=one(s,'struct FlowData {',
          'struct SharedLocalTaylor {\n'
          '  using WideVector=Eigen::Matrix<long double,Eigen::Dynamic,1>;\n'
          '  std::vector<WideVector> states,absolute_states;\n'
          '  bool ready=false;\n'
          '};\nstruct FlowData {',
          'shared Taylor type')
    s=one(s,
          '  mutable std::map<std::string,std::shared_ptr<FlowData>> observable_cache;\n',
          '  struct ObservableEntry { Vector row; std::shared_ptr<FlowData> flow; };\n'
          '  mutable std::unordered_map<std::uint64_t,std::vector<ObservableEntry>> observable_cache;\n',
          'binary-row projected Flow cache')
    s=one(s,
          '  mutable std::vector<Eigen::Matrix<long double, Eigen::Dynamic, 1>> local_state;\n',
          '  mutable std::shared_ptr<SharedLocalTaylor> shared_local;\n',
          'shared local state field')
    # Exact same long-double recurrence, calculated once. Before using shared
    # states, verify basis/anchor/rate identity; no global/static sharing.
    local_start='void prepare_local(FlowData &d) {'
    local_end='  d.local_ready = true;\n}'
    new_local='''void prepare_local(FlowData &d) {
  if (d.local_ready) return;
  using Wide = long double;
  using WMatrix = Eigen::Matrix<Wide, Eigen::Dynamic, Eigen::Dynamic>;
  using WVector = Eigen::Matrix<Wide, Eigen::Dynamic, 1>;
  if (!d.shared_local) d.shared_local=std::make_shared<SharedLocalTaylor>();
  auto &anchor=*d.shared_local;
  const auto &b=*d.basis;
  const int n=int(b.generator.rows())-1;
  if(!anchor.ready) {
    WVector z=WVector::Ones(n+1);
    if(n)z.head(n)=(b.reduce.cast<Wide>()*d.initial.cast<Wide>())
        .cwiseQuotient(b.scaling.head(n).cast<Wide>());
    WMatrix a=b.balanced.cast<Wide>()/Wide(d.local_rate);
    WVector absolute_z=z.cwiseAbs();
    anchor.states.resize(FlowData::local_degree+1);
    anchor.absolute_states.resize(FlowData::local_degree+1);
    anchor.states[0]=z;
    anchor.absolute_states[0]=absolute_z;
    for (int j=1;j<=FlowData::local_degree;++j) {
      z=(a*z/Wide(j)).eval();
      absolute_z=(a.cwiseAbs()*absolute_z/Wide(j)).eval();
      anchor.states[j]=z;
      anchor.absolute_states[j]=absolute_z;
    }
    anchor.ready=true;
  }
  std::vector<WVector> projected;
  const auto &guards=d.mode.binding.read().guards;
  projected.reserve(guards.size());
  d.local.resize(guards.size());
  d.local_absolute.resize(guards.size());
  d.local_scale.resize(guards.size());
  const auto &z=anchor.states[0];
  for(size_t k=0;k<guards.size();++k) {
    const auto &g=guards[k];
    WVector p=WVector::Zero(n+1);
    if(n) p.head(n)=(b.lift.cast<Wide>().transpose()*
       g.row.head(d.initial.size()-1).cast<Wide>())
       .cwiseProduct(b.scaling.head(n).cast<Wide>());
    projected.push_back(p);
    d.local[k][0]=Wide(g.row.dot(d.initial));
    d.local_absolute[k][0]=g.row.cast<Wide>().cwiseAbs()
        .dot(d.initial.cast<Wide>().cwiseAbs());
    d.local_scale[k]=p.cwiseAbs().sum()*z.cwiseAbs().maxCoeff();
  }
  for(int j=1;j<=FlowData::local_degree;++j)
    for(size_t k=0;k<projected.size();++k) {
      d.local[k][j]=projected[k].dot(anchor.states[j]);
      d.local_absolute[k][j]=projected[k].cwiseAbs()
          .dot(anchor.absolute_states[j]);
    }
  d.local_ready=true;
}'''
    s=between(s,local_start,local_end,new_local,'shared-local prepare implementation')
    s=one(s,'d.local_state[j].head(n)','d.shared_local->states[j].head(n)',
          'Flow state Taylor access')
    s=one(s,'++flow_counts.reprojected;Flow next(m,data_->initial);next.offset_=offset_+Time::from(elapsed);next.data_->archive_origin_id=data_->archive_origin_id;return next;',
          '++flow_counts.reprojected;Flow next(m,data_->initial);\n'
          '  if(next.data_->basis==data_->basis && next.data_->local_rate==data_->local_rate)\n'
          '    next.data_->shared_local=data_->shared_local;\n'
          '  next.offset_=offset_+Time::from(elapsed);\n'
          '  next.data_->archive_origin_id=data_->archive_origin_id;return next;',
          'Flow continuation share anchor')
    # Only the Flow projection's single guard depends on a row; no giant Mode
    # is copied. Full row bits are compared even when hashes collide.
    observe_start='  std::string id(reinterpret_cast<const char*>(row.data()),size_t(row.size())*sizeof(double));\n'
    observe_stop='  return projection.value(0,t,derivative);'
    observe='''  const auto id=stage_d::hash_bytes(row.data(),size_t(row.size())*sizeof(double));
  std::shared_ptr<FlowData> projected;
  const auto hit=data_->observable_cache.find(id);
  if(hit!=data_->observable_cache.end())
    for(const auto &entry:hit->second)
      if(entry.row.size()==row.size() &&
         stage_d::bitwise_equal(entry.row.data(),row.data(),size_t(row.size()))) {
        projected=entry.flow; break;
      }
  if(!projected) {
    Mode view;
    view.definition=data_->mode.definition;
    view.numerical_strategy=data_->mode.numerical_strategy;
    view.binding.edit().guards.push_back({row,0,1,"OBSERVE"});
    Flow projection(view,data_->initial);
    require(projection.data_->basis==data_->basis &&
            projection.data_->local_rate==data_->local_rate,12,
            "FLOW_SHARED_ANCHOR","observable projection has differing propagation basis");
    if(!data_->shared_local)
      data_->shared_local=std::make_shared<SharedLocalTaylor>();
    projection.data_->shared_local=data_->shared_local;
    projected=projection.data_;
    data_->observable_cache[id].push_back({row,projected});
  }
  Flow projection=*this;
  projection.data_=std::move(projected);
  return projection.value(0,t,derivative);'''
    s=between(s,observe_start,observe_stop,observe,'row-bit cache and shared projection')
    files['src/engineering_flow.cpp']=s

    # D3: Replace only lookup-key encodings, NOT PEVT byte format, identities,
    # ordering or serialization. All cache equality remains exact even after
    # a hash collision. This removes several short-lived Bytes/string keys per
    # event and uses reusable temporary word vectors.
    s=files['src/pevt.cpp']
    s=one(s,'#include "pulse/pevt.hpp"\n',
          '#include "pulse/pevt.hpp"\n#include "pulse/stage_d_runtime.hpp"\n',
          'PEVT typed cache include')
    s=one(s,
      '  std::unordered_map<std::string,uint32_t> component_ids,signal_ids,block_ids,value_ids,\n'
      '      definition_ids,instance_ids,state_ids,component_mode_ids;\n',
      '  std::unordered_map<std::string,uint32_t> component_ids,signal_ids,block_ids,definition_ids;\n'
      '  std::unordered_map<std::vector<uint64_t>,uint32_t,stage_d::WordVectorHash> value_word_ids,state_word_ids;\n'
      '  std::unordered_map<uint64_t,uint32_t> instance_pair_ids,component_mode_pair_ids;\n'
      '  std::vector<uint64_t> value_lookup,state_lookup;\n',
      'PEVT four typed caches')
    original_instance='''  uint32_t bind_instance(uint32_t definition,uint32_t values_id){
    Bytes b;put(b,definition,4);put(b,values_id,4);auto k=key(b);
    if(auto it=instance_ids.find(k);it!=instance_ids.end())return it->second;
    auto index=uint32_t(instances.size());instance_ids[k]=index;instances.push_back({definition,values_id});return index;
  }'''
    new_instance='''  uint32_t bind_instance(uint32_t definition,uint32_t values_id){
    const uint64_t key=stage_d::pair_key(definition,values_id);
    if(auto it=instance_pair_ids.find(key);it!=instance_pair_ids.end())return it->second;
    auto index=uint32_t(instances.size());
    instance_pair_ids.emplace(key,index);
    instances.push_back({definition,values_id});return index;
  }'''
    s=one(s,original_instance,new_instance,'typed archive instance key')
    original_modes='''      auto k=std::to_string(modal.component)+":"+std::to_string(value);auto it=component_mode_ids.find(k);
      if(it==component_mode_ids.end()) {
        auto id=uint32_t(component_modes.size());component_mode_ids[k]=id;'''
    new_modes='''      const uint64_t k=stage_d::pair_key(modal.component,uint32_t(value));
      auto it=component_mode_pair_ids.find(k);
      if(it==component_mode_pair_ids.end()) {
        auto id=uint32_t(component_modes.size());component_mode_pair_ids.emplace(k,id);'''
    s=one(s,original_modes,new_modes,'typed archive component-mode key')
    old_value='''  uint32_t value_set(const Mode&m) {
    std::vector<double> v;Bytes b;
    for(auto&name:slots){const auto&row=m.binding.read().maps.at(name);require(row.size()==Eigen::Index(nx),11,"PEVT_SHAPE","held value row differs");double value=row[row.size()-1];v.push_back(value);real(b,value);}
    auto k=key(b);if(auto it=value_ids.find(k);it!=value_ids.end())return it->second;auto id=uint32_t(values.size());value_ids[k]=id;values.push_back(std::move(v));return id;
  }'''
    new_value='''  uint32_t value_set(const Mode&m) {
    value_lookup.clear();
    for(const auto &name:slots){
      const auto &row=m.binding.read().maps.at(name);
      require(row.size()==Eigen::Index(nx),11,"PEVT_SHAPE","held value row differs");
      value_lookup.push_back(stage_d::double_bits(row[row.size()-1]));
    }
    if(auto it=value_word_ids.find(value_lookup);it!=value_word_ids.end())return it->second;
    const auto id=uint32_t(values.size());
    std::vector<double> v;v.reserve(value_lookup.size());
    for(uint64_t bits:value_lookup)v.push_back(std::bit_cast<double>(bits));
    value_word_ids.emplace(value_lookup,id);
    values.push_back(std::move(v));return id;
  }'''
    s=one(s,old_value,new_value,'typed archive value set')
    old_state='''  uint32_t state(const Vector&x,uint32_t vs) {
    require(size_t(x.size())==nx&&x.allFinite(),11,"PEVT_SHAPE","invalid event state");Bytes b;put(b,vs,4);for(Eigen::Index i=0;i<x.size();++i)real(b,x[i]);auto k=key(b);
    if(auto it=state_ids.find(k);it!=state_ids.end())return it->second;
    auto id=uint32_t(states.size());state_ids[k]=id;states.push_back({x,vs});return id;
  }'''
    new_state='''  uint32_t state(const Vector&x,uint32_t vs) {
    require(size_t(x.size())==nx&&x.allFinite(),11,"PEVT_SHAPE","invalid event state");
    state_lookup.clear();state_lookup.push_back(vs);
    for(Eigen::Index i=0;i<x.size();++i)state_lookup.push_back(stage_d::double_bits(x[i]));
    if(auto it=state_word_ids.find(state_lookup);it!=state_word_ids.end())return it->second;
    const auto id=uint32_t(states.size());
    state_word_ids.emplace(state_lookup,id);
    states.push_back({x,vs});return id;
  }'''
    s=one(s,old_state,new_state,'typed archive state key')
    s=one(s,'    meta["value_slot_count"]=slots.size();meta["modal_component_count"]=modals.size();\n',
          '    meta["value_slot_count"]=slots.size();meta["modal_component_count"]=modals.size();\n'
          '    value_lookup.reserve(slots.size());state_lookup.reserve(nx+1);\n',
          'archive lookup scratch reserve')
    files['src/pevt.cpp']=s

    s=input_files['src/runtime.cpp'].replace('\r\n','\n')
    s=one(s,'  out.report["flow_statistics"]=engineering::flow_statistics();\n',
          '  out.report["flow_statistics"]=engineering::flow_statistics();\n'
          '    out.report["stage_d_rebound_cache"]={{"hits",out.stats.stage_d_rebound_hits},\n'
          '        {"misses",out.stats.stage_d_rebound_misses}};\n',
          'D cache counters in report')
    files['src/runtime.cpp']=s

    # Tests use a topologically neutral helper, linked with the same C++20 flags.
    files['CMakeLists.txt']=files['CMakeLists.txt'].rstrip()+'''\n\nif(BUILD_TESTING)
  add_executable(stage_d_runtime_tests tests/stage_d_runtime.cpp)
  target_link_libraries(stage_d_runtime_tests PRIVATE pulse_core)
  add_test(NAME stage_d_runtime COMMAND stage_d_runtime_tests)
  add_executable(stage_d_integration_tests tests/stage_d_integration.cpp)
  target_link_libraries(stage_d_integration_tests PRIVATE pulse_core)
  add_test(NAME stage_d_integration COMMAND stage_d_integration_tests)
endif()
'''
    return files

def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--repo',type=Path,required=True)
    a.add_argument('--dry-run',action='store_true')
    a.add_argument('--allow-nonpinned',action='store_true',help='Only for a reviewed rebased Stage C checkout')
    a.add_argument('--manifest',type=Path)
    args=a.parse_args();repo=args.repo.resolve()
    for path in OLD_FILES:
      if not (repo/path).is_file():raise SystemExit(f'MISSING {repo/path}')
    for path in NEW_FILES:
      if (repo/path).exists():raise SystemExit(f'REFUSE to overwrite existing {repo/path}')
    if (repo/'.git').exists() and not args.allow_nonpinned:
      import subprocess
      head=subprocess.run(['git','-C',str(repo),'rev-parse','HEAD'],capture_output=True,text=True)
      if head.returncode or head.stdout.strip()!=BASE_SHA:
        raise SystemExit(f'Base HEAD differs from pinned {BASE_SHA}: {head.stdout.strip()}')
    before={p:(repo/p).read_text(encoding='utf-8') for p in OLD_FILES}
    try:after=transform(before)
    except ValueError as exc:raise SystemExit(f'STAGE D ANCHOR ERROR: {exc}')
    root=Path(__file__).resolve().parent.parent
    added={p:(root/p).read_text(encoding='utf-8') for p in NEW_FILES}
    audit={'base':BASE_SHA,'status':'DRY_RUN_VALIDATED_ANCHORS' if args.dry_run else 'PATCH_WRITTEN_UNCOMPILED',
           'modified_files':{},'added_files':list(added),'schema':'stage-d-full-source-20261104'}
    for p in OLD_FILES:
      n=before[p].replace('\r\n','\n')
      audit['modified_files'][p]={'before_sha256':hashlib.sha256(n.encode()).hexdigest(),
       'after_sha256':hashlib.sha256(after[p].encode()).hexdigest(),
       'modified':n!=after[p]}
      if not audit['modified_files'][p]['modified']:
         raise SystemExit(f'No modification detected in {p}')
    if not args.dry_run:
      # All transformations have succeeded; write all files.
      for p,text in after.items(): (repo/p).write_text(text,encoding='utf-8',newline='\n')
      for p,text in added.items():
         dest=repo/p;dest.parent.mkdir(parents=True,exist_ok=True)
         dest.write_text(text,encoding='utf-8',newline='\n')
    if args.manifest:
      args.manifest.parent.mkdir(parents=True,exist_ok=True)
      args.manifest.write_text(json.dumps(audit,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(audit,indent=2))

if __name__=='__main__':main()
