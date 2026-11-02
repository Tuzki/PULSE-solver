#!/usr/bin/env python3
"""Sequential fresh PLECS/optimized PULSE campaign; no original-PULSE timing."""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import platform
import subprocess
import sys


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case-set',type=pathlib.Path,required=True)
    p.add_argument('--out',type=pathlib.Path,required=True)
    p.add_argument('--win-event',type=pathlib.Path,required=True)
    p.add_argument('--linux-event',required=True)
    p.add_argument('--linux-source',required=True)
    p.add_argument('--native-out',required=True)
    p.add_argument('--repetitions',type=int,default=3)
    p.add_argument('--only',nargs='+',default=['rohm-c002-d-boost','rohm-a010-dot-totem-pole-pfc-sync'])
    a=p.parse_args();root=pathlib.Path(__file__).resolve().parents[1];a.out=a.out.resolve()
    a.out.mkdir(parents=True,exist_ok=True)
    if (a.out/'campaign.json').exists():raise ValueError('use a fresh campaign directory')
    def command(args,cwd=root):return subprocess.check_output(args,cwd=cwd,text=True,encoding='utf-8',errors='replace').strip()
    prefix=['wsl.exe','-d','Ubuntu-24.04','-u','root','--exec']
    data={'scope':'fresh PLECS and optimized PULSE only; all original channels and full durations',
          'utc_start':datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'source_parent':command(['git','rev-parse','HEAD']),
          'source_patch_sha256':hashlib.sha256(subprocess.check_output(['git','diff','--binary'],cwd=root)).hexdigest(),
          'case_set_commit':command(['git','rev-parse','HEAD'],a.case_set.resolve()),
          'environment':{'windows':platform.platform(),'processor':platform.processor(),'logical_cpus':os.cpu_count(),
                         'windows_gcc':command(['g++','--version']).splitlines()[0],
                         'linux_gcc':command(prefix+['g++','--version']).splitlines()[0],
                         'linux':command(prefix+['uname','-a'])},'repetitions':[]}
    def save():(a.out/'campaign.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    save()
    for i in range(1,a.repetitions+1):
        out=a.out/('run'+str(i));native=a.native_out+'/run'+str(i)
        args=[sys.executable,str(root/'scripts/benchmark_pevt_vs_plecs.py'),'--case-set',str(a.case_set.resolve()),
              '--out',str(out),'--win-event',str(a.win_event.resolve()),'--linux-event',a.linux_event,
              '--linux-source',a.linux_source,'--native-out',native,'--max-event-plecs-ratio','10','--include-waveform','--only']+a.only
        entry={'index':i,'command':args,'utc_start':datetime.datetime.now(datetime.timezone.utc).isoformat()}
        data['repetitions'].append(entry);save();print('CAMPAIGN REPETITION',i,flush=True)
        result=subprocess.run(args,cwd=root)
        entry['returncode']=result.returncode;entry['utc_end']=datetime.datetime.now(datetime.timezone.utc).isoformat();save()
        if result.returncode:
            data['stopped_reason']='Child benchmark stopped/failed; no subsequent repetition started.';save();return result.returncode
    data['utc_end']=datetime.datetime.now(datetime.timezone.utc).isoformat();data['finished']=True;save()
    print('CAMPAIGN FINISHED',flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
