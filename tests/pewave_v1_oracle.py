#!/usr/bin/env python3
import json,sys,zipfile,hashlib
import numpy as np

def check(path, ref=False):
    with np.load(path, allow_pickle=False) as f:
        names=set(f.files)
        t=f['time']; m=json.loads(f['metadata_json'].item())
        assert m['format']=='PEWave' and m['version']==1, m.get('format')
        assert t.ndim==1 and t.dtype==np.float64 and np.all(np.diff(t)>0)
        assert m['time']['count']==len(t)==f['time'].shape[0]
        assert m['time']['t_end']==float(t[-1])
        sigs=m['signals']; ids=[s['id'] for s in sigs]
        assert len(ids)==len(set(ids))
        assert int(m['available_signal_count'])>=len(ids)
        assert int(m['exported_signal_count'])==len(ids)
        used=set()
        analog=0; digital=0
        for s in sigs:
            assert {'id','name','unit','kind','axis','dtype'} <= set(s), s
            a=f[s['id']]
            assert a.ndim==1 and len(a)==len(t), (s['id'],a.shape,len(t))
            assert str(a.dtype)==s['dtype'], (s['id'],a.dtype,s['dtype'])
            assert a.dtype in (np.dtype('float32'),np.dtype('uint8'))
            used.add(s['id'])
            if a.dtype==np.uint8:
                assert set(np.unique(a)).issubset({0,1}), (s['id'],np.unique(a))
                digital+=1
            else: analog+=1
        assert names == used | {'time','metadata_json'}, (names-used, used-names)
        assert len(sigs)==analog+digital
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        for n in z.namelist():
            data=z.read(n)
            assert data[:6]==b'\x93NUMPY'
            assert data[6:8]==bytes([1,0])
    return {'path':path,'samples':len(t),'t_end':float(t[-1]),'signals':len(sigs),'analog':analog,'digital':digital,'sha256':hashlib.sha256(open(path,'rb').read()).hexdigest()}
if __name__=='__main__':
    for p in sys.argv[1:]: print(json.dumps(check(p),indent=2))
