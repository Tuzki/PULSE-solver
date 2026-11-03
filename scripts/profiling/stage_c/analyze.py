#!/usr/bin/env python3
"""Physical-frame perf analysis, disjoint module shares, and exact-count joins."""
import argparse
import collections
import csv
import gzip
import html
import json
import math
from pathlib import Path
import re
import subprocess
import sys

from profile_run import symbols


def ci(hits,n):
    z=1.95996398454;p=hits/n;d=1+z*z/n
    c=(p+z*z/(2*n))/d;r=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [100*(c-r),100*(c+r)]


def category(stack):
    leaf=stack[0]['name'];names=[f['name'] for f in stack]
    in_bind=any('::bind_observations(' in n for n in names)
    if re.match(r'^(?:__)?(?:libc_)?(?:malloc|calloc|realloc|free|cfree|_int_malloc|_int_free|malloc_consolidate|unlink_chunk|sysmalloc|alloc_new_heap|new_heap|tcache)',leaf):return 'memory_allocator'
    if stack[0]['dso'].startswith(('[kernel','[unknown')):
        if any(re.search(r'write|fsync|fdatasync|vfs_|filemap',n) for n in names):return 'disk_io_kernel'
        return 'kernel_or_unknown'
    for f in stack:
        n=f['name']
        if 'CowValue<pulse::ModeBinding>::edit' in n:return 'cow_binding_copy'
        if 'pulse::Mode::Mode(' in n or 'pulse::Mode::operator=' in n or 'pulse::RunState::' in n:return 'state_mode_copy'
        if 'bind_observations(' in n:return 'mode_binding'
        if 'pulse::engineering::Flow::Flow(' in n:return 'flow_construction'
        if 'Flow::compatible(' in n:return 'flow_compatibility'
        if 'Flow::continued' in n:return 'flow_continuation'
        if any(s in n for s in ('Flow::state(','Flow::value(','Flow::bounds(','Flow::observe(','Flow::tangent(')):return 'flow_evaluation'
        if any(s in n for s in ('decimal_origin','decimal_origins','pulse::Time::','::time_input(','::sum_origin(','::exact_time_origin(')):return 't128_and_origins'
        if 'engineering::next_events(' in n or 'engineering::validate_event_timing(' in n:return 'root_search_own'
        if 'PevtArchive::' in n or 'pulse::Trajectory::' in n:return 'pevt_archive'
        if n.startswith('pulse::software::') or f['dso'].endswith('CTRL.so'):return 'software_control'
        if '::Assembler::' in n and in_bind:return 'mode_binding'
        if any(s in n for s in ('compile_specified(','::Assembler::','portfolio_compile(','portfolio_mode(','::settle(')):return 'mode_entry_and_compile_residual'
        if 'portfolio_original_check(' in n:return 'original_equation_checks'
        if any(s in n for s in ('EventKernel::','event_fingerprint(','check_agenda_origins(','::prune(')):return 'event_scheduling'
        if '::closure(' in n:return 'closure_residual'
        if re.match(r'^(?:__)?(?:write|writev|fsync|fdatasync)',n):return 'disk_io_user'
    return 'runtime_initialization_other'


def flame(records,path,cpu,total):
    root={'name':'all target CPU','weight':0,'children':{}}
    for r in records:
        node=root;node['weight']+=r['weight']
        for f in reversed(r['frames']):
            name=f['name'];node=node['children'].setdefault(name,{'name':name,'weight':0,'children':{}});node['weight']+=r['weight']
    maxdepth=0;rects=[]
    def walk(node,x,depth):
        nonlocal maxdepth
        maxdepth=max(maxdepth,depth);width=1600*node['weight']/total
        if width<.35:return
        color=f'hsl({sum(map(ord,node["name"]))%48+8},85%,72%)'
        title=html.escape(f'{node["name"]}\n{100*node["weight"]/total:.4f}% inclusive; {cpu*node["weight"]/total:.6f} estimated CPU s')
        label=html.escape(node['name'][:max(0,int(width/7)-1)])
        rects.append(f'<g class="frame"><title>{title}</title><rect x="{x:.3f}" y="{depth*18+40}" width="{width:.3f}" height="17" fill="{color}"/><text x="{x+2:.3f}" y="{depth*18+53}">{label}</text></g>')
        child_x=x
        for child in sorted(node['children'].values(),key=lambda c:c['name']):
            walk(child,child_x,depth+1);child_x+=1600*child['weight']/total
    walk(root,0,0);height=(maxdepth+1)*18+45
    body=f'<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="{height}" preserveAspectRatio="none" viewBox="0 0 1600 {height}"><style>text{{font:11px monospace;pointer-events:none}}.frame:hover rect{{stroke:black;stroke-width:.7}}rect{{cursor:pointer}}</style><text x="8" y="20">Stage C: physical call stacks; hover for function and CPU share; click to zoom; double click to reset</text>'+''.join(rects)+f'<script><![CDATA[const s=document.documentElement;const initial="0 0 1600 {height}";document.querySelectorAll(".frame").forEach(g=>g.onclick=e=>{{e.stopPropagation();let r=g.querySelector("rect"),x=+r.getAttribute("x"),y=+r.getAttribute("y"),w=+r.getAttribute("width");s.setAttribute("viewBox",[x,y,w,Math.max(50,{height}-y)].join(" "));}});s.ondblclick=()=>s.setAttribute("viewBox",initial);]]></script></svg>'
    path.write_text(body,encoding='utf-8')


def main():
    p=argparse.ArgumentParser();p.add_argument('--sampling',type=Path,required=True);p.add_argument('--counts',type=Path,required=True);p.add_argument('--binary',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    measurement=json.loads((a.sampling/'measurement.json').read_text());pid=measurement['pid'];cpu=measurement['cpu_total_seconds'];records=[];current=None;mappings=[]
    with gzip.open(a.sampling/'perf-script.txt.gz','rt',errors='replace') as f:
        for line in f:
            if 'PERF_RECORD_MMAP2' in line:
                m=re.search(r'PERF_RECORD_MMAP2 (\d+)/(\d+): \[(0x[0-9a-f]+)\((0x[0-9a-f]+)\) @ (0x[0-9a-f]+|0).*?:\s+[-rwxps]+\s+(.+)$',line)
                if m and int(m[1])==pid:mappings.append((int(m[3],16),int(m[4],16),int(m[5],16),m[6].strip()))
                continue
            m=re.match(r'^\s*(\S+)\s+(\d+)\s+([0-9.]+):\s+(\d+)\s+cpu-clock[^:]*:',line)
            if m:
                if current and current['frames']:records.append(current)
                current={'weight':int(m[4]),'time':float(m[3]),'frames':[]} if int(m[2])==pid else None;continue
            if re.match(r'^\s*\S+\s+\d+\s+(?:\[\d+\]\s+)?[0-9.]+:',line):
                if current and current['frames']:records.append(current)
                current=None;continue
            if current is None:continue
            m=re.match(r'\s+([0-9a-f]+)\s+(.+)\s+\(([^()]*)\)\s*$',line)
            if m:
                name=m[2];off=re.search(r'\+0x([0-9a-f]+)$',name);delta=int(off[1],16) if off else 0
                if off:name=name[:off.start()]
                current['frames'].append({'ip':int(m[1],16),'name':sys.intern(name),'dso':sys.intern(m[3]),'offset':delta})
    if current and current['frames']:records.append(current)
    assert records,'No target CPU stacks'
    total=sum(r['weight'] for r in records);N=len(records);funcs={};source_ips={};symcache={}
    # Physical function symbols remain authoritative. DWARF only provides source
    # locations; it never substitutes inline aliases for a physical frame.
    for module in {f['dso'] for r in records for f in r['frames']}:
        file=Path(module)
        if file.is_file() and 'pulse-solver' in file.name:
            symcache[module]={r['function']:r['address'] for r in symbols(file)}
    for r in records:
        for i,f in enumerate(r['frames']):
            key=(f['name'],f['dso']);f['key']=key
            if key not in funcs:funcs[key]={'self_weight':0,'total_weight':0,'self_samples':0,'total_samples':0,'stack':r['frames']}
            table=symcache.get(f['dso'],{})
            if f['name'] in table:
                f['relative']=table[f['name']]+f['offset']-(1 if i else 0)
                source_ips.setdefault(f['dso'],set()).add(f['relative'])
            elif Path(f['dso']).is_file():
                for base,length,off,path in reversed(mappings):
                    if path==f['dso'] and base<=f['ip']<base+length:
                        f['relative']=f['ip']-base+off-(1 if i else 0)
                        source_ips.setdefault(f['dso'],set()).add(f['relative']);break
        funcs[r['frames'][0]['key']]['self_weight']+=r['weight'];funcs[r['frames'][0]['key']]['self_samples']+=1
        for key in {f['key'] for f in r['frames']}:funcs[key]['total_weight']+=r['weight'];funcs[key]['total_samples']+=1
    locations={}
    for module,ips in source_ips.items():
        values=sorted(ips);s=subprocess.check_output(['addr2line','-f','-C','-e',module],input=''.join(hex(i)+'\n' for i in values),text=True).splitlines()
        assert len(s)==2*len(values)
        for i,ip in enumerate(values):locations[module,ip]=s[2*i+1]
    def source(frame):return locations.get((frame['dso'],frame.get('relative')),'external / physical ELF symbol')
    manifest=json.loads((a.counts/'probes.json').read_text());counter=json.loads((a.counts/'counts.json').read_text());by_name={m['function']:(q,m) for q,m in zip(counter['probes'],manifest) if m['symbol']!='instruction+0x40'}
    exclusive=collections.Counter();hits=collections.Counter();bindparts=collections.Counter();bindhits=collections.Counter();groups=collections.Counter();group_hits=collections.Counter();folded=collections.Counter()
    for r in records:
        stack=r['frames'];w=r['weight'];cat=category(stack);exclusive[cat]+=w;hits[cat]+=1
        names=[f['name'] for f in stack];joined='\n'.join(names)
        for label,needle in [('observe','Flow::observe('),('flow_ctor','Flow::Flow('),('flow_compatible','Flow::compatible('),('bind_observations','::bind_observations('),('closure','::closure('),('roots','engineering::next_events('),('archive','PevtArchive::'),('t128','decimal_origin'),('software','pulse::software::Data::call(')]:
            if needle in joined:groups[label]+=w;group_hits[label]+=1
        if 'Flow::Flow(' in joined and 'Flow::observe(' in joined:groups['observe_temporary_flow']+=w;group_hits['observe_temporary_flow']+=1
        bind=next((i for i,f in enumerate(stack) if '::bind_observations(' in f['name']),None)
        if bind is not None:
            inner='\n'.join(names[:bind+1]);location=source(stack[bind]);m=re.search(r'descriptor.cpp:(\d+)',location);line=int(m[1]) if m else None
            if 'CowValue<pulse::ModeBinding>::edit' in inner:part='COW_binding_clone_including_children'
            elif 'Mode::Mode(' in inner:part='initial_Mode_copy'
            elif 'Eigen::' in inner:part='matrix_math_and_matrix_buffers'
            elif any(s in inner for s in ('basic_ostream','basic_ostringstream','num_put','printf','basic_stringbuf','ostream_insert','sputn')):part='mode_id_string_formatting'
            elif any(s in inner for s in ('_Rb_tree','std::map','basic_string','memcmp','strlen','char_traits')):part='strings_and_map_lifecycle'
            elif line and 746<=line<=767:part='matrix_math_norms_and_temporary_buffers'
            elif line==738:part='initial_N_B_matrix_copies'
            elif line and 768<=line<=773:part='mode_id_string_formatting'
            elif line==739:part='Assembler_maps_and_string_setup'
            else:part='held_updates_lookup_and_other'
            bindparts[part]+=w;bindhits[part]+=1
        folded[';'.join(f['name'].replace(';',':') for f in reversed(stack))]+=w
    rows=[]
    for key,q in sorted(funcs.items(),key=lambda pair:pair[1]['self_weight'],reverse=True):
        name,module=key;pair=by_name.get(name);count=pair[0]['entries'] if pair else None
        self_s=cpu*q['self_weight']/total;total_s=cpu*q['total_weight']/total
        frame=next(f for f in q['stack'] if f['key']==key)
        rows.append({'rank':len(rows)+1,'function':name,'module':module,'source':source(frame),
                     'self_cpu_percent':100*q['self_weight']/total,'total_cpu_percent':100*q['total_weight']/total,
                     'self_cpu_seconds_estimate':self_s,'total_cpu_seconds_estimate':total_s,
                     'self_samples':q['self_samples'],'total_samples':q['total_samples'],
                     'actual_calls':count if count is not None else 'not instrumented / possibly inline',
                     'self_cpu_ns_per_call_estimate':1e9*self_s/count if count else '',
                     'total_cpu_ns_per_call_estimate':1e9*total_s/count if count else '',
                     'self_percent_ci95_ideal':json.dumps(ci(q['self_samples'],N)),
                     'representative_stack_leaf_to_root':' <- '.join(f['name'] for f in q['stack'])})
    def csvfile(name,data):
        with (a.out/name).open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
    csvfile('FUNCTION_HOTSPOTS.csv',rows)
    modules=[{'module':k,'exclusive_cpu_percent':100*v/total,'exclusive_cpu_seconds_estimate':cpu*v/total,'samples':hits[k],'ci95_percent_ideal':json.dumps(ci(hits[k],N))} for k,v in exclusive.most_common()]
    csvfile('MODULE_EXCLUSIVE.csv',modules);assert abs(sum(r['exclusive_cpu_percent'] for r in modules)-100)<1e-8
    bindtotal=sum(bindparts.values());bindrows=[{'component':k,'cpu_seconds_estimate':cpu*v/total,'percent_of_process':100*v/total,'percent_within_bind':100*v/bindtotal,'samples':bindhits[k]} for k,v in bindparts.most_common()]
    if bindrows:csvfile('BIND_BREAKDOWN.csv',bindrows)
    group_rows=[{'group':k,'inclusive_cpu_seconds_estimate':cpu*v/total,'inclusive_cpu_percent':100*v/total,'samples':group_hits[k]} for k,v in groups.most_common()]
    csvfile('NESTED_GROUPS.csv',group_rows)
    (a.out/'stacks.folded').write_text(''.join(f'{k} {v}\n' for k,v in folded.items()),encoding='utf-8')
    flame(records,a.out/'FLAMEGRAPH.svg',cpu,total)
    summary={'sample_count':N,'period_weight_total_ns':total,'cpu_seconds_os':cpu,'modules':modules,'bind_breakdown':bindrows,'groups':group_rows,'top20':rows[:20],
             'method':'Physical frames; exclusive module allocation is one category per sample. Function and nested-group Total shares overlap. CPU seconds are sample-weight estimates scaled to target OS CPU; mean per-call costs join a separate verified full execution count. CI is ideal independent-sample Wilson interval and excludes correlation and systematic bias.'}
    (a.out/'analysis.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({'samples':N,'modules':modules,'bind_breakdown':bindrows},indent=2))


if __name__=='__main__':main()
