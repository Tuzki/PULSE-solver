#!/usr/bin/env python3
"""Independent stdlib-only parser/validator for the PULSEES1 protocol."""
import argparse
import gzip
import hashlib
import json
import math
import pathlib
import struct
import copy


class Cursor:
    def __init__(self,b):self.b=b;self.p=0
    def get(self,fmt):
        fmt='<'+fmt;n=struct.calcsize(fmt)
        if self.p+n>len(self.b):raise ValueError('truncated record')
        x=struct.unpack_from(fmt,self.b,self.p);self.p+=n
        return x[0] if len(x)==1 else x
    def vector(self,n):
        x=[self.get('d') for _ in range(n)]
        if not all(map(math.isfinite,x)):raise ValueError('nonfinite value')
        return x
    def end(self):
        if self.p!=len(self.b):raise ValueError('record count/section length mismatch')


def read(path):
    path=pathlib.Path(path);path=path/'out.pevt' if path.is_dir() else path
    raw=path.read_bytes();c=Cursor(raw);magic,version,count,flags=c.get('8sHHI')
    if magic!=b'PULSEES1' or version!=1 or flags or not 9<=count<=10:raise ValueError('invalid file header')
    sections={};headers=[]
    for _ in range(count):
        kind,codec,stored,decoded,n,sha=c.get('IIQQQ32s')
        if kind in sections or kind not in range(1,11) or stored>len(raw)-c.p:raise ValueError('invalid section')
        b=raw[c.p:c.p+stored];c.p+=stored
        if codec==1:b=gzip.decompress(b)
        elif codec!=0:raise ValueError('unknown codec')
        if len(b)!=decoded or hashlib.sha256(b).digest()!=sha:raise ValueError('section SHA256/length mismatch')
        sections[kind]=(n,b);headers.append({'type':kind,'codec':codec,'records':n,'stored_bytes':stored,'decoded_bytes':decoded,'sha256':sha.hex()})
    c.end()
    if not set(range(1,10))<=sections.keys():raise ValueError('missing section')
    def js(i):
        if sections[i][0]!=1:raise ValueError('JSON record count')
        return json.loads(sections[i][1])
    m,defs,end=js(1),js(3),js(9);nx,np,nm=[m[k] for k in ('state_dimension','value_slot_count','modal_component_count')]
    for key,n in [('state_layout',nx),('value_slots',np),('modal_components',nm)]:
        if len(m[key])!=n:raise ValueError('schema dimension differs')
    matrices=[];d=Cursor(sections[2][1])
    for i in range(sections[2][0]):
        bid,r,col=d.get('III')
        if bid!=i or r*col>1000000:raise ValueError('invalid numeric block')
        matrices.append({'rows':r,'cols':col,'data':d.vector(r*col)})
    d.end();values=[];d=Cursor(sections[4][1])
    for i in range(sections[4][0]):
        if d.get('I')!=i:raise ValueError('value ID order')
        values.append(d.vector(np))
    d.end();instances=[];d=Cursor(sections[5][1])
    for i in range(sections[5][0]):
        eid,definition,vs=d.get('III')
        if eid!=i or definition>=len(defs) or vs>=len(values):raise ValueError('equation reference')
        instances.append((definition,vs))
    d.end();states=[];d=Cursor(sections[6][1])
    for i in range(sections[6][0]):
        if d.get('I')!=i:raise ValueError('state ID order')
        x=d.vector(nx);vs=d.get('I')
        if vs>=len(values):raise ValueError('state values reference')
        states.append({'x':x,'value_set_id':vs})
    d.end()
    for i,definition in enumerate(defs):
        if definition['definition_id']!=i:raise ValueError('definition ID order')
        for name in ('state_matrix','invariant_lift','invariant_generator','invariant_reduce','constraints','residual_map','residual_reference'):
            if definition[name]>=len(matrices):raise ValueError('matrix reference')
        main=matrices[definition['state_matrix']]
        if (main['rows'],main['cols'])!=(nx,nx):raise ValueError('state matrix shape')
        for b in definition['dynamic_bindings']:
            block=matrices[b['target_block_id']]
            if not(0<=b['slot_id']<np and b['row']<block['rows'] and b['col']<block['cols']):raise ValueError('invalid dynamic binding')
        for row in definition['observation_rows']:
            if row['signal_id']>=len(m['signals']):raise ValueError('signal reference')
            block=matrices[row['row_block_id']]
            if (block['rows'],block['cols'])!=(nx,1):raise ValueError('observation shape')
    flows=[];d=Cursor(sections[8][1])
    for i in range(sections[8][0]):
        fid,reference,origin,state,equation,whole,tick,sub=d.get('IQQIIqQQ')
        if fid!=i or state>=len(states) or equation>=len(instances) or whole<0:raise ValueError('invalid Flow record')
        flows.append({'reference':reference,'origin':origin,'state':state,'equation':equation,'offset':(whole,tick,sub)})
    d.end();events=[];d=Cursor(sections[7][1]);modal=m['component_modes']
    for i in range(sections[7][0]):
        eid=d.get('Q');t=d.get('qQQ');txn=d.get('Q');micro,kind,state,before,after,observer,outgoing=d.get('IIIIIII')
        pre=[d.get('I') for _ in range(nm)];post=[d.get('I') for _ in range(nm)];members=[d.get('II') for _ in range(d.get('I'))]
        if eid!=i or t[0]<0 or kind not in range(1,7) or state>=len(states) or before>=len(instances) or after>=len(instances):raise ValueError('invalid event')
        if events and (t,txn,micro,eid)<events[-1]['order']:raise ValueError('event order')
        for modes,eq in [(pre,before),(post,after)]:
            if modes!=defs[instances[eq][0]]['component_mode_ids']:raise ValueError('event/equation component mode mismatch')
            for j,mode in enumerate(modes):
                if mode>=len(modal) or modal[mode]['component_id']!=m['modal_components'][j]:raise ValueError('component mode reference')
        if states[state]['value_set_id']!=instances[after][1]:raise ValueError('state slice is not complete post-mode values')
        for f in (observer,outgoing):
            if f!=0xffffffff and (f>=len(flows) or flows[f]['reference']!=eid):raise ValueError('event Flow reference')
        for cid,k in members:
            if cid>=len(m['components']) or k not in range(1,7):raise ValueError('event member')
        events.append({'id':eid,'time':t,'order':(t,txn,micro,eid),'kind':kind,'state_id':state,'before':before,'after':after,'observer':observer,'outgoing':outgoing,'before_components':pre,'after_components':post,'members':members})
    d.end()
    if not events or events[0]['kind']!=1 or events[-1]['kind']!=6 or end['last_event_id']!=len(events)-1:raise ValueError('initial/end record')
    for f in flows:
        if not(0<=f['origin']<=f['reference']<len(events)) or events[f['origin']]['state_id']!=f['state']:raise ValueError('Flow origin reference')
    diagnostics=[]
    if 10 in sections:
        diagnostics=[json.loads(line) for line in sections[10][1].splitlines() if line]
        if len(diagnostics)!=sections[10][0]:raise ValueError('diagnostic record count')
    return {'meta':m,'definitions':defs,'matrices':matrices,'values':values,'instances':instances,'states':states,'events':events,'flows':flows,'end':end,'diagnostics':diagnostics,'sections':sections,'headers':headers}


def summary(data):
    return {'format':'PULSEES1','valid':True,'status':data['end']['status'],'sections':data['headers'],
            'counts':{k:len(data[k]) for k in ('definitions','matrices','values','instances','states','events','flows','diagnostics')},
            'state_dimension':data['meta']['state_dimension'],'last_time_T128':data['events'][-1]['time'],
            'single_state_per_event':True,'complete_component_modes':True,'all_references_valid':True}


def equation(data,index):
    """Materialize coefficient/mode fields independently from the native reader."""
    definition,vs=data['instances'][index];d=data['definitions'][definition];changed={}
    for b in d['dynamic_bindings']:
        i=b['target_block_id']
        if i not in changed:changed[i]=copy.deepcopy(data['matrices'][i])
        block=changed[i];block['data'][b['row']+b['col']*block['rows']]=data['values'][vs][b['slot_id']]
    def block(i):return copy.deepcopy(changed.get(i,data['matrices'][i]))
    mode={old:block(d[new]) for old,new in [('M','state_matrix'),('lift','invariant_lift'),('generator','invariant_generator'),('reduce','invariant_reduce'),('constraints','constraints'),('residual_map','residual_map'),('residual_reference','residual_reference')]}
    mode.update({'observations':{'rows':0,'cols':0,'data':[]},'strategy':d['numerical_strategy'],'maps':{},'bools':{},'segments':[],'guards':[]})
    for row in d['observation_rows']:mode['maps'][data['meta']['signals'][row['signal_id']]['name']]=block(row['row_block_id'])
    regions={}
    for i in d['component_mode_ids']:
        item=data['meta']['component_modes'][i]['definition']
        if item['kind']=='REGION':regions[item['source_part_index']]=item['value']
        elif item['signal'] and item['signal'] not in ('0','1'):mode['bools'][item['signal']]=bool(item['value'])
    mode['segments']=[list(x) for x in sorted(regions.items())]
    for g in d['guards']:
        value={k:g[k] for k in ('direction','kind','knot','segment','step')};value['row']=block(g['row_block_id']);value['part']=data['meta']['components'][g['component_id']]['source_part_index'];mode['guards'].append(value)
    return mode


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('file',type=pathlib.Path);p.add_argument('--out',type=pathlib.Path)
    a=p.parse_args();result=summary(read(a.file));text=json.dumps(result,indent=2)+'\n'
    if a.out:a.out.write_text(text,encoding='utf-8')
    print(text)


if __name__=='__main__':main()
