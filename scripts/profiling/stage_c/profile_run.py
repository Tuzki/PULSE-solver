#!/usr/bin/env python3
"""External Linux profiling harness. Never changes solver sources or inputs."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import struct
import subprocess
import threading
import time


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()


def offset(path,address):
    with Path(path).open('rb') as f:
        header=f.read(64)
        assert header[:6]==b'\x7fELF\x02\x01'
        start=struct.unpack_from('<Q',header,32)[0]
        size,count=struct.unpack_from('<HH',header,54)
        f.seek(start)
        for _ in range(count):
            p=f.read(size);kind,flags,off,va,_,length=struct.unpack_from('<IIQQQQ',p)
            if kind==1 and va<=address<va+length:return off+address-va
    raise ValueError(('Unmapped ELF address',path,hex(address)))


def symbols(binary):
    lines=subprocess.check_output(['nm','-S','-n','--defined-only',str(binary)],text=True).splitlines()
    rows=[]
    for line in lines:
        p=line.split()
        if len(p)==4 and p[2] in ('t','T','W','w'):
            rows.append({'address':int(p[0],16),'size':int(p[1],16),'symbol':p[3]})
    names=subprocess.check_output(['c++filt'],input='\n'.join(r['symbol'] for r in rows)+'\n',text=True).splitlines()
    for row,name in zip(rows,names):row['function']=name
    return rows


def make_manifest(binary,controller,out):
    rows=symbols(binary)
    selectors=[
      ('observe','pulse::engineering::Flow::observe(',True,None),
      ('bind_observations','::bind_observations(',True,None),
      ('flow_ctor','pulse::engineering::Flow::Flow(pulse::Mode const&',True,'observe'),
      ('flow_compatible','pulse::engineering::Flow::compatible(',False,None),
      ('flow_continued','pulse::engineering::Flow::continued_after_check(',False,None),
      ('flow_state','pulse::engineering::Flow::state(',False,None),
      ('flow_value','pulse::engineering::Flow::value(',False,None),
      ('flow_bounds','pulse::engineering::Flow::bounds(',False,None),
      ('closure','::closure(',True,None),
      ('roots','pulse::engineering::next_events(',True,None),
      ('fingerprint','pulse::event_fingerprint(',False,None),
      ('agenda_check','::check_agenda_origins(',False,None),
      ('changed_edges','pulse::EventKernel::changed_edges[',False,None),
      ('mode_compile','pulse::compile_specified(',False,None),
      ('portfolio_compile','pulse::portfolio_compile(',False,None),
      ('portfolio_mode','pulse::portfolio_mode(',False,None),
      ('original_check','pulse::portfolio_original_check(',False,None),
      ('cow_binding_edit','pulse::CowValue<pulse::ModeBinding>::edit(',False,'bind_observations'),
      ('mode_copy','pulse::Mode::Mode(pulse::Mode const&)',False,'bind_observations'),
      ('time_from','pulse::Time::from(',False,None),
      ('time_times','pulse::Time::times(',False,None),
      ('time_canonical','pulse::Time::canonical[',False,None),
      ('decimal_binary','pulse::decimal_origin_from_binary_time(',True,None),
      ('decimal_parse','pulse::parse_decimal_origin(',False,None),
      ('decimal_add','pulse::add_decimal_origins(',False,None),
      ('decimal_times','pulse::times_decimal_origin(',False,None),
      ('decimal_compare','pulse::compare_decimal_origins(',False,None),
      ('decimal_canonical','pulse::canonical_decimal_origin[',False,None),
      ('software_call','pulse::software::Data::call(',False,None),
      ('software_execute','pulse::software::Session::execute(',False,None),
      ('archive_equation','pulse::PevtArchive::Data::equation(',False,None),
      ('archive_compare','pulse::PevtArchive::Data::same_archive_definition(',False,None),
      ('archive_append','pulse::PevtArchive::Data::append(',True,None),
      ('archive_write','pulse::PevtArchive::write(',True,None),
    ]
    manifest=[];missing=[];seen=set()
    for label,needle,timing,parent in selectors:
        found=[r for r in rows if r['function'].startswith('pulse::') and needle in r['function'] and '[clone' not in r['function'] and '::{lambda' not in r['function']]
        if label=='software_execute':found=[r for r in found if 'CowValue' in r['function']]
        if not found:missing.append(label);continue
        unique={r['address']:r for r in found}
        assert len(unique)==1,(label,list(unique.values()))
        row=next(iter(unique.values())).copy()
        if row['address'] in seen:continue
        seen.add(row['address']);row.update(label=label,path=str(binary),timing=timing,parent=parent)
        row['offset']=offset(binary,row['address']);manifest.append(row)
    # Count the actual copy branch, not every edit() call. Pin this disassembly
    # to the frozen machine code; refuse another layout instead of guessing.
    edit=next(r for r in manifest if r['label']=='cow_binding_edit')
    assert edit['address']==0x115550,'Re-verify COW detach instruction on this binary'
    with binary.open('rb') as f:
        f.seek(offset(binary,0x115590));assert f.read(5)==bytes.fromhex('bfa0000000')
    manifest.append({'label':'cow_binding_detach','function':'CowValue<ModeBinding>::edit() actual detach branch',
                     'address':0x115590,'size':0,'symbol':'instruction+0x40','path':str(binary),
                     'offset':offset(binary,0x115590),'timing':False,'parent':'bind_observations'})
    if controller:
        for row in symbols(controller):
            if row['function'] in ('controller_step','controller_init'):
                row.update(label=row['function'],path=str(controller),timing=False,parent=None,offset=offset(controller,row['address']))
                manifest.append(row)
    indexes={r['label']:i for i,r in enumerate(manifest)}
    assert not missing,('Required outlined entry absent',missing)
    out.write_text(''.join(f"{r['label']}\t{r['path']}\t{r['offset']:x}\t{indexes[r['parent']] if r['parent'] else -1}\t{int(r['timing'])}\n" for r in manifest))
    out.with_suffix('.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('binary','model','perf','counter','observer','controller','out'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--duration',default='.5');p.add_argument('--frequency',type=int,default=499)
    p.add_argument('--no-counts',action='store_true');p.add_argument('--timeout',type=float,default=1800)
    p.add_argument('--no-observer',action='store_true')
    p.add_argument('--io-trace',action='store_true')
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    a.binary=a.binary.resolve();a.out=a.out.resolve()
    manifest=make_manifest(a.binary,a.controller.resolve(),a.out/'probes.tsv')
    command=[str(a.binary),str(a.model), '--t-end',a.duration,'--output-format','trajectory','--out',str(a.out/'run')]
    (a.out/'run').mkdir()
    env=os.environ.copy();env.pop('PULSE_PROFILE_PHASES',None);env.pop('PULSE_WALL_SECONDS',None)
    if not a.no_observer:
        env['LD_PRELOAD']=str(a.observer);env['PULSE_ALLOC_REPORT']=str(a.out/'allocations.json')
    else:
        env.pop('LD_PRELOAD',None);env.pop('PULSE_ALLOC_REPORT',None)
    readfd,writefd=os.pipe();pid=os.fork()
    if pid==0:
        os.close(readfd);os.dup2(writefd,1);os.close(writefd)
        err=os.open(a.out/'solver-stderr.txt',os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o644);os.dup2(err,2);os.close(err)
        os.kill(os.getpid(),signal.SIGSTOP);os.execve(a.binary,command,env)
    os.close(writefd);os.waitpid(pid,os.WUNTRACED)
    helper=None;sampler=None;io_tracer=None;telemetry=[];telemetry_errors=[];finished=threading.Event();notification=[None];output=[]
    before_io={}
    started=None
    def monitor():
        root=Path('/proc')/str(pid)
        while not finished.wait(.1):
            try:
                status=dict(line.split(':',1) for line in (root/'status').read_text().splitlines() if ':' in line)
                stat=(root/'stat').read_text().split(') ',1)[1].split()
                io={k:int(v) for k,v in (line.split(':') for line in (root/'io').read_text().splitlines())} if (root/'io').exists() else None
                telemetry.append({'elapsed_seconds':time.perf_counter()-started,'threads':int(status['Threads']),
                    'rss_kib':int(status.get('VmRSS','0 kB').split()[0]),'peak_rss_kib':int(status.get('VmHWM','0 kB').split()[0]),
                    'cpu_user_ticks':int(stat[11]),'cpu_system_ticks':int(stat[12]),'io':io})
            except (OSError,KeyError,ProcessLookupError,ValueError) as error:
                telemetry_errors.append(repr(error))
                if isinstance(error,(FileNotFoundError,ProcessLookupError)):break
    def reader():
        with os.fdopen(readfd,'r') as f:
            for line in f:
                output.append(line)
                if line.startswith('  "status":') and '"COMPLETED"' in line:notification[0]=time.perf_counter()-started
    try:
        if not a.no_counts:
            err=(a.out/'counter-stderr.txt').open('w')
            possible=Path('/sys/devices/system/cpu/possible').read_text().strip();cpus=int(possible.split('-')[-1])+1
            helper=subprocess.Popen([str(a.counter),str(pid),str(a.out/'probes.tsv'),str(a.out/'counts.json'),str(cpus)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err,text=True)
            ready=helper.stdout.readline();(a.out/'counter-ready.txt').write_text(ready)
            assert ready.startswith('READY'),(a.out/'counter-stderr.txt').read_text()
        if a.io_trace:
            io_command=[str(a.perf),'trace','-S','-p',str(pid),'-e','write,writev,fsync,fdatasync','-o',str(a.out/'io-trace.txt')]
            err=(a.out/'io-trace-stderr.txt').open('w')
            io_tracer=subprocess.Popen(io_command,stdout=err,stderr=err)
        perf_command=[str(a.perf),'record','-e','cpu-clock','-F',str(a.frequency),'--call-graph','dwarf,32768','-m','4096','-o',str(a.out/'perf.data'),'-p',str(pid)]
        with (a.out/'perf-stdout.txt').open('w') as out,(a.out/'perf-stderr.txt').open('w') as err:
            sampler=subprocess.Popen(perf_command,stdout=out,stderr=err)
        for _ in range(200):
            if sampler.poll() is not None:raise RuntimeError((a.out/'perf-stderr.txt').read_text())
            links=[]
            for f in Path('/proc',str(sampler.pid),'fd').iterdir():
                try:links.append(os.readlink(f))
                except FileNotFoundError:pass
            if any('perf_event' in link for link in links):break
            time.sleep(.025)
        else:raise RuntimeError('perf did not attach')
        time.sleep(.1)
        threads=[];started=time.perf_counter();utc=datetime.datetime.now(datetime.timezone.utc).isoformat()
        for target in (monitor,reader):
            t=threading.Thread(target=target,daemon=True);t.start();threads.append(t)
        os.kill(pid,signal.SIGCONT)
        deadline=time.monotonic()+a.timeout
        while True:
            waited,status,usage=os.wait4(pid,os.WNOHANG)
            if waited:break
            if time.monotonic()>deadline:os.kill(pid,signal.SIGKILL);waited,status,usage=os.wait4(pid,0);raise TimeoutError('Profiling exceeded limit')
            time.sleep(.025)
        elapsed=time.perf_counter()-started;finished.set()
        for t in threads:t.join(timeout=5)
        (a.out/'stdout.json').write_text(''.join(output))
        row={'pid':pid,'started_utc':utc,'command':command,'perf_command':perf_command,'duration':a.duration,
             'completion_wall_seconds':notification[0],'exit_wall_seconds':elapsed,
             'returncode':os.waitstatus_to_exitcode(status),'cpu_user_seconds':usage.ru_utime,'cpu_system_seconds':usage.ru_stime,
             'cpu_total_seconds':usage.ru_utime+usage.ru_stime,'peak_rss_kib':usage.ru_maxrss,
             'peak_threads_observed':max((r['threads'] for r in telemetry),default=None),'thread_poll_interval_seconds':.1,
             'binary_sha256':digest(a.binary),'model_sha256':digest(a.model),'allocation_observer_sha256':digest(a.observer) if not a.no_observer else None,
             'counter_enabled':not a.no_counts,'cpu_scope':'target process through exit; gate setup excluded from wall; RSS includes observer',
             'environment':{k:env[k] for k in ('LD_PRELOAD','PULSE_ALLOC_REPORT') if k in env}}
        (a.out/'measurement.json').write_text(json.dumps(row,indent=2)+'\n')
        (a.out/'telemetry.json').write_text(json.dumps(telemetry,indent=2)+'\n')
        (a.out/'telemetry-errors.json').write_text(json.dumps(telemetry_errors,indent=2)+'\n')
        assert row['returncode']==0 and notification[0] is not None,row
        print(json.dumps(row,indent=2),flush=True)
    finally:
        finished.set()
        if sampler and sampler.poll() is None:sampler.send_signal(signal.SIGINT);sampler.wait(timeout=30)
        if io_tracer and io_tracer.poll() is None:io_tracer.send_signal(signal.SIGINT);io_tracer.wait(timeout=30)
        if helper and helper.poll() is None:helper.communicate('\n',timeout=30)
        try:os.kill(pid,signal.SIGKILL)
        except ProcessLookupError:pass
    if not a.no_counts:
        counts=json.loads((a.out/'counts.json').read_text())
        for q,m in zip(counts['probes'],manifest):
            assert q['collisions']==q['unmatched_returns']==q['map_errors']==0,q
            if m['timing']:assert q['entries']==q['returns'],q
        bind=next(q for q in counts['probes'] if q['label']=='bind_observations')
        assert sum(q['bindings'] for q in counts['observer_binding_identities'])==bind['entries']
    report=json.loads((a.out/'run/simulation_report.json').read_text())
    assert report['status']=='COMPLETED' and len(report['analog_channels'])==13 and len(report['digital_channels'])==4
    assert report['source_sha256']=='ad516d111e95fdcf9bf226da40bee4ceabc1bc069ad9b308b3d2bbf49bb9b642'


if __name__=='__main__':main()
