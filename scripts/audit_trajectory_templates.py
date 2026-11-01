#!/usr/bin/env python3
"""Offline v1 template-bloat audit. Never invokes a solver or changes inputs.

The block pool below is a storage experiment, NOT a deployed trajectory format.
It interns exact typed binary values and arrays with 32-element leaf chunks, with
full lossless round-trip checks. It does not round or merge nearby numbers.
"""
import argparse
import hashlib
import json
import pathlib
import struct
import time


def templates(path):
    decoder=json.JSONDecoder()
    with path.open(encoding='utf-8') as f:
        buf=f.read(65536); pos=0
        if not buf.startswith('['): raise ValueError('template array required')
        pos=1
        while True:
            while pos<len(buf) and buf[pos] in ', \r\n\t': pos+=1
            if pos==len(buf):
                buf=f.read(65536);pos=0
                if not buf: raise ValueError('truncated template array')
                continue
            if buf[pos]==']':
                if (buf[pos+1:]+f.read()).strip(): raise ValueError('trailing data')
                return
            try: obj,end=decoder.raw_decode(buf,pos)
            except json.JSONDecodeError:
                more=f.read(65536)
                if not more: raise
                buf=buf[pos:]+more;pos=0;continue
            yield obj,len(buf[pos:end].encode('utf-8'))
            pos=end
            if pos>65536:buf=buf[pos:];pos=0


class ExactPool:
    def __init__(self): self.ids={};self.nodes=[];self.bytes=0
    def intern(self,b):
        found=self.ids.get(b)
        if found is not None:return found
        i=len(self.nodes);self.ids[b]=i;self.nodes.append(b);self.bytes+=4+len(b)
        return i
    def array(self,ids):
        if len(ids)>32:
            tag=b'A';ids=[self.array(ids[i:i+32]) for i in range(0,len(ids),32)]
        else:tag=b'a'
        return self.intern(tag+struct.pack('<I',len(ids))+b''.join(struct.pack('<I',i) for i in ids))
    def encode(self,x):
        if x is None:return self.intern(b'n')
        if isinstance(x,bool):return self.intern(b'b'+bytes([x]))
        if isinstance(x,int):return self.intern(b'i'+struct.pack('<q',x))
        if isinstance(x,float):return self.intern(b'f'+struct.pack('<d',x))
        if isinstance(x,str):return self.intern(b's'+x.encode('utf-8'))
        if isinstance(x,list):return self.array([self.encode(v) for v in x])
        return self.intern(b'o'+struct.pack('<I',self.array([
            self.array([self.encode(k),self.encode(v)]) for k,v in sorted(x.items())])))
    def decode(self,i):
        b=self.nodes[i];tag=b[:1]
        if tag==b'n':return None
        if tag==b'b':return bool(b[1])
        if tag==b'i':return struct.unpack('<q',b[1:])[0]
        if tag==b'f':return struct.unpack('<d',b[1:])[0]
        if tag==b's':return b[1:].decode('utf-8')
        if tag==b'o':return dict(self.decode(struct.unpack('<I',b[1:])[0]))
        count=struct.unpack('<I',b[1:5])[0]
        children=[self.decode(struct.unpack_from('<I',b,5+4*k)[0]) for k in range(count)]
        return [x for chunk in children for x in chunk] if tag==b'A' else children


def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')


def differences(a,b,path=''):
    if type(a)!=type(b):return [path]
    if isinstance(a,dict):return [p for k in a.keys()|b.keys() for p in (differences(a[k],b[k],path+'/'+k) if k in a and k in b else [path+'/'+k])]
    if isinstance(a,list):
        if len(a)!=len(b):return [path]
        return [p for i,(x,y) in enumerate(zip(a,b)) for p in differences(x,y,path+'/'+str(i))]
    # Preserve signed zero and all binary64 bits in the diagnostic too.
    if isinstance(a,float):return [] if struct.pack('<d',a)==struct.pack('<d',b) else [path]
    return [] if a==b else [path]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('templates',type=pathlib.Path)
    p.add_argument('--sample',type=int,default=10000)
    p.add_argument('--out',type=pathlib.Path,required=True)
    a=p.parse_args()
    if a.sample<=0:p.error('--sample must be positive')
    if a.out.exists():p.error('output exists; use a fresh output path')
    pool=ExactPool();fields={};examples=[];source_bytes=0;count=0;previous=None;start=time.perf_counter()
    # Synthetic values exercise signed zero, a 1-ULP difference and long arrays.
    test=[0.0,-0.0,1.0,struct.unpack('<d',struct.pack('<Q',0x3ff0000000000001))[0],list(range(100)),{'x':False}]
    assert canonical(pool.decode(pool.encode(test)))==canonical(test)
    pool=ExactPool()
    for i,(obj,size) in enumerate(templates(a.templates)):
        count+=1
        if i>=a.sample:continue
        source_bytes+=size;root=pool.encode(obj);restored=pool.decode(root)
        if canonical(restored)!=canonical(obj):raise ValueError('lossless round-trip failed at '+str(i))
        if previous is not None and i<=5:
            changes=differences(previous,obj)
            examples.append({'from':i-1,'to':i,'changed_leaves':len(changes),'first_changed_paths':changes[:12]})
        previous=obj
        for key,value in obj.items():
            b=canonical(value);d=hashlib.sha256(b).digest()
            info=fields.setdefault(key,{'serialized_bytes':0,'unique_bytes':0,'digests':set()})
            info['serialized_bytes']+=len(b)
            if d not in info['digests']:info['digests'].add(d);info['unique_bytes']+=len(b)
        if (i+1)%1000==0:print('AUDIT',i+1,'pool bytes',pool.bytes,flush=True)
    for info in fields.values():info['unique_values']=len(info.pop('digests'))
    sampled=min(count,a.sample);pooled=pool.bytes+4*sampled+24
    digest=hashlib.sha256()
    with a.templates.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):digest.update(block)
    result={'input':str(a.templates.resolve()),'input_bytes':a.templates.stat().st_size,'sha256':digest.hexdigest(),
      'total_templates':count,'sampled_templates':sampled,'original_sample_bytes':source_bytes,
      'prototype_pool_bytes_including_root_ids':pooled,'prototype_nodes':len(pool.nodes),
      'prototype_fraction':pooled/source_bytes,'roundtrip_checked':sampled,'roundtrip_failures':0,
      'synthetic_signed_zero_and_one_ulp_check':True,'adjacent_examples':examples,'fields':fields,
      'audit_wall_seconds':time.perf_counter()-start,
      'scope':'offline archive analysis only; no solver execution; prototype size is not measured full-case output or simulation speed'}
    a.out.parent.mkdir(parents=True,exist_ok=True)
    with a.out.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('fields','adjacent_examples')},indent=2),flush=True)


if __name__=='__main__':main()
