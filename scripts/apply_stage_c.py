#!/usr/bin/env python3
"""Apply Stage C1 event-kernel source changes to pinned PULSE B+COW commit.

No repository network or nondeterministic match heuristics. Every before-anchor
must occur exactly once. Prepares all files before writing any replacement.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import pathlib
import subprocess
import sys

COMMIT = '44207f2e863db73b234a1e778f72838ffe1b5e13'
BLOBS = {
  'src/runtime.cpp': '9191a238f4bbe39b587ad7d115e671e884695f32',
  'include/pulse/software.hpp': None,
  'src/software.cpp': None,
  'src/engineering_flow.cpp': '05d7ec67edea3e037e2818d041b736fedfa70ded',
  'src/pevt.cpp': 'f533c9fdeb71362e1424c57486ec5932109cc9d6',
  'CMakeLists.txt':'9e26bd0ab38e892d0893cb1ba3b6d4f2f97a6ab1',
}
ROOT = pathlib.Path(__file__).resolve().parent.parent

def replace_once(content: str, old: str, new: str, path: str, label: str) -> str:
    n = content.count(old)
    if n != 1:
        raise RuntimeError(f'{path}: {label}: expected one source anchor, got {n}')
    return content.replace(old, new, 1)

def build_patches():
    rt=[]
    def rr(label,old,new): rt.append((label,old,new))
    rr('include header', '#include "pulse/core.hpp"\n',
       '#include "pulse/core.hpp"\n#include "pulse/event_kernel.hpp"\n')
    rr('valid generation single lookup',
'''bool valid(const RunState &s, const Agenda &a) {
  auto i = s.generations.read().find(a.part);
  return a.generation == (i == s.generations.read().end() ? 0 : i->second);
}''',
'''bool valid(const RunState &s, const Agenda &a) {
  const auto& generations=s.generations.read();
  const auto i=generations.find(a.part);
  return a.generation==(i==generations.end()?0:i->second);
}''')
    rr('prune only detach if invalid',
'''void prune(RunState &s) {
  std::erase_if(s.agenda.edit(), [&](auto &a) { return !valid(s, a); });
}''',
'''void prune(RunState &s) {
  // Removing invalidated entries cannot introduce a deadline-origin conflict.
  // Avoid detaching a shared COW queue on the common no-op path.
  const auto& pending=s.agenda.read();
  if (std::none_of(pending.begin(),pending.end(),[&](const Agenda& a){return !valid(s,a);})) return;
  std::erase_if(s.agenda.edit(), [&](auto &a) { return !valid(s, a); });
}''')
    rr('remove old textual fingerprint',
'''std::string fingerprint(const RunState &s, const std::set<std::string> &trig) {
  std::ostringstream x;
  x << std::setprecision(17) << s.mode.id;
  for (auto &t : trig)
    x << "!" << t;
  for (const auto &[name, state] : s.software.read()) {
    x << "$" << name << ":" << state.invocation << ":";
    for (auto byte : state.bytes) x << unsigned(byte) << ",";
  }
  std::vector<std::string> pending;
  for (const auto &a : s.agenda.read())
    if (valid(s, a))
      pending.push_back(a.at.canonical() + ":" + a.trigger + ":" + a.origin);
  std::sort(pending.begin(), pending.end());
  for (auto &a : pending)
    x << "@" << a;
  return x.str();
}''','')
    rr('remove old edge decoder',
'''std::set<std::string> edges(const Model &m, const Mode &before,
                            const Mode &after) {
  std::set<std::string> result;
  for (int i : m.events) {
    const auto &p = m.parts[i].raw;
    if (op(p, "MODE") != "EDGE")
      continue;
    auto source = net_name(op(p, "SOURCE"));
    bool a = before.bools.at(source), b = after.bools.at(source);
    auto direction = op(p, "EDGE");
    if (a != b && (direction == "BOTH" || (direction == "RISE" && b) ||
                   (direction == "FALL" && !b)))
      result.insert(net_name(p.args[0]));
  }
  return result;
}''','')
    rr('closure receives compiled plan',
       'void closure(const Model &m, RunState &candidate,',
       'void closure(const Model &m, const EventKernel& kernel, RunState &candidate,')
    rr('cycle key preserved', 'fingerprint(candidate, triggers)', 'event_fingerprint(candidate, triggers)')
    rr('COW register staging',
       '    auto newregs = snap.regs.read();\n',
       '    auto newregs = snap.regs; // O(1) snapshot until first register/software write\n')
    rr('register command loop',
'''    for (int i : m.registers) {
      const auto &p = m.parts[i].raw;
      auto name = net_name(p.args[0]);
      if (m.software_outputs.count(name)) continue;
      if (op(p, "MODE") == "SR") {
        bool set = triggers.count(net_name(op(p, "SET"))),
             reset = triggers.count(net_name(op(p, "RESET")));
        if (set || reset)
          newregs[name] = set && reset ? (op(p, "PRIORITY") == "SET") : set;
      } else if (triggers.count(net_name(p.args[2])))
        newregs[name] = snapshot(snap, p.args[1]);
    }''',
'''    // Rules remain in the original Model.registers order. The trigger and
    // lvalue names were canonicalized once, not on every microstep.
    for (const auto& rule:kernel.registers()) {
      if (rule.kind==EventKernel::RegisterRule::Kind::SetReset) {
        const bool set=triggers.count(rule.set)!=0, reset=triggers.count(rule.reset)!=0;
        if (set||reset)
          newregs.edit()[rule.name]=set&&reset?rule.set_priority:set;
      } else if (triggers.count(rule.clock))
        newregs.edit()[rule.name]=snapshot(snap,rule.expression);
    }''')
    rr('cancel loop',
'''    for (int i : m.events) {
      const auto &p = m.parts[i].raw;
      if (op(p, "MODE") == "DELAY" && p.options.count("CANCEL") &&
          triggers.count(net_name(op(p, "CANCEL"))))
        ++candidate.generations.edit()[i];
    }''',
'''    bool agenda_validity_changed=false;
    for (const auto& rule:kernel.delays())
      if (rule.has_cancel&&triggers.count(rule.cancel)) {
        ++candidate.generations.edit()[rule.part];
        agenda_validity_changed=true;
      }''')
    rr('delay schedule loop',
'''    for (int i : m.events) {
      const auto &p = m.parts[i].raw;
      if (op(p, "MODE") != "DELAY" ||
          !triggers.count(net_name(op(p, "SOURCE"))))
        continue;
      double delay = p.options.count("DELAY_INPUT")
                         ? snapshot(snap, op(p, "DELAY_INPUT"))
                         : number(op(p, "DELAY"));
      require(delay >= 0 && std::isfinite(delay), 7, "INVALID_DELAY",
              "latched delay is negative or nonfinite", false, p.source);
      if (op(p, "POLICY", "TRANSPORT") == "REPLACE")
        ++candidate.generations.edit()[i];
      auto trigger = net_name(p.args[0]);
      if (delay == 0)
        next.insert(trigger);
      else
        candidate.agenda.edit().push_back(
            {candidate.at + Time::from(delay), i, 0, candidate.generations.edit()[i],
             trigger,
             sum_origin(
                 candidate.time_origin,
                 p.options.count("DELAY_INPUT")
                     ? exact_time_origin(Time::from(delay))
                     : time_input(p.option_text.at("DELAY"), m.netlist))});
    }''',
'''    bool deadline_added=false;
    for (const auto& rule:kernel.delays()) {
      if (!triggers.count(rule.source)) continue;
      const auto& p=m.parts[rule.part].raw;
      const double delay=rule.has_delay_input
          ? snapshot(snap,rule.delay_input) : number(rule.delay_literal);
      require(delay >= 0 && std::isfinite(delay), 7, "INVALID_DELAY",
              "latched delay is negative or nonfinite", false, p.source);
      if (rule.replace) {
        ++candidate.generations.edit()[rule.part];
        agenda_validity_changed=true;
      }
      if (delay == 0) next.insert(rule.trigger);
      else {
        candidate.agenda.edit().push_back(
            {candidate.at + Time::from(delay), rule.part, 0,
             candidate.generations.edit()[rule.part],rule.trigger,
             sum_origin(candidate.time_origin,
                rule.has_delay_input ? exact_time_origin(Time::from(delay)) :
                                       time_input(p.option_text.at("DELAY"),m.netlist))});
        deadline_added=true;
      }
    }''')
    rr('software wakeup sets validation flag',
'''        candidate.agenda.edit().push_back({candidate.at + delay, wake.part, 0, 0, wake.trigger,
                                    sum_origin(candidate.time_origin, exact_time_origin(delay))});
      }
    }
    check_agenda_origins(m, candidate);''',
'''        candidate.agenda.edit().push_back({candidate.at + delay, wake.part, 0, 0, wake.trigger,
                                    sum_origin(candidate.time_origin, exact_time_origin(delay))});
        deadline_added=true;
      }
    }
    // Reuse validation only when the valid agenda is unchanged. Invalidation
    // can expose adjacent known origins previously separated by an unproven
    // origin, so cancellation and REPLACE also require the original check.
    if(deadline_added || agenda_validity_changed) check_agenda_origins(m, candidate);''')
    rr('new edges compiled',
       '    auto newedges = edges(m, snap.mode, candidate.mode);',
       '    auto newedges = kernel.changed_edges(snap.mode, candidate.mode);')
    rr('construct runtime event kernel once',
       '    Time end = Time::from(out.t_end);\n    RunState state;',
       '    Time end = Time::from(out.t_end);\n    const EventKernel kernel(m);\n    RunState state;')
    rr('prepare periodic cache lazily and once per active rule',
       '    const EventKernel kernel(m);\n    RunState state;',
       '''    const EventKernel kernel(m);
    // A periodic rule can be inactive; defer conversion until its first due
    // event, retaining the original error timing for unused rules.
    struct PreparedPeriod {
      Time start, period;
      std::string start_origin, period_origin;
    };
    std::map<int,PreparedPeriod> prepared_periodic;
    RunState state;''')
    rr('periodic precompiled lookup',
'''          const auto &p = m.parts[a.part].raw;
          if (op(p, "MODE") == "PERIODIC") {
            auto cycle = a.cycle + 1;
            remaining.push_back(
                {Time::from(number(op(p, "START", "0"))) +
                     Time::from(number(op(p, "PERIOD"))).times(cycle),
                 a.part, cycle, 0, a.trigger,
                 sum_origin(time_input(p.option_text.count("START")
                                           ? p.option_text.at("START")
                                           : "0",
                                       m.netlist),
                            time_input(p.option_text.at("PERIOD"), m.netlist),
                            cycle)});
          }''',
'''          if (const auto* periodic=kernel.periodic(a.part)) {
            auto cycle = a.cycle + 1;
            auto found=prepared_periodic.find(a.part);
            if(found==prepared_periodic.end()){
              // The original conversion and parameter-resolution routines are
              // unchanged. Time+origin values are immutable per frozen Model.
              PreparedPeriod prepared;
              prepared.start=Time::from(number(periodic->start_literal));
              prepared.period=Time::from(number(periodic->period_literal));
              prepared.start_origin=time_input(periodic->start_origin,m.netlist);
              prepared.period_origin=time_input(m.parts[a.part].raw.option_text.at("PERIOD"),m.netlist);
              found=prepared_periodic.emplace(a.part,std::move(prepared)).first;
            }
            const auto& p=found->second;
            remaining.push_back(
                {p.start+p.period.times(cycle),
                 a.part, cycle, 0, a.trigger,
                 sum_origin(p.start_origin,p.period_origin,cycle)});
          }''')
    rr('closure call gets plan',
       '       closure(m, candidate, std::move(triggers), crossings, seeds, out, o, logs,',
       '       closure(m, kernel, candidate, std::move(triggers), crossings, seeds, out, o, logs,')

    head=[]
    head.append(('COW execute overload',
'''  std::vector<Wakeup> execute(const RunState &snapshot, RunState &candidate,
       const std::set<std::string> &triggers, std::map<std::string,double> &writes,
       std::vector<Json> &logs, uint64_t transaction, size_t delta);''',
'''  std::vector<Wakeup> execute(const RunState &snapshot, RunState &candidate,
       const std::set<std::string> &triggers, std::map<std::string,double> &writes,
       std::vector<Json> &logs, uint64_t transaction, size_t delta);
  // COW-aware variant: no register-map copy if no task actually executes.
  std::vector<Wakeup> execute(const RunState &snapshot, RunState &candidate,
       const std::set<std::string> &triggers,
       CowValue<std::map<std::string,double>> &writes,
       std::vector<Json> &logs, uint64_t transaction, size_t delta);'''))
    sw=[]
    sw.append(('implement COW execute overload',
'''Json Session::identity()const{return data_->identity;}''',
'''std::vector<Wakeup> Session::execute(const RunState&snapshot,RunState&candidate,
 const std::set<std::string>&triggers,CowValue<std::map<std::string,double>>&writes,
 std::vector<Json>&logs,uint64_t tx,size_t delta) {
  std::vector<Wakeup>w;
  for(auto &t:data_->tasks) {
    uint32_t flags=0;
    if(triggers.count(t.spec->trigger)&&!t.spec->self_trigger)flags|=PULSE_SW_EXTERNAL;
    if(triggers.count(t.spec->wake_trigger))flags|=PULSE_SW_WAKEUP;
    if(flags)data_->call(t,snapshot,candidate,writes.edit(),false,w,&logs,tx,delta,flags);
  }
  return w;
}
Json Session::identity()const{return data_->identity;}'''))
    cm=[]
    cm.append(('link event kernel implementation',
''' src/propagate.cpp src/runtime.cpp src/engineering_flow.cpp src/engineering_mode.cpp''',
''' src/propagate.cpp src/runtime.cpp src/event_kernel.cpp src/engineering_flow.cpp src/engineering_mode.cpp'''))
    cm.append(('add real kernel CTest',
''' add_test(NAME cow_value COMMAND cow_value_tests)
endif()''',
''' add_test(NAME cow_value COMMAND cow_value_tests)
endif()

if(BUILD_TESTING)
 add_executable(stage_c_event_kernel_tests tests/stage_c_event_kernel.cpp)
 target_link_libraries(stage_c_event_kernel_tests PRIVATE pulse_core)
 add_test(NAME stage_c_event_kernel COMMAND stage_c_event_kernel_tests)
endif()'''))
    flow=[]
    flow.append(('header deque for pinned COW basis cache',
'''#include <cstring>
#include <functional>''',
'''#include <cstring>
#include <deque>
#include <functional>'''))
    flow.append(('identity shortcut for prepared eigenbasis',
'''std::shared_ptr<Basis> basis(const Mode &mode) {
  static thread_local std::unordered_map<std::string, std::shared_ptr<Basis>> cache;
  auto id = key(mode);
  if (auto it = cache.find(id); it != cache.end()) { ++flow_counts.basis_hits; return it->second; }''',
'''std::shared_ptr<Basis> basis(const Mode &mode) {
  static thread_local std::unordered_map<std::string, std::shared_ptr<Basis>> cache;
  // Pointer identity is safe only while the exact COW storage is retained.
  // Pin at most 128 definitions; any subsequent Mode::definition.edit()
  // detaches, making the old pointer-key result immutable.
  struct IdentityBasis {
    CowValue<ModeDefinition> owner;
    std::shared_ptr<Basis> prepared;
  };
  static thread_local std::unordered_map<const ModeDefinition*,IdentityBasis> by_identity;
  static thread_local std::deque<const ModeDefinition*> identity_order;
  const auto* identity=std::addressof(mode.definition.read());
  if(auto it=by_identity.find(identity);it!=by_identity.end()) {
    ++flow_counts.basis_hits;
    return it->second.prepared;
  }
  const auto remember_identity=[&](const std::shared_ptr<Basis>& b) {
    if(by_identity.size()>=128){
      by_identity.erase(identity_order.front());
      identity_order.pop_front();
    }
    identity_order.push_back(identity);
    by_identity.emplace(identity,IdentityBasis{mode.definition,b});
  };
  auto id = key(mode);
  if (auto it = cache.find(id); it != cache.end()) {
    ++flow_counts.basis_hits;
    remember_identity(it->second);
    return it->second;
  }'''))
    flow.append(('memoize computed basis identity on cache insertion',
'''  cache.emplace(std::move(id), b);
  return b;
}''',
'''  cache.emplace(std::move(id), b);
  remember_identity(b);
  return b;
}'''))
    flow.append(('skip physically identical static matrices in Flow compatibility',
'''  if(m.numerical_strategy!=old.numerical_strategy||
     !same_key_matrix(m.definition.read().M,old.definition.read().M)||
     !same_key_matrix(m.definition.read().invariant_lift,old.definition.read().invariant_lift)||
     !same_key_matrix(m.definition.read().invariant_generator,old.definition.read().invariant_generator)||
     !same_key_matrix(m.definition.read().invariant_reduce,old.definition.read().invariant_reduce)||
     m.segments!=old.segments||''',
'''  // Shared COW definitions have identical bytes. Other Mode fields are
  // still verified by the original compatibility rules below.
  const bool distinct_definition=!m.definition.shares_storage_with(old.definition);
  if(m.numerical_strategy!=old.numerical_strategy||
     (distinct_definition&&
       (!same_key_matrix(m.definition.read().M,old.definition.read().M)||
        !same_key_matrix(m.definition.read().invariant_lift,old.definition.read().invariant_lift)||
        !same_key_matrix(m.definition.read().invariant_generator,old.definition.read().invariant_generator)||
        !same_key_matrix(m.definition.read().invariant_reduce,old.definition.read().invariant_reduce)))||
     m.segments!=old.segments||'''))
    pevt=[]
    pevt.append(('skip redundant immutable PEVT matrices after COW comparison',
'''    if(!identical(a.definition.read().M,b.definition.read().M) || !identical(a.binding.read().observations,b.binding.read().observations) ||
       !identical(a.definition.read().constraints,b.definition.read().constraints) ||
       !identical(a.binding.read().residual_map,b.binding.read().residual_map) ||
       !same_reference(a,b) ||
       !identical(a.definition.read().invariant_lift,b.definition.read().invariant_lift) ||
       !identical(a.definition.read().invariant_generator,b.definition.read().invariant_generator) ||
       !identical(a.definition.read().invariant_reduce,b.definition.read().invariant_reduce))return false;''',
'''    // Only skip byte-identical comparisons when COW storage is literally
    // shared. Dynamic observer validation remains mandatory.
    const bool distinct_definition=!a.definition.shares_storage_with(b.definition);
    const bool distinct_binding=!a.binding.shares_storage_with(b.binding);
    if((distinct_definition &&
        (!identical(a.definition.read().M,b.definition.read().M) ||
         !identical(a.definition.read().constraints,b.definition.read().constraints) ||
         !identical(a.definition.read().invariant_lift,b.definition.read().invariant_lift) ||
         !identical(a.definition.read().invariant_generator,b.definition.read().invariant_generator) ||
         !identical(a.definition.read().invariant_reduce,b.definition.read().invariant_reduce))) ||
       (distinct_binding &&
        (!identical(a.binding.read().observations,b.binding.read().observations) ||
         !identical(a.binding.read().residual_map,b.binding.read().residual_map))) ||
       !same_reference(a,b))return false;'''))
    pevt.append(('skip duplicate PEVT maps and guard comparisons on shared binding',
'''    auto x=a.binding.read().maps.begin(), y=b.binding.read().maps.begin();
    for(;x!=a.binding.read().maps.end();++x,++y)
      if(x->first!=y->first)return false;
      else if(a.observer_maps.count(x->first)){
        if(x->second.size()!=y->second.size()||!x->second.size()||std::memcmp(x->second.data(),y->second.data(),size_t(x->second.size()-1)*sizeof(double))!=0)return false;
      }else if(!identical(x->second,y->second))return false;
    for(size_t i=0;i<a.binding.read().guards.size();++i){
      const auto&g=a.binding.read().guards[i];const auto&h=b.binding.read().guards[i];
      if(g.part!=h.part || g.direction!=h.direction || g.kind!=h.kind ||
         g.knot!=h.knot || g.segment!=h.segment || g.step!=h.step ||
         !identical(g.row,h.row))return false;
    }''',
'''    if(distinct_binding){
      auto x=a.binding.read().maps.begin(), y=b.binding.read().maps.begin();
      for(;x!=a.binding.read().maps.end();++x,++y)
        if(x->first!=y->first)return false;
        else if(a.observer_maps.count(x->first)){
          if(x->second.size()!=y->second.size()||!x->second.size()||std::memcmp(x->second.data(),y->second.data(),size_t(x->second.size()-1)*sizeof(double))!=0)return false;
        }else if(!identical(x->second,y->second))return false;
      for(size_t i=0;i<a.binding.read().guards.size();++i){
        const auto&g=a.binding.read().guards[i];const auto&h=b.binding.read().guards[i];
        if(g.part!=h.part || g.direction!=h.direction || g.kind!=h.kind ||
           g.knot!=h.knot || g.segment!=h.segment || g.step!=h.step ||
           !identical(g.row,h.row))return false;
      }
    }'''))
    return {'src/runtime.cpp':rt,'include/pulse/software.hpp':head,'src/software.cpp':sw,'CMakeLists.txt':cm,'src/engineering_flow.cpp':flow,'src/pevt.cpp':pevt}

def subprocess_git(repo: pathlib.Path,*args:str)->str:
    result=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
    if result.returncode:raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('repo',type=pathlib.Path)
    p.add_argument('--in-place',action='store_true',help='write changes in the working tree')
    p.add_argument('--output-dir',type=pathlib.Path,help='export resulting complete modified source files')
    a=p.parse_args();repo=a.repo.resolve()
    if subprocess_git(repo,'rev-parse','HEAD')!=COMMIT:
        raise RuntimeError('Base commit must be pinned '+COMMIT)
    if subprocess_git(repo,'status','--porcelain'):
        raise RuntimeError('Working tree is not clean; use a new branch and commit/stash your changes')
    changes={}
    for name,patch_list in build_patches().items():
        path=repo/name
        if name in BLOBS and BLOBS[name]:
            actual=subprocess_git(repo,'hash-object','--',name)
            if actual!=BLOBS[name]:raise RuntimeError(f'{name}: unexpected Git blob {actual}')
        data=path.read_bytes();newline='\r\n' if b'\r\n' in data else '\n'
        result=data.decode('utf-8').replace('\r\n','\n')
        for label,old,new in patch_list:
            result=replace_once(result,old,new,name,label)
        changes[name]=result.replace('\n',newline).encode('utf-8')
    for name in ['include/pulse/event_kernel.hpp','src/event_kernel.cpp','tests/stage_c_event_kernel.cpp']:
        target=repo/name
        if target.exists():raise RuntimeError(f'{name} already exists; stop')
        changes[name]=(ROOT/name).read_bytes()
    if not a.in_place and not a.output_dir:
        p.error('Specify --in-place or --output-dir')
    if a.output_dir:
        dest=a.output_dir.resolve()
        if dest==repo:raise RuntimeError('Choose separate output-dir, not repository root')
        for name,data in changes.items():
            file=dest/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(data)
    if a.in_place:
        for name,data in changes.items():
            file=repo/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(data)
    manifest={'base_commit':COMMIT,'files':{name:{'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()} for name,data in changes.items()},'status':'SOURCE_GENERATED_ONLY_REQUIRES_FULL_BUILD_AND_REGRESSION'}
    if a.output_dir:(a.output_dir/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(manifest,indent=2))
if __name__=='__main__':
    try:main()
    except Exception as exc:print(f'ERROR: {exc}',file=sys.stderr);raise SystemExit(1)
