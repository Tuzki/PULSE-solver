#!/usr/bin/env python3
"""Read-only /proc telemetry for an already running profiling target."""
import argparse
import datetime
import json
import os
import pathlib
import time

p=argparse.ArgumentParser();p.add_argument('--binary',required=True);p.add_argument('--out',type=pathlib.Path,required=True)
a=p.parse_args();target=None
for d in pathlib.Path('/proc').iterdir():
    if not d.name.isdigit():continue
    try:cmd=(d/'cmdline').read_bytes().split(b'\0')
    except (FileNotFoundError,PermissionError):continue
    if cmd and cmd[0].decode(errors='replace')==a.binary:
        target=d;break
if target is None:raise SystemExit('Target not running')
hz=os.sysconf('SC_CLK_TCK');rows=[]
while True:
    try:
        stat=(target/'stat').read_text();fields=stat[stat.rfind(')')+2:].split()
        status=dict(line.split(':',1) for line in (target/'status').read_text().splitlines() if ':' in line)
        rows.append({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'monotonic':time.monotonic(),
                     'cpu_user_seconds':int(fields[11])/hz,'cpu_system_seconds':int(fields[12])/hz,
                     'rss_kb':int(status.get('VmRSS','0 kB').split()[0]),'hwm_kb':int(status.get('VmHWM','0 kB').split()[0]),
                     'threads':int(status['Threads'])})
    except FileNotFoundError:break
    time.sleep(1)
result={'pid':int(target.name),'clock_ticks_per_second':hz,'scope':'1Hz read-only telemetry; attached after target start; observed HWM is a lower bound on final process peak','samples':rows}
a.out.write_text(json.dumps(result,indent=2)+'\n');print('Telemetry points:',len(rows))
