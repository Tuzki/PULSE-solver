#!/usr/bin/env python3
"""Summarize external CPU samples. Sample hits are never invocation counts."""
import argparse
import bisect
import collections
import csv
import gzip
import json
import pathlib
import re
import subprocess


def resolve(binary, addresses, tool):
    values = sorted(set(addresses))
    if not values:
        return {}
    result = subprocess.run([tool, '-f', '-C', '-e', str(binary)],
                            input=''.join(hex(x)+'\n' for x in values),
                            text=True, capture_output=True, check=True)
    lines = result.stdout.splitlines()
    if len(lines) != len(values)*2:
        raise ValueError('Unexpected addr2line output shape')
    return {v: (lines[2*i], lines[2*i+1]) for i,v in enumerate(values)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--platform', choices=['linux','windows'], required=True)
    p.add_argument('--samples', type=pathlib.Path, required=True)
    p.add_argument('--binary', type=pathlib.Path, required=True)
    p.add_argument('--ledger', type=pathlib.Path, required=True)
    p.add_argument('--addr2line', default='addr2line')
    p.add_argument('--out', type=pathlib.Path, required=True)
    a = p.parse_args(); a.out.mkdir(parents=True,exist_ok=True)
    ledger=json.loads(a.ledger.read_text(encoding='utf8')); run=ledger['runs'][0]
    pid=run['pid']; cpu=run['cpu_total_seconds']; records=[]; origins={}; exported={}; locations={}
    opener=gzip.open if a.samples.suffix=='.gz' else open
    if a.platform=='linux':
        mappings=[]; current=None; last_key=None; module_cache={}
        def flush():
            if current and current['frames']: records.append(current.copy())
        with opener(a.samples,'rt',encoding='utf8',errors='replace') as stream:
            for line in stream:
                if 'PERF_RECORD_MMAP2' in line:
                    m=re.search(r'PERF_RECORD_MMAP2 (\d+)/(\d+): \[(0x[0-9a-f]+)\((0x[0-9a-f]+)\) @ (0x[0-9a-f]+).*?:\s+[-rwxps]+\s+(.+)$',line)
                    if m and int(m[1])==pid:
                        mappings.append((int(m[3],16),int(m[4],16),int(m[5],16),m[6].strip()))
                    continue
                m=re.match(r'^\s*(\S+)\s+(\d+)\s+([0-9.]+):\s+(\d+)\s+cpu-clock[^:]*:',line)
                if m:
                    flush();current=None;last_key=None
                    if int(m[2])==pid:current={'weight':int(m[4]),'frames':[],'time':float(m[3])}
                    continue
                if re.match(r'^\s*\S+\s+\d+\s+(?:\[\d+\]\s+)?[0-9.]+:',line):
                    flush();current=None;last_key=None
                    continue
                if current is not None:
                    m=re.match(r'\s+([0-9a-f]+)\s+(.+?)\s*$',line)
                    if not m:
                        location=line.strip().removesuffix(' (inlined)')
                        if last_key and re.search(r':\d+(?:\s|$)',location):
                            locations.setdefault(last_key,location)
                        continue
                    ip=int(m[1],16);name=m[2]
                    suffix=re.search(r'\s+\(([^()]*)\)$',name)
                    dso=suffix[1] if suffix else None
                    if suffix:name=name[:suffix.start()]
                    name=re.sub(r'\+0x[0-9a-f]+$','',name)
                    if not dso or dso=='inlined':
                        if ip not in module_cache:
                            module_cache[ip]=next((path for base,size,offset,path in mappings if base<=ip<base+size),'[unmapped]')
                        dso=module_cache[ip]
                    key=(name,dso);current['frames'].append(key)
                    last_key=key
                    if key not in origins and pathlib.Path(dso).is_file():
                        for base,size,offset,path in mappings:
                            if path==dso and base<=ip<base+size:
                                origins[key]=ip-base+offset;break
            flush()
        by_module=collections.defaultdict(list)
        for key,ip in origins.items():by_module[key[1]].append(ip)
        for module,addresses in by_module.items():
            decoded=resolve(module,addresses,a.addr2line)
            for key,ip in origins.items():
                if key[1]==module:locations.setdefault(key,decoded[ip][1])
    else:
        modules={}; raw=[]
        with opener(a.samples,'rt',encoding='utf8',errors='replace') as stream:
            for line in stream:
                parts=line.rstrip('\n').split('\t')
                if parts[0]=='M':modules[(int(parts[1],16),int(parts[2],16))]=parts[3]
                elif parts[0]=='F':exported[int(parts[1],16)]=parts[2]
                elif parts[0]=='S':raw.append((float(parts[1]),int(parts[2]),[int(x,16) for x in parts[5].split(',')]))
        imagebase=0x140000000  # Verified with objdump -p for this x64 MinGW executable.
        target=[(base,size,path) for (base,size),path in modules.items() if pathlib.PureWindowsPath(path).name.lower()=='pulse-solver.exe']
        assert len(target)==1, target
        base,size,path=target[0]
        ips={ip for _,_,stack in raw for ip in stack if base<=ip<base+size}
        decoded=resolve(a.binary,[ip-base+imagebase for ip in ips],a.addr2line)
        locations={}
        for time,weight,stack in raw:
            if not weight:continue  # Idle threads: retain raw evidence, exclude from CPU shares.
            frames=[]
            for ip in stack:
                if base<=ip<base+size:
                    name,location=decoded[ip-base+imagebase];dso=str(a.binary)
                else:
                    found=next(((b,s,p) for (b,s),p in modules.items() if b<=ip<b+s),None)
                    dso=found[2] if found else '[unmapped]'
                    name=exported.get(ip,pathlib.PureWindowsPath(dso).name+'+'+hex(ip-(found[0] if found else 0)))
                    location='external PE/export symbol; source unavailable'
                key=(name,dso);frames.append(key)
                if key not in locations or locations[key].startswith('??'):locations[key]=location
            if frames:records.append({'weight':weight,'frames':frames,'time':time})

    assert records, 'No target samples parsed'
    total=sum(r['weight'] for r in records)
    self_weight=collections.Counter();inclusive=collections.Counter();self_hits=collections.Counter();inc_hits=collections.Counter()
    representatives={}; categories=collections.Counter();category_hits=collections.Counter();groups=collections.Counter()
    routing={'engineering_next_events_samples':0,'fri_namespace_samples':0,'first_root_source_samples':0}
    group_tests={
        'portfolio_original_check':lambda n:'portfolio_original_check(' in n,
        'Flow_constructor':lambda n:'pulse::engineering::Flow::Flow(' in n,
        'Flow_continued':lambda n:'pulse::engineering::Flow::continued(' in n,
        'Flow_compatible':lambda n:'pulse::engineering::Flow::compatible(' in n,
        'engineering_next_events':lambda n:'pulse::engineering::next_events(' in n,
        'archive_append':lambda n:'PevtArchive::append(' in n or 'PevtArchive::Data::append(' in n or 'pulse::Trajectory::append(' in n,
        'archive_write':lambda n:'PevtArchive::write(' in n,
        'archive_equation_dedup':lambda n:'PevtArchive::Data::equation(' in n,
        'software_Data_call':lambda n:'pulse::software::Data::call(' in n,
        'software_Data_inputs':lambda n:'pulse::software::Data::inputs(' in n,
        'decimal_origin':lambda n:'decimal_origin_from_binary_time(' in n,
        'multiply_digits':lambda n:'multiply_digits(' in n,
        'Mode_copy':lambda n:'pulse::Mode::Mode(' in n or 'pulse::Mode::operator=(' in n,
        'RunState_copy':lambda n:'pulse::RunState::RunState(' in n or 'pulse::RunState::operator=(' in n,
        'bind_observations':lambda n:'bind_observations(' in n,
        'allocation_free_union':lambda n:n.startswith(('malloc','cfree','_int_malloc','_int_free','operator new(','operator delete(')),
        'state_signal':lambda n:'pulse::state_signal(' in n,
    }
    for r in records:
        stack=r['frames'];weight=r['weight'];leaf=stack[0];unique=set(stack)
        self_weight[leaf]+=weight;self_hits[leaf]+=1
        for key in unique:
            inclusive[key]+=weight;inc_hits[key]+=1
            if key not in representatives or len(stack)>len(representatives[key]):representatives[key]=stack
        names=[k[0] for k in stack];joined='\n'.join(names)
        if 'pulse::engineering::next_events(' in joined:routing['engineering_next_events_samples']+=1
        if 'fri::' in joined:routing['fri_namespace_samples']+=1
        if any('first_root.cpp' in locations.get(k,'') for k in unique):routing['first_root_source_samples']+=1
        for group,predicate in group_tests.items():
            if any(predicate(n) for n in names):groups[group]+=weight
        if any(group_tests['software_Data_call'](n) for n in names) and any(group_tests['Flow_compatible'](n) for n in names):
            groups['software_call_and_Flow_compatible_intersection']+=weight
        if any(group_tests['bind_observations'](n) for n in names) and any(group_tests['Mode_copy'](n) for n in names):
            groups['bind_observations_and_Mode_copy_intersection']+=weight
        if 'PevtArchive::write(' in joined:category='archive_final_write'
        elif any(group_tests['archive_append'](n) for n in names):category='archive_append'
        elif 'portfolio_original_check(' in joined:category='original_checks'
        elif 'pulse::engineering::next_events(' in joined:category='roots'
        elif 'pulse::(anonymous namespace)::closure(' in joined:category='closure_other'
        elif 'portfolio_mode(' in joined:category='mode_entry'
        elif 'pulse::engineering::Flow::Flow(' in joined:category='flow_construction_other'
        elif 'pulse::engineering::Flow::continued(' in joined:category='flow_continuation_other'
        else:category='other_or_unresolved'
        categories[category]+=weight;category_hits[category]+=1

    rows=[]
    for key,value in self_weight.most_common():
        name,dso=key
        row={'platform':a.platform,'rank':len(rows)+1,'function':name,'source_file_line':locations.get(key,'unresolved/external'),
             'self_cpu_percent':100*value/total,'total_cpu_percent':100*inclusive[key]/total,
             'self_samples':self_hits[key],'total_samples':inc_hits[key],
             'self_sample_hits_per_cpu_second':self_hits[key]/cpu,
             'actual_invocations':'NOT_MEASURED_BY_SAMPLING',
             'self_cpu_seconds_estimate':cpu*value/total,'total_cpu_seconds_estimate':cpu*inclusive[key]/total,
             'module':dso,'representative_stack_leaf_to_root':' <- '.join(k[0] for k in representatives[key])}
        rows.append(row)
    report={'platform':a.platform,'target_pid':pid,'cpu_seconds_os':cpu,'sample_count':len(records),'weight_total':total,
            'weight_unit':'cpu-clock nanoseconds' if a.platform=='linux' else 'per-thread CPU-time delta in 100ns ticks',
            'method':'sampling estimates; inclusive shares overlap; sample hits are not function calls',
            'routing':routing,'groups':{k:{'total_cpu_percent':100*v/total,'cpu_seconds_estimate':cpu*v/total} for k,v in groups.items()},
            'exclusive_categories':{k:{'percent':100*v/total,'cpu_seconds_estimate':cpu*v/total,'samples':category_hits[k]} for k,v in categories.items()},
            'top_self':rows[:50],
            'top_inclusive':[{'function':k[0],'module':k[1],'source_file_line':locations.get(k,'unresolved/external'),
                              'percent':100*v/total,'samples':inc_hits[k],
                              'representative_stack_leaf_to_root':' <- '.join(x[0] for x in representatives[k])} for k,v in inclusive.most_common(50)]}
    (a.out/'hotspots.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    with (a.out/'hotspots.csv').open('w',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print(json.dumps({k:report[k] for k in ['platform','sample_count','routing','groups','exclusive_categories']},indent=2))
    for r in rows[:20]:print(f"{r['self_cpu_percent']:6.2f}% self {r['total_cpu_percent']:6.2f}% inclusive {r['function'][:145]} {r['source_file_line']}")


if __name__=='__main__':main()
