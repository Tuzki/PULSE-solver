"""Read-only parser for PLECS text model blocks, including base64 values."""
import base64
import collections
import hashlib
import json
from pathlib import Path
import re


def parse(lines,pos=0):
    out=[]
    while pos<len(lines):
        s=lines[pos].strip();pos+=1
        if not s:continue
        if s=='}':return out,pos
        if s.endswith('{'):
            children,pos=parse(lines,pos);out.append(dict(key=s[:-1].strip(),children=children))
        elif s.startswith('"') and out:
            out[-1]['raw']+=s
        else:
            m=re.match(r'(\S+)\s+(.*)',s)
            if m:out.append(dict(key=m[1],raw=m[2]))
    return out,pos


def value(raw):
    if raw.startswith('{'):return raw.replace('""','')
    strings=re.findall(r'"((?:\\.|[^"\\])*)"',raw)
    if raw.startswith('base64 '):return base64.b64decode(''.join(strings)).decode('utf-8')
    if raw.startswith('"'):
        return ''.join(strings).replace('\\n','\n').replace('\\"','"').replace('\\\\','\\')
    return raw


def scalar(block):return {x['key']:value(x['raw']) for x in block if 'raw' in x}
def subs(block,key):return [x['children'] for x in block if x['key']==key and 'children' in x]


def inventory(path):
    path=Path(path);root=parse(path.read_text().splitlines())[0][0]['children'];objects=[]
    def walk(schematic,parent=''):
        for component in subs(schematic,'Component'):
            c=scalar(component);c['path']=parent+c.get('Name','?')
            c['parameters']={scalar(p).get('Variable'):scalar(p).get('Value') for p in subs(component,'Parameter')}
            objects.append(c)
            for child in subs(component,'Schematic'):walk(child,c['path']+'/')
    walk(subs(root,'Schematic')[0])
    return dict(source=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),settings=scalar(root),
                types=dict(collections.Counter(c['Type'] for c in objects)),components=objects),root


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('manifest');p.add_argument('--out',required=True);a=p.parse_args()
    manifest=Path(a.manifest);out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    for sample in json.loads(manifest.read_text())['samples']:
        inv,root=inventory(manifest.parent/sample['models'][0]);key=sample['id']
        (out/(key+'.json')).write_text(json.dumps(inv,ensure_ascii=False,indent=2)+'\n')
        (out/(key+'.tree.json')).write_text(json.dumps(root,ensure_ascii=False,indent=2)+'\n')
        (out/(key+'.m')).write_text(inv['settings']['InitializationCommands'])
        print(key,len(inv['components']),json.dumps(inv['types'],ensure_ascii=False))
