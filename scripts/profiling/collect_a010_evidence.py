#!/usr/bin/env python3
"""Collect timing ledgers, checked archive section metadata, and host evidence."""
import gzip
import hashlib
import json
import pathlib
import platform
import struct
import subprocess
import sys

root=pathlib.Path(sys.argv[1]);source=pathlib.Path(sys.argv[2])

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()

def archive(path):
    result={'path':str(path),'bytes':path.stat().st_size,'sections':[]};meta=None
    with path.open('rb') as f:
        magic,version,count,flags=struct.unpack('<8sHHI',f.read(16))
        assert magic==b'PULSEES1' and version==1 and flags==0
        for _ in range(count):
            kind,codec,stored,decoded,n,expected=struct.unpack('<IIQQQ32s',f.read(64))
            b=f.read(stored);payload=gzip.decompress(b) if codec==1 else b
            assert len(payload)==decoded and hashlib.sha256(payload).digest()==expected
            result['sections'].append({'kind':kind,'codec':codec,'records':n,'bytes':stored,'sha256':expected.hex()})
            if kind==1:meta=json.loads(payload)
        assert not f.read(1)
    result['archive_counts']=meta['provenance']['archive_counts']
    result['archive_signal_count']=len(meta['signals'])
    result['archive_signal_names']=[s['name'] for s in meta['signals']]
    return result

ledgers={}
sources=[('campaign',root/'linux-campaign/ledger.json'),('sampling',root/'linux-sampling/run/ledger.json')]
if (root/'linux-call-counts/run/ledger.json').exists():sources.append(('call_counts',root/'linux-call-counts/run/ledger.json'))
for label,path in sources:
    ledger=json.loads(path.read_text())
    for r in ledger['runs']:
        if r['label'].startswith('reconstruction'):
            r['scope']='excluded from analysis by user scope update; raw completed work retained'
            continue
        assert r['returncode']==0 and r['report']['status']=='COMPLETED'
        assert r['report']['source_sha256']=='e820d1dcb9a84707d6f2333ee965ef188e7be78f5a55511cb963f8e71601ab60'
        r['archive']=archive(pathlib.Path(r['output_path'])/'out.pevt')
        public=r['report']['analog_channels']+r['report']['digital_channels']
        assert len(public)==17 and set(public)<=set(r['archive']['archive_signal_names'])
    ledgers[label]=ledger
commands=[['uname','-a'],['g++','--version'],['cmake','--version'],['ninja','--version'],
          ['/usr/lib/linux-tools/6.8.0-147-generic/perf','version','--build-options'],
          ['dpkg-query','-W','libc6','libstdc++6','libssl3t64','linux-tools-generic']]
machine={'platform':platform.platform(),'cpuinfo':pathlib.Path('/proc/cpuinfo').read_text(),
         'meminfo':pathlib.Path('/proc/meminfo').read_text(),'os_release':pathlib.Path('/etc/os-release').read_text(),
         'commands':[{ 'command':c,'output':subprocess.check_output(c,text=True)} for c in commands]}
files={}
for path in root.rglob('*'):
    if path.is_file() and 'reconstruction_500ms_off' not in str(path) and path.name!='collected.json':
        files[str(path.relative_to(root))]={'bytes':path.stat().st_size,'sha256':digest(path),'absolute_path':str(path)}
result={'solver_baseline':'6e5dea9bc5f7c03a5258a738725df474433a20b5','validated_base':'186c9ed37bd11aa39d24fc2a769a8898a389068c',
        'scope':'Linux only; simulation compute and complete trajectory generation; reconstruction excluded',
        'core_source_changed':False,'machine':machine,'ledgers':ledgers,'raw_artifacts':files,
        'source_compile_commands':json.loads((source/'build-profile/compile_commands.json').read_text())}
(root/'collected.json').write_text(json.dumps(result,indent=2)+'\n')
print('Collected',len(files),'raw files; all trajectory section digests checked; 17 channels retained.')
