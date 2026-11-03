#!/usr/bin/env python3
"""Apply a fail-closed, idempotency-detecting Stage D.1 patch to PULSE.

Accepted input: Stage D b3906c7713f057a763536629b5d7873cb21d34e9
or an unmodified source descendant (such as audit/cd-runtime-repetition-20261104).

No network, commits, rebases, cleanups, or tool installation. The installer
checks *all* anchors before writing *any* file, and preserves line endings.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import pathlib
import subprocess
import sys

BASE = 'b3906c7713f057a763536629b5d7873cb21d34e9'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(root: pathlib.Path, *args: str) -> str:
    p=subprocess.run(['git','-C',str(root),*args],capture_output=True,text=True)
    if p.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed: {p.stderr.strip()}")
    return p.stdout.strip()


class Patch:
    def __init__(self,root: pathlib.Path):
        self.root=root
        self.data:dict[str,bytes]={}
        self.before:dict[str,bytes]={}
        self.operations:list[dict]=[]

    def load(self,path: str)->bytes:
        if path not in self.data:
            data=(self.root/path).read_bytes()
            self.before[path]=data
            self.data[path]=data
        return self.data[path]

    def replace(self,path: str, old: str, new: str, label: str):
        data=self.load(path)
        for newline in ('\r\n','\n'):
            orig=old.replace('\n',newline).encode('utf-8')
            updated=new.replace('\n',newline).encode('utf-8')
            count=data.count(orig)
            if count == 1:
                # A one-line anchor has no EOL fingerprint: use its actual
                # adjacent line ending, not the first attempted candidate.
                if '\n' not in old:
                    off=data.find(orig)+len(orig)
                    nl=data.find(b'\n',off)
                    actual='\r\n' if nl>=1 and data[nl-1:nl]==b'\r' else '\n'
                    updated=new.replace('\n',actual).encode('utf-8')
                self.data[path]=data.replace(orig,updated,1)
                self.operations.append({'path':path,'label':label})
                return
            if count > 1: raise RuntimeError(f'{path} ambiguous anchor {label}: {count} copies')
        raise RuntimeError(f'{path}: unexpected source at {label} (requires exact Stage D source)')

    def add(self,path: str,content:bytes):
        target=self.root/path
        if target.exists():
            raise RuntimeError(f'{path} already exists: refusing to overwrite')
        self.data[path]=content
        self.operations.append({'path':path,'label':'add'})

    def write(self,dry_run:bool):
        manifest={'base':BASE,'dry_run':dry_run,'changed_files':{},'operations':self.operations}
        for name,after in sorted(self.data.items()):
            before=self.before.get(name)
            if before==after: raise RuntimeError(f'{name}: empty patch')
            manifest['changed_files'][name]={'before_sha256':sha(before) if before is not None else None,
                                              'after_sha256':sha(after),'bytes':len(after)}
        if not dry_run:
            for name,after in self.data.items():
                dst=self.root/name;dst.parent.mkdir(parents=True,exist_ok=True)
                dst.write_bytes(after)
        return manifest


def patch(p: Patch, package_root:pathlib.Path)->None:
    # D.1a: Eigen Vector -> Matrix materialization in Flow::compatible.
    p.replace('src/engineering_flow.cpp',
        '  auto same=[](const Matrix&a,const Matrix&b){return a.rows()==b.rows()&&a.cols()==b.cols()&&(a.array()==b.array()).all();};',
        '  // Keep original coefficient-wise numerical equality (+0 == -0);\n'
        '  // template deduction avoids implicit Vector -> Matrix materialization.\n'
        '  auto same=[](const auto&a,const auto&b){return a.rows()==b.rows()&&a.cols()==b.cols()&&(a.array()==b.array()).all();};',
        'D1a nonallocating exact semantic comparison')

    # D.1c: A is an immutable component of the existing ObserverBinding.
    p.replace('include/pulse/core.hpp',
        'struct ObserverBinding {\n  Matrix A, N, B;\n  std::map<std::string,int> rows;\n};',
        'struct ObserverBinding {\n  Matrix A, N, B;\n'
        '  // A is static within this compiled binding; cache original-order\n'
        '  // lpNorm<1>() rows, never dynamic B or N norms.\n'
        '  Vector a_row_norm;\n  std::map<std::string,int> rows;\n};',
        'D1c immutable A row norms')
    p.replace('src/descriptor.cpp',
        '                    binding->B=m.floating_references.empty()?B:physical_B;binding->N=N;\n'
        '                    mode.observer_binding=binding;',
        '                    binding->B=m.floating_references.empty()?B:physical_B;binding->N=N;\n'
        '                    binding->a_row_norm.resize(binding->A.rows());\n'
        '                    for(int i=0;i<binding->A.rows();++i)\n'
        '                        binding->a_row_norm[i]=binding->A.row(i).lpNorm<1>();\n'
        '                    mode.observer_binding=binding;',
        'D1c populate once after A materialization')
    p.replace('src/descriptor.cpp',
        '        a_row_norm[size_t(i)]=binding.A.row(i).lpNorm<1>();\n'
        '        b_row_norm[size_t(i)]=B.row(i).lpNorm<1>();',
        '        // Fallback keeps manually assembled ObserverBinding instances\n'
        '        // equivalent; compiled bindings always have a cached A norm.\n'
        '        a_row_norm[size_t(i)]=binding.a_row_norm.size()==na\n'
        '            ?binding.a_row_norm[i]:binding.A.row(i).lpNorm<1>();\n'
        '        b_row_norm[size_t(i)]=B.row(i).lpNorm<1>();',
        'D1c use precomputed A norms (B remains dynamic)')

    # D.1b: scoped coordinate Binding reuse. This extends the EXISTING mode
    # cache, not a global/TLS lifecycle. Each entry owns its physical source
    # COW; source address can therefore never dangle or be reused while cached.
    p.replace('src/descriptor.cpp',
        '    size_t rebound_capacity=512;\n};',
        '    size_t rebound_capacity=512;\n'
        '    // Coordinate-adapted Binding is derived solely from the exact\n'
        '    // physical COW object and fixed chart L. Scoped to this Model.\n'
        '    struct CoordinateEntry {\n'
        '        CowValue<ModeBinding> physical, internal;\n'
        '        Matrix chart_l;\n'
        '    };\n'
        '    std::map<const ModeBinding*,CoordinateEntry,std::less<const ModeBinding*>> coordinate_entries;\n'
        '    std::deque<const ModeBinding*> coordinate_order;\n'
        '};',
        'D1b cache lifetime under existing ScopedModeCache')
    p.replace('include/pulse/solver_strategy.hpp',
        'Mode portfolio_compile(const Model &, const Vector &internal,',
        '// Internal: return immutable, chart-adapted observer Binding from the\n'
        '// current simulation-scoped exact-source cache (or materialize once).\n'
        'CowValue<ModeBinding> coordinate_bound_binding(const Model &,\n'
        '    const CowValue<ModeBinding> &, const Matrix &chart_l);\n'
        'Mode portfolio_compile(const Model &, const Vector &internal,',
        'D1b helper declaration (no new runtime module)')

    # Existing cache constructor/destructor anchors also show correct ownership.
    p.replace('src/descriptor.cpp',
        'ScopedModeCache::~ScopedModeCache() {\n    active_mode_cache = previous_;\n}\nMode settle(',
        '''ScopedModeCache::~ScopedModeCache() {
    active_mode_cache = previous_;
}
// No process-global cache: entries die with the simulation's ScopedModeCache.
// The physical COW is retained in every entry to keep its address unique;
// a caller's later edit() detaches and cannot corrupt cached equations.
CowValue<ModeBinding> coordinate_bound_binding(const Model &m,
                                                const CowValue<ModeBinding> &physical,
                                                const Matrix &L) {
    ModeCacheData *cache = active_mode_cache && active_mode_cache->model == &m &&
                                   active_mode_cache->capacity ? active_mode_cache : nullptr;
    const ModeBinding *const key = &physical.read();
    auto same_chart = [&](const Matrix &old) {
        return old.rows()==L.rows() && old.cols()==L.cols() &&
               (old.size()==0 || std::memcmp(old.data(),L.data(),
                                           size_t(old.size())*sizeof(double))==0);
    };
    if (cache) {
        const auto hit=cache->coordinate_entries.find(key);
        if (hit!=cache->coordinate_entries.end() && same_chart(hit->second.chart_l))
            return hit->second.internal;
    }
    CowValue<ModeBinding> internal=physical;
    auto &b=internal.edit(); // One detached materialization for this exact source.
    if(b.observations.cols()==L.rows())b.observations=b.observations*L;
    if(b.residual_map.rows())b.residual_map=b.residual_map*L;
    if(b.residual_reference.rows())b.residual_reference=b.residual_reference*L;
    for(auto &[name,row]:b.maps)row=L.transpose()*row;
    for(auto &guard:b.guards)guard.row=L.transpose()*guard.row;
    if (cache) {
        auto hit=cache->coordinate_entries.find(key);
        if(hit!=cache->coordinate_entries.end()) {
            hit->second.internal=internal;
            hit->second.chart_l=L;
        } else {
            if(cache->coordinate_entries.size()>=cache->rebound_capacity) {
                cache->coordinate_entries.erase(cache->coordinate_order.front());
                cache->coordinate_order.pop_front();
            }
            cache->coordinate_entries.emplace(key,
                ModeCacheData::CoordinateEntry{physical,internal,L});
            cache->coordinate_order.push_back(key);
        }
    }
    return internal;
}
Mode settle(''',
        'D1b scoped exact-source coordinate reuse')
    p.replace('src/descriptor.cpp',
        '#include <deque>\n#include <functional>',
        '#include <deque>\n#include <cstring>\n#include <functional>',
        'D1b std::memcmp include')

    # Substitute only Binding transformations; leave M, constraints, invariant
    # and candidate_roundoff_scale computation/physical validation untouched.
    p.replace('src/solver_strategy.cpp',
        '  if(mode.binding.read().observations.cols()==L.rows())mode.binding.edit().observations=mode.binding.read().observations*L;\n'
        '  if(mode.definition.read().constraints.rows())',
        '  if(mode.definition.read().constraints.rows())',
        'D1b remove per-call observations edit')
    p.replace('src/solver_strategy.cpp',
        '  if(mode.binding.read().residual_map.rows())mode.binding.edit().residual_map=mode.binding.read().residual_map*L;\n'
        '  if(mode.binding.read().residual_reference.rows())mode.binding.edit().residual_reference=mode.binding.read().residual_reference*L;\n'
        '  if(mode.definition.read().invariant_lift.rows())',
        '  if(mode.definition.read().invariant_lift.rows())',
        'D1b remove per-call residual Binding edits')
    p.replace('src/solver_strategy.cpp',
        '  for(auto&[name,row]:mode.binding.edit().maps)row=L.transpose()*row;\n'
        '  for(auto&guard:mode.binding.edit().guards)guard.row=L.transpose()*guard.row;\n'
        '  if(mode.candidate_roundoff_scale)',
        '  // A cache hit skips only repeated chart materialization. Original\n'
        '  // compile_specified() entry checks and all definition transforms ran.\n'
        '  mode.binding=coordinate_bound_binding(m,mode.binding,L);\n'
        '  if(mode.candidate_roundoff_scale)',
        'D1b replace repeated Binding coordinate edits')

    test=(package_root/'tests/stage_d1_regression.cpp').read_bytes()
    p.add('tests/stage_d1_regression.cpp',test)
    p.replace('CMakeLists.txt',
        'if(BUILD_TESTING)\n  add_executable(stage_d_runtime_tests tests/stage_d_runtime.cpp)',
        'if(BUILD_TESTING)\n'
        '  add_executable(stage_d1_regression_tests tests/stage_d1_regression.cpp)\n'
        '  target_link_libraries(stage_d1_regression_tests PRIVATE pulse_core)\n'
        '  add_test(NAME stage_d1_regression COMMAND stage_d1_regression_tests)\n'
        'endif()\n\n'
        'if(BUILD_TESTING)\n  add_executable(stage_d_runtime_tests tests/stage_d_runtime.cpp)',
        'D1 explicit regression target')


def main()->int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo',type=pathlib.Path,required=True)
    ap.add_argument('--dry-run',action='store_true')
    ap.add_argument('--manifest',type=pathlib.Path)
    args=ap.parse_args();repo=args.repo.resolve()
    if not (repo/'.git').exists():raise RuntimeError(f'{repo} is not a git working tree')
    head=git(repo,'rev-parse','HEAD')
    if head!=BASE:
        git(repo,'merge-base','--is-ancestor',BASE,'HEAD')
    if not args.dry_run and git(repo,'status','--porcelain'):
        raise RuntimeError('working tree is not clean; commit or move local changes before applying')
    p=Patch(repo)
    patch(p,pathlib.Path(__file__).resolve().parent.parent)
    manifest=p.write(args.dry_run)
    manifest['head_before_patch']=head
    output=json.dumps(manifest,ensure_ascii=False,indent=2)+'\n'
    if args.manifest:
        path=args.manifest.resolve()
        if not args.dry_run:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(output,encoding='utf-8')
    print(output)
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (RuntimeError,ValueError,OSError) as ex:
        print('STAGE_D1_REFUSED: '+str(ex),file=sys.stderr)
        raise SystemExit(2)
