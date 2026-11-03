#!/usr/bin/env python3
"""Stage B1/B2 source transformation (architecture migration candidate).

Input: unmodified Tuzki/PULSE-solver performance/stage-b-20261103,
SHA 0cb30419575f9254901882c14aa88d6e01e78f3f.
Output: ModeDefinition + ModeBinding COW, RunState COW, code-access migration.

This script deliberately does not claim compilation or A010 certification.
After applying, Codex must resolve C++ type/mutation issues and run tests.
"""
from __future__ import annotations
import argparse
import json
import re
import subprocess
from pathlib import Path

BASE = "0cb30419575f9254901882c14aa88d6e01e78f3f"
DEF_FIELDS = {'M','constraints','invariant_lift','invariant_generator','invariant_reduce'}
BIND_FIELDS = {'observations','residual_map','residual_reference','maps','guards'}
COW_STATE_FIELDS = {'regs','software','agenda','generations'}
COW_HEADER = 'include/pulse/cow_value.hpp'
TEST = 'tests/stage_b_cow_transaction.cpp'
MODE_START = 'struct Mode {\n'
MODE_END = 'struct Stats {\n'
MODES = '''struct ModeDefinition;
struct ModeBinding;
struct Mode {
  bool classification_only = false;
  int numerical_strategy = 2;
  std::shared_ptr<const Matrix> candidate_roundoff_scale;
  std::shared_ptr<const ObserverBinding> observer_binding;
  std::set<std::string> observer_maps;
  std::vector<int> observer_rows;
  std::map<std::string, bool> bools;
  std::map<int, int> segments;
  struct Guard {
    Vector row;
    int part;
    int direction;
    std::string kind;
    int knot = -1, segment = -1, step = 0;
    double arrival_error = 0;
  };
  // Immutable static matrix definition (COW detached only during compilation
  // or an explicitly requested state-coordinate transformation).
  CowValue<ModeDefinition> definition;
  // Dynamic observer binding, guards and mode-dependent signal maps.
  CowValue<ModeBinding> binding;
  std::string id;
  std::string elimination_path;
  uint64_t version = 0;
  double residual = 0;
  Mode();
  Mode(const Mode&) = default;
  Mode(Mode&&) noexcept = default;
  Mode& operator=(const Mode&) = default;
  Mode& operator=(Mode&&) noexcept = default;
};
struct ModeDefinition {
  Matrix M, constraints;
  Matrix invariant_lift, invariant_generator, invariant_reduce;
};
struct ModeBinding {
  Matrix observations, residual_map, residual_reference;
  std::map<std::string, Vector> maps;
  std::vector<Mode::Guard> guards;
};
inline Mode::Mode() = default;
'''


def git_sha(root):
    try:
        return subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
    except (FileNotFoundError,subprocess.CalledProcessError):
        return None


def patch_core(text):
    assert text.count(MODE_START)==1 and text.count(MODE_END)==1
    before, rest = text.split(MODE_START,1)
    discarded, after = rest.split(MODE_END,1)
    assert 'Matrix M, observations, constraints, residual_map,' in discarded
    assert 'std::vector<Guard> guards;' in discarded
    text=before+MODES+MODE_END+after
    assert '#include <memory>' in text
    text=text.replace('#include <memory>','#include <memory>\n#include "pulse/cow_value.hpp"',1)
    old='''  std::map<std::string, double> regs;
  struct SoftwareState {
    std::vector<unsigned char> bytes;
    uint64_t invocation = 0;
  };
  std::map<std::string, SoftwareState> software;
  Mode mode;
  std::vector<Agenda> agenda;
  std::map<int, uint64_t> generations;
'''
    new='''  CowValue<std::map<std::string, double>> regs;
  struct SoftwareState {
    std::vector<unsigned char> bytes;
    uint64_t invocation = 0;
  };
  CowValue<std::map<std::string, SoftwareState>> software;
  Mode mode;
  CowValue<std::vector<Agenda>> agenda;
  CowValue<std::map<int, uint64_t>> generations;
'''
    assert text.count(old)==1, 'RunState definition differs; stop'
    return text.replace(old,new,1)


def replace_basic_fields(text):
    """Convert legacy field access to read-only shared storage access."""
    for field in sorted(DEF_FIELDS|BIND_FIELDS,key=len,reverse=True):
        owner = 'definition' if field in DEF_FIELDS else 'binding'
        # Guard against replacing member names inside the new header's struct
        text,n=re.subn(r'\.'+field+r'\b',f'.{owner}.read().{field}',text)
        text,n2=re.subn(r'->'+field+r'\b',f'->{owner}.read().{field}',text)
    for field in sorted(COW_STATE_FIELDS,key=len,reverse=True):
        text=re.sub(r'\.'+field+r'\b',f'.{field}.read()',text)
        text=re.sub(r'->'+field+r'\b',f'->{field}.read()',text)
    return text


def rewrite_mutation_on_line(line):
    """Replace read() with edit() for explicitly mutable expressions.

    Uses a conservative, line-scoped source transformation. Codex must still
    compile the result and inspect any remaining non-const-binding diagnostics.
    """
    # Whole-value assignments use CowValue<T>::operator=(T), which creates
    # fresh ownership rather than changing a shared copy.
    line=re.sub(r'\.(regs|software|agenda|generations)\.read\(\)(\s*=\s*(?!=))',
                lambda m: '.'+m.group(1)+m.group(2),line)
    # Whole Mode field writes, including M.topRows()/maps[key] mutations.
    fragments=line.split(';')
    rewritten=[]
    for fragment in fragments:
        # Each side of an assignment needs its own alias classification.
        # Match simple assignment operators, not comparison operators.
        assignments=list(re.finditer(r'(?<![=!<>])(?:\+=|-=|\*=|/=|=(?!=))',fragment))
        for a in reversed(assignments):
            left=fragment[:a.start()]
            matches=list(re.finditer(r'\.(definition|binding|regs|software|agenda|generations)\.read\(\)',left))
            if not matches:
                continue
            last=matches[-1]
            # Only a storage field on the LHS is mutable. A predicate before
            # the LHS could contain reads, so restrict to last occurrence.
            suffix=left[last.end():].strip()
            if suffix and not suffix.startswith(('.', '[', '(')):
                continue
            if last.group(1) in ('definition','binding') and not suffix.startswith('.'):
                continue
            if last.group(1) in COW_STATE_FIELDS and not suffix:
                # Whole CowValue assignment: revert .read() to direct owner.
                fragment=fragment[:last.start()]+fragment[last.start():].replace('.read()','',1)
            else:
                fragment=fragment[:last.start()]+fragment[last.start():].replace('.read()','.edit()',1)
        rewritten.append(fragment)
    line=';'.join(rewritten)
    # Non-const reference / for-each writes: use mutable detached storage.
    if re.search(r'\bfor\s*\(\s*(?:const\s+)?auto\s*&',line) and 'const auto' not in line:
        line=re.sub(r'\.(definition|binding|regs|software|agenda|generations)\.read\(\)',
                    lambda m:'.'+m.group(1)+'.edit()',line)
    if re.search(r'(?<!const )\bauto\s*&(?:\s*\[|\s*[a-zA-Z_])[^;=]*=',line) and not re.search(r'\bconst\s+auto\s*&',line):
        # Non-const reference to one of our storage fields.
        line=re.sub(r'\.(definition|binding|regs|software|agenda|generations)\.read\(\)',
                    lambda m:'.'+m.group(1)+'.edit()',line)
    if re.search(r'\bstd::erase_if\s*\(',line):
        line=re.sub(r'\.(regs|software|agenda|generations)\.read\(\)',
                    lambda m:'.'+m.group(1)+'.edit()',line)
    # COW map's operator[] is inherently mutable, even if it happened to be a read.
    line=re.sub(r'\.(regs|software|agenda|generations)\.read\(\)(?=\s*\[)',
                lambda m:'.'+m.group(1)+'.edit()',line)
    line=re.sub(r'\.binding\.read\(\)\.maps(?=\s*\[)', '.binding.edit().maps',line)
    # Eigen and map mutators called through .at()/.row() require COW detachment.
    if re.search(r'\.(?:at|row|col|topRows|bottomRows|block|segment)\([^;]*\)\.(?:setZero|setIdentity|resize|clear)\(',line):
        line=re.sub(r'\.(?:definition|binding)\.read\(\)',lambda m:m.group(0).replace('.read()', '.edit()'),line)
    # Mutator calls on COW-owned STL/Eigen values.
    method=r'(?:push_back|emplace_back|emplace|insert|erase|clear|resize|reserve|setZero|setIdentity|swap|pop_back|assign|shrink_to_fit|push_front|pop_front)'
    line=re.sub(r'\.(definition|binding|regs|software|agenda|generations)\.read\(\)(?=(?:\.[A-Za-z_][A-Za-z0-9_]*|\[[^\]]*\])*\.'+method+r'\s*\()',
                lambda m:'.'+m.group(1)+'.edit()',line)
    return line


def migrate(text):
    text=replace_basic_fields(text)
    return '\n'.join(rewrite_mutation_on_line(line) for line in text.split('\n'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('repo',type=Path)
    p.add_argument('--in-place',action='store_true',required=True)
    p.add_argument('--allow-different-head',action='store_true',help='Only if you verified content manually')
    args=p.parse_args()
    root=args.repo.resolve();assert (root/'include/pulse/core.hpp').is_file(),root
    sha=git_sha(root)
    if not args.allow_different_head and sha!=BASE:
        raise SystemExit(f'Wrong HEAD {sha!r}; expected {BASE}. Use a fresh Stage B branch.')
    if COW_HEADER in str(root):raise SystemExit('invalid root')
    if (root/COW_HEADER).exists():raise SystemExit('cow_value.hpp already present; stop')
    src=Path(__file__).resolve().parents[1]
    core=root/'include/pulse/core.hpp'
    orig=core.read_bytes(); crlf=b'\r\n' in orig
    current=orig.decode('utf-8').replace('\r\n','\n')
    transformed=patch_core(current)
    changes={}
    # Source files (including existing tests/CLI and public headers) must be
    # migrated together because Mode/RunState are public C++ types.
    paths=[]
    for folder in ('src','include/pulse','apps','tests'):
        for path in (root/folder).rglob('*'):
            if path.is_file() and path.suffix in ('.cpp','.hpp','.h','.c') and path!=core:
                paths.append(path)
    outputs={core:transformed}
    for path in paths:
        b=path.read_bytes()
        try:t=b.decode('utf-8').replace('\r\n','\n')
        except UnicodeDecodeError:continue
        new=migrate(t)
        if new!=t:outputs[path]=new
    # Write only after all transformations succeed.
    for path,s in outputs.items():
        orig=path.read_bytes()
        b=s.encode('utf-8')
        if b'\r\n' in orig:b=b.replace(b'\n',b'\r\n')
        path.write_bytes(b)
        changes[path.relative_to(root).as_posix()]={'old_bytes':len(orig),'new_bytes':len(b)}
    for artifact in (COW_HEADER,TEST):
        target=root/artifact;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((src/artifact).read_bytes());changes[artifact]={'added':True}
    cmake=root/'CMakeLists.txt';cmtext=cmake.read_bytes(); assert b'add_test(NAME stage_b_shared_flow' in cmtext
    snippet='''\nif(BUILD_TESTING)\n add_executable(stage_b_cow_transaction_tests tests/stage_b_cow_transaction.cpp)\n target_link_libraries(stage_b_cow_transaction_tests PRIVATE pulse_core)\n add_test(NAME stage_b_cow_transaction COMMAND stage_b_cow_transaction_tests)\nendif()\n'''
    cmake.write_bytes(cmtext+snippet.encode());changes['CMakeLists.txt']={'updated':True}
    report=root/'STAGE_B_REMAINING_MIGRATION.json'
    report.write_text(json.dumps({'baseline':BASE,'modified':changes,'status':'CODEGEN_NOT_COMPILE_VALIDATED',
                                   'validation_needed':['Windows/Linux Release','all CTest','5ms bitwise PEVT','500ms A010 17 channels',
                                                        'six rollback injection points','re-profile 68.08s baseline']},indent=2)+'\n')
    print(f'Applied B1/B2 COW structural migration to {len(changes)} files; compile and repair required.')
    print('Changes recorded in:',report)


if __name__=='__main__':main()
