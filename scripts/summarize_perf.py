#!/usr/bin/env python3
"""Resolve frame-pointer perf stacks using ELF symbols when perf lacks libelf.

Sample percentages are diagnostic inclusive call-path shares, not exclusive
timers. Unknown/truncated external stacks remain explicitly unclassified.
"""
import argparse
import bisect
import collections
import json
import pathlib
import re
import subprocess


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',required=True)
    p.add_argument('--binary',required=True)
    p.add_argument('--out',type=pathlib.Path,required=True)
    a=p.parse_args();binary=str(pathlib.Path(a.binary).resolve())
    text=subprocess.check_output(['perf','script','--show-mmap-events','-i',a.data],text=True)
    maps=[]
    for line in text.splitlines():
        m=re.search(r'PERF_RECORD_MMAP2 .*?\[(0x[0-9a-f]+)\((0x[0-9a-f]+)\) @ (0x[0-9a-f]+).*?:\s+[-rwxp]+\s+(.+)$',line)
        if m and m[4]==binary:maps.append(tuple(int(m[i],16) for i in (1,2,3)))
    if not maps:raise ValueError('binary mmap missing')
    symbols=[]
    for line in subprocess.check_output(['nm','-n','-S','-C',binary],text=True).splitlines():
        m=re.match(r'^([0-9a-f]+)\s+([0-9a-f]+)\s+[tTwW]\s+(.+)$',line)
        if m:symbols.append((int(m[1],16),int(m[2],16),m[3]))
    symbols.sort();starts=[s[0] for s in symbols]
    def resolve(address):
        for base,size,offset in maps:
            if base<=address<base+size:
                value=address-base+offset;i=bisect.bisect_right(starts,value)-1
                if i>=0 and value<symbols[i][0]+symbols[i][1]:return symbols[i][2]
        return None
    inclusive=collections.Counter();categories=collections.Counter();leaves=collections.Counter();total=0;samples=0
    for block in text.split('\n\n'):
        header=re.search(r':\s+(\d+)\s+cpu-clock:',block)
        if not header:continue
        weight=int(header[1]);total+=weight;samples+=1;names=[];frames=[]
        for line in block.splitlines()[1:]:
            m=re.match(r'\s+([0-9a-f]+)\s+.*\(([^()]*)\)\s*$',line)
            if not m:continue
            frames.append(m[2])
            if m[2]==binary:
                name=resolve(int(m[1],16))
                if name:names.append(name)
        if frames:leaves[pathlib.Path(frames[0]).name]+=weight
        for name in set(names):inclusive[name]+=weight
        joined='\n'.join(names)
        if 'stream_emit(' in joined:category='waveform stream_emit call path'
        elif 'compile_specified(' in joined:category='mode compilation call path'
        elif 'TrajectoryPool::encode(' in joined:category='archive shared-block encoding'
        elif 'TrajectoryPool::expand(' in joined:category='archive shared-block decoding'
        elif 'Trajectory::mode(' in joined:category='other archive template encoding'
        elif 'next_events(' in joined or 'first_root' in joined:category='event search call path'
        else:category='other or unavailable caller'
        categories[category]+=weight
    def rows(counter):return [{'name':name,'percent':value/total*100} for name,value in counter.most_common()]
    result={'samples':samples,'period_total':total,'binary':binary,'data':a.data,
            'method':'frame-pointer samples; ELF-relative addresses from perf mmap and nm; inclusive shares overlap',
            'call_path_categories':rows(categories),'leaf_modules':rows(leaves),'inclusive_symbols':rows(inclusive)}
    a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('samples','call_path_categories','leaf_modules')},indent=2))
    for row in result['inclusive_symbols'][:25]:print(f"{row['percent']:6.2f}% {row['name']}")


if __name__=='__main__':main()
