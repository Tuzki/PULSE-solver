"""Native Windows PULSE vs live PLECS RPC comparison; frozen library stays read-only."""
import argparse
import copy
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
import traceback
import xmlrpc.client
from zipfile import ZipFile

PROJECT = Path(__file__).resolve().parents[1]
TOOLS = Path(r'D:\codex\tool\pulse-win\python')
if TOOLS.exists(): sys.path.insert(0, str(TOOLS))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

LIBRARY = Path(r'D:\codex\pulses-compare-base\pulses-compare-base')
sys.path.insert(0, str(LIBRARY / 'tools'))
# Prefer the independently validated primitive mappings; frozen library stays read-only.
sys.path.insert(0, str(PROJECT / 'tools' / 'plecs_conversion'))
from plecs_text import inventory, parse, scalar, subs
from convert_rohm import Converter
from rohm_model import number
from compare import read_wave, mode_statistics


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def serialize(nodes, depth=0):
    lines = []
    for node in nodes:
        indent = '  '*depth
        if 'children' in node:
            lines.append(indent + node['key'] + ' {')
            lines.append(serialize(node['children'], depth+1))
            lines.append(indent + '}')
        else:
            lines.append(indent + f"{node['key']:<24} " + node['raw'])
    return '\n'.join(lines)


def capture_model(source, dest, channels):
    shutil.copytree(source.parent, dest, dirs_exist_ok=True)
    # Some unpacked case folders omit Unicode-named thermal XML files; restore
    # their exact bytes from the case's frozen vendor archive into this run only.
    restored=[]
    assets=dest/(source.stem+'_plecs')
    for archive in sorted((source.parent.parent/'archive').glob('*.zip')):
        with ZipFile(archive) as z:
            for item in z.infolist():
                if item.filename.lower().endswith('.xml') and (source.stem+'_plecs/') in item.filename:
                    relative=item.filename.split(source.stem+'_plecs/',1)[1]
                    target=(assets/relative).resolve()
                    if not target.is_relative_to(assets.resolve()):raise ValueError('Unsafe archive path')
                    target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(z.read(item))
                    restored.append({'path':str(target.relative_to(dest)),'sha256':sha(target),'archive_sha256':sha(archive)})
    dump(dest/'restored_thermal_files.json',restored)
    tree = parse(source.read_text(encoding='utf-8-sig').splitlines())[0]
    root = tree[0]['children']
    schematic = subs(root, 'Schematic')[0]
    extra = []
    connections = []
    terminals = []
    for i,ch in enumerate(channels,1):
        target = ch['plecs_component']
        parent, _, component = target.rpartition('/')
        q = lambda s: json.dumps(s, ensure_ascii=False)
        snippet = f'''Component {{
  Type PlecsProbe
  Name "WIN_PROBE_{i}"
  Show off
  Position [5000, {1000+40*i}]
  Direction right
  Flipped off
  LabelPosition south
  Probe {{
    Component {q(component)}
    Path {q(parent)}
    Signals {{{q(ch['plecs_signal'])}}}
  }}
}}
Component {{
  Type Output
  Name "WIN_OUT_{i}"
  Show off
  Position [5100, {1000+40*i}]
  Direction right
  Flipped off
  LabelPosition south
  Parameter {{
    Variable "Index"
    Value "{i}"
    Show off
  }}
  Parameter {{
    Variable "Width"
    Value "1"
    Show off
  }}
}}
'''
        extra.extend(parse(snippet.splitlines())[0])
        connections.extend(parse(f'''Connection {{
  Type Signal
  SrcComponent "WIN_PROBE_{i}"
  SrcTerminal 1
  DstComponent "WIN_OUT_{i}"
  DstTerminal 1
}}
'''.splitlines())[0])
        terminals.extend(parse(f'''Terminal {{
  Type Output
  Index "{i}"
}}
'''.splitlines())[0])
    first = next((i for i,n in enumerate(schematic) if n['key']=='Connection'),len(schematic))
    schematic[first:first] = extra
    annotation = next((i for i,n in enumerate(schematic) if n['key']=='Annotation'),len(schematic))
    schematic[annotation:annotation] = connections
    first = next(i for i,n in enumerate(root) if n['key']=='Schematic')
    root[first:first] = terminals
    path = dest/source.name
    path.write_text(serialize(tree)+'\n', encoding='utf-8')
    return path


BUCK_CHANNELS = {
    'VINBUS': ('V_dc','Source voltage'), 'IIN': ('V_dc','Source current'),
    'VOUT': ('Rload','Resistor voltage'), 'IOUT': ('Rload','Resistor current'),
    'VDS': ('SiC_MOSFET','Device voltage'), 'ID': ('SiC_MOSFET','Device current'),
    'IDIODE': ('SiC_SBD','Diode current (A)'),
}


def measure(t, y, window):
    mask=(t>=window[0]) & (t<=window[1])
    tx=t[mask]; v=y[mask]
    if len(tx)<2: raise ValueError('Missing statistics window')
    dt=np.diff(tx)
    return {'mean':float(np.sum(dt*(v[:-1]+v[1:])/2)/(tx[-1]-tx[0])),
            'rms':float(np.sqrt(np.sum(dt*(v[:-1]**2+v[:-1]*v[1:]+v[1:]**2)/3)/(tx[-1]-tx[0]))),
            'max':float(v.max())}


def plots(out, pt, ps, rt, rs, channels, end):
    for kind, window in [('startup',(0,min(.005,end))),('steady',(max(0,end-.0001),end))]:
        fig, axes = plt.subplots(len(channels),1,figsize=(14,2.0*len(channels)),squeeze=False,sharex=True)
        for ax,ch in zip(axes[:,0],channels):
            n=ch['pulse']
            for t,v,label,color in [(rt,rs[n],'PLECS','#222222'),(pt,ps[n],'PULSE','#d84b27')]:
                m=(t>=window[0]) & (t<=window[1])
                ids=np.flatnonzero(m)
                if len(ids)>15000: ids=ids[::max(1,len(ids)//15000)]
                ax.plot(t[ids]*1000,v[ids],label=label,color=color,lw=.8,alpha=.85)
            ax.set_ylabel(n+' ('+ch.get('unit','')+')'); ax.grid(alpha=.2)
        axes[0,0].legend(loc='upper right',ncol=2)
        axes[-1,0].set_xlabel('Time (ms)')
        fig.suptitle(out.name+' | '+kind);fig.tight_layout()
        fig.savefig(out/(kind+'.png'),dpi=140);plt.close(fig)


def run_case(case, out, solver, proxy, timeout):
    config=json.loads((case/'case.json').read_text(encoding='utf-8'))
    entry={'case':config['case_id'],'status':'PREPARING','source_case':str(case)}
    out.mkdir(parents=True,exist_ok=True)
    dump(out/'case_snapshot.json',config)
    source=case/config['source_model']
    entry['source_sha256']=sha(source)
    inv,root=inventory(source)
    end=float(config.get('simulation',{}).get('end_s',.3))
    dt=float(config.get('simulation',{}).get('save_dt_s',2e-7))
    # Historical case duration is frozen; new conversion uses source Test_time.
    if not config.get('netlist'):
        conv=Converter(root)
        end=number(inv['settings']['TimeSpan'],conv.m.env)
        nettext=conv.convert(end=end,save_dt=dt)
        channels=conv.channels
        # Newly converted fixed-PWM cases have no frozen comparison schedule.
        # Derive it from the source, before either simulator is executed.
        pulses=[c for c in conv.m.components.values() if c['Type']=='PulseGenerator']
        if len(pulses)==1 and conv.m.num(pulses[0],'Delay')==0:
            pulse=pulses[0];period=1/conv.m.num(pulse,'f')
            config['switching_schedule']={'period_s':period,'on_s':period*conv.m.num(pulse,'DutyCycle'),'origin_s':0}
            dump(out/'comparison_schedule.json',{'source':'single zero-delay source PulseGenerator','schedule':config['switching_schedule'],'rtol':config.get('acceptance',{}).get('rtol',.01),'atol':{ch['pulse']:ch['atol'] for ch in channels}})
        dump(out/'conversion.json',{'channels':channels,'approximations':conv.approximations,'reference_planes':conv.reference_planes})
    else:
        nettext=(case/config['netlist']).read_text(encoding='utf-8')
        channels=copy.deepcopy(config['channels'])
        for ch in channels:
            if 'plecs_component' not in ch:
                ch['plecs_component'],ch['plecs_signal']=BUCK_CHANNELS[ch['pulse']]
    dump(out/'channel_mapping.json',channels)
    net=out/'input.md';net.write_text(nettext,encoding='utf-8')
    entry['netlist_sha256']=sha(net)
    pulseout=out/'pulse';pulseout.mkdir(exist_ok=True)
    command=[str(solver),str(net),'--out',str(pulseout)]
    started=time.perf_counter()
    try:
        run=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
        (pulseout/'stdout.json').write_text(run.stdout,encoding='utf-8')
        (pulseout/'stderr.txt').write_text(run.stderr,encoding='utf-8')
        entry.update(pulse_returncode=run.returncode,pulse_wall_seconds=time.perf_counter()-started)
    except subprocess.TimeoutExpired as exc:
        entry.update(status='PULSE_TIMEOUT',pulse_wall_seconds=time.perf_counter()-started)
        (pulseout/'timeout_stdout.txt').write_bytes(exc.stdout or b'')
        return entry
    report=pulseout/'simulation_report.json'
    if report.exists():
        native=json.loads(report.read_text(encoding='utf-8'))
        entry.update(pulse_status=native.get('status'),effective_end=native.get('simulated_seconds'),diagnostic=native.get('diagnostic'))
    if run.returncode:
        if not report.exists():
            try:
                diagnostic=json.loads(run.stdout or run.stderr)
                entry.update(pulse_status='COMPILE_ERROR',diagnostic=diagnostic)
            except (ValueError,TypeError):pass
        entry['status']='PULSE_UNSUPPORTED_OR_FAILED'
        return entry
    waves=list(pulseout.glob('*.npz'))
    pt,ps=read_wave(waves[0])
    end=float(pt[-1])
    capture=capture_model(source,out/'plecs_model',channels)
    entry['capture_model_sha256']=sha(capture)
    name=source.stem
    try:
        try: proxy.plecs.close(name)
        except xmlrpc.client.Fault: pass
        proxy.plecs.load(capture.as_posix())
        # Output only startup, frozen statistic windows and final steady detail.
        windows=[(0,min(.005,end)),(max(0,end-.0002),end)]
        baseline_path=config.get('baseline')
        baseline=json.loads((case/baseline_path).read_text(encoding='utf-8')) if baseline_path else {}
        for ch in channels:
            window=baseline.get('channels',{}).get(ch['pulse'],{}).get('statistics',{}).get('window_s')
            if window: windows.append(tuple(window))
        if not baseline: windows.append((max(0,end-min(.1,end)),end))
        outputs=np.unique(np.concatenate([np.r_[np.arange(a,b,dt),a,b] for a,b in windows]+[np.array([end])]))
        outputs=outputs[(outputs>=0)&(outputs<=end)]
        started=time.perf_counter()
        result=proxy.plecs.simulate(name,{'SolverOpts':{'OutputTimes':outputs.tolist(),'OutputTimesOption':'specified','Timeout':timeout}})
        entry['plecs_wall_seconds']=time.perf_counter()-started
        rt=np.asarray(result['Time'],dtype=float)
        values=np.asarray(result['Values'],dtype=float)
        if values.shape==(len(channels),len(rt)): values=values.T
        if values.shape!=(len(rt),len(channels)) or not len(rt):raise ValueError(f'PLECS output shape {values.shape}')
        if not np.all(np.isfinite(values)):raise ValueError('Non-finite PLECS output')
        if np.all(values==0):raise ValueError('All PLECS capture channels are zero; measurement configuration must be reviewed')
        rs={ch['pulse']:values[:,i] for i,ch in enumerate(channels)}
        np.savez_compressed(out/'plecs_waveforms.npz',time=rt,**rs)
        del result,values
    finally:
        try: proxy.plecs.close(name)
        except Exception: pass
    rows=[]
    for ch in channels:
        n=ch['pulse']
        window=baseline.get('channels',{}).get(n,{}).get('statistics',{}).get('window_s') or [max(0,end-min(.1,end)),end]
        # Refuse gap-spanning interpolation; PLECS output contains full statistic windows.
        schedule=config.get('switching_schedule')
        if schedule:
            pstats=mode_statistics(pt,ps,[n],window,schedule)[n]
            mask=(rt>=window[0]-dt*.01)&(rt<=window[1]+dt*.01)
            # Remove other disjoint capture windows before integrating modes.
            rstats=mode_statistics(rt[mask],{n:rs[n][mask]},[n],window,schedule)[n]
        else:
            pstats=measure(pt,ps[n],window);rstats=measure(rt,rs[n],window)
        for metric in ('rms','max','mean'):
            ref=rstats[metric];actual=pstats[metric]
            tolerance=ch.get('atol',1e-4)+config.get('acceptance',{}).get('rtol',.01)*abs(ref)
            rows.append({'channel':n,'metric':metric,'window_s':window,'plecs':ref,'pulse':actual,'abs_error':abs(actual-ref),'allowed_error':tolerance,'passed':abs(actual-ref)<=tolerance})
    dump(out/'statistics.json',rows)
    with (out/'statistics.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
    plots(out,pt,ps,rt,rs,channels,end)
    entry.update(status='STATISTICS_PASS_VISUAL_REVIEW_PENDING' if all(r['passed'] for r in rows) else 'FAIL_STATISTICS',channels=len(channels),statistics_passed=sum(r['passed'] for r in rows),statistics_total=len(rows),plecs_samples=len(rt))
    return entry


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--library',type=Path,default=LIBRARY)
    p.add_argument('--solver',type=Path,default=PROJECT/'build/pulse-solver.exe')
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--case',action='append',help='Family folder names, default latest version of all cases')
    p.add_argument('--timeout',type=int,default=180)
    a=p.parse_args();a.out=a.out.resolve();a.solver=a.solver.resolve();a.out.mkdir(parents=True,exist_ok=False)
    socket.setdefaulttimeout(a.timeout+60)
    proxy=xmlrpc.client.ServerProxy('http://127.0.0.1:1080',allow_none=True)
    cases=[]
    for family in sorted((a.library/'cases').iterdir()):
        if not family.is_dir() or (a.case and family.name not in a.case): continue
        versions=sorted(x for x in family.glob('v*') if (x/'case.json').exists())
        if versions:cases.append(versions[-1])
    summary={'solver':str(a.solver),'solver_sha256':sha(a.solver),'plecs_executable':r'D:\Program Files\PLECS482\PLECS.exe','plecs_version':'4.8.2','platform':sys.platform,'method':'Live PLECS RPC vs native Windows PULSE; frozen library read-only; 1% + channel atol; visual review separate; captured startup/statistics/final-detail windows, not a continuous full-history waveform','cases':[]}
    for case in cases:
        print('START',case.parent.name,case.name,flush=True)
        out=a.out/(case.parent.name+'-'+case.name)
        try: entry=run_case(case,out,a.solver,proxy,a.timeout)
        except Exception as exc:
            out.mkdir(exist_ok=True)
            (out/'error.txt').write_text(traceback.format_exc(),encoding='utf-8')
            entry={'case':case.parent.name+'-'+case.name,'status':'ERROR','error':str(exc)}
        dump(out/'result.json',entry)
        summary['cases'].append(entry);dump(a.out/'summary.json',summary)
        lines=['# Windows PULSE / live PLECS comparison','','Solver SHA256: `'+summary['solver_sha256']+'`','','| Case | Status | Statistics |','|---|---|---|']
        for x in summary['cases']:lines.append(f"| {x['case']} | {x['status']} | {x.get('statistics_passed','-')}/{x.get('statistics_total','-')} |")
        lines+=['','Statistics use frozen channel tolerances. PASS requires separate waveform and topology review. Failed/unsupported cases retain diagnostics. Existing library files are not modified.']
        (a.out/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        print(entry['case'],entry['status'],entry.get('error',''),flush=True)


if __name__=='__main__': main()
