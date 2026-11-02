"""Independent protocol layout and runtime-history checks; no NumPy required."""
import argparse,json,pathlib,struct,subprocess,sys,hashlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from read_pevt import read

p=argparse.ArgumentParser();p.add_argument('--scratch',type=pathlib.Path,required=True);p.add_argument('--replay',required=True);a=p.parse_args()
for name in ('linear_rc','buck_ccm','boost_dcm'):
    directory=a.scratch/name;data=read(directory);expected=json.loads((directory/'expected-slices.json').read_text())
    assert len(data['events'])==len(expected)+1
    def modes(ids):
        bools={};regions={}
        for mode in ids:
            d=data['meta']['component_modes'][mode]['definition']
            if d['kind']=='REGION':regions[d['source_part_index']]=d['value']
            elif d['signal'] and d['signal'] not in ('0','1'):bools[d['signal']]=bool(d['value'])
        return bools,regions
    for i,want in enumerate(expected):
        e=data['events'][i];state=data['states'][e['state_id']];parts=want['time'].split(':');t=(int(parts[1]),int(parts[2],16),int(parts[3],16))
        assert tuple(e['time'])==t
        assert struct.pack('<'+'d'*len(state['x']),*state['x'])==struct.pack('<'+'d'*len(want['x']),*want['x'])
        b,r=modes(e['after_components']);assert b==want['bools'] and r==dict(want['regions'])
        b,r=modes(e['before_components']);prior=expected[max(i-1,0)];assert b==prior['bools'] and r==dict(prior['regions'])
    # Invalid reference with a valid checksum must fail semantic validation.
    bad=a.scratch/(name+'-bad-reference.pevt');sections=data['sections'];output=bytearray(struct.pack('<8sHHI',b'PULSEES1',1,len(sections),0))
    for kind,(count,payload) in sorted(sections.items()):
        payload=bytearray(payload)
        if kind==7:struct.pack_into('<I',payload,48,0xffffffff)
        output+=struct.pack('<IIQQQ32s',kind,0,len(payload),len(payload),count,hashlib.sha256(payload).digest())+payload
    bad.write_bytes(output)
    result=subprocess.run([a.replay,str(bad),'--out',str(a.scratch/(name+'-invalid-output'))],capture_output=True,text=True)
    assert result.returncode!=0 and 'PEVT_REFERENCE' in result.stderr,result.stderr
print('Protocol headers, checksums, references and every runtime event slice verified independently.')
