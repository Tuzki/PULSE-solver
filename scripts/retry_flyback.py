"""Retry Flyback without solver changes or cross-island electrical connections."""
from pathlib import Path
import json
import os
import re
import socket
import subprocess
import sys
import time
import xmlrpc.client

root=Path(r'D:\codex\pulse-solver-v1.15win')
sys.path.insert(0,str(root/'scripts'))
import windows_compare as w
np=w.np
case=w.LIBRARY/'cases/rohm-c010-d-flyback/v002'
out=root/'reports'/('flyback_retry_'+time.strftime('%Y%m%d_%H%M%S'))
out.mkdir(parents=True,exist_ok=False)
config=json.loads((case/'case.json').read_text(encoding='utf-8'))
source=case/config['source_model']
solver=root/'build/pulse-solver.exe'
summary={'solver_sha256':w.sha(solver),'source_sha256':w.sha(source),'output':str(out),'runs':[]}
w.dump(out/'case_snapshot.json',config)
inv,tree=w.inventory(source)
converter=w.Converter(tree)
fresh=converter.convert(end=.3,save_dt=2e-7)
w.dump(out/'conversion.json',{'channels':converter.channels,'approximations':converter.approximations,'reference_planes':converter.reference_planes})
frozen=(case/config['netlist']).read_text(encoding='utf-8')
variants=[('frozen',frozen),('fresh',fresh),('fresh_primary_reference_0',re.sub(r'\bREF1\b','0',fresh))]
for label,text in variants:
    dest=out/label;dest.mkdir()
    net=dest/'input.md';net.write_text(text,encoding='utf-8')
    run=subprocess.run([str(solver),str(net),'--out',str(dest/'pulse')],capture_output=True,text=True,encoding='utf-8',timeout=60)
    (dest/'stdout.json').write_text(run.stdout,encoding='utf-8')
    (dest/'stderr.txt').write_text(run.stderr,encoding='utf-8')
    report=json.loads((dest/'pulse/simulation_report.json').read_text(encoding='utf-8'))
    entry={'variant':label,'netlist_sha256':w.sha(net),'returncode':run.returncode,'status':report['status'],'effective_end':report['simulated_seconds'],'diagnostic':report.get('diagnostic')}
    summary['runs'].append(entry);w.dump(out/'summary.json',summary)
    print(json.dumps(entry),flush=True)

# Independently establish that the original physical model runs in PLECS.
try:
    with socket.create_connection(('127.0.0.1',1080),timeout=1):pass
except OSError:
    env=os.environ.copy();env['LM_LICENSE_FILE']=r'D:\Program Files\PLECS482\license.lic'
    log=(out/'plecs_server.log').open('w')
    subprocess.Popen([r'D:\Program Files\PLECS482\PLECS_server.exe','-e'],env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
    for i in range(40):
        try:
            with socket.create_connection(('127.0.0.1',1080),timeout=.3):break
        except OSError:time.sleep(.5)
    else:raise RuntimeError('PLECS server did not become available')

socket.setdefaulttimeout(240)
proxy=xmlrpc.client.ServerProxy('http://127.0.0.1:1080')
capture=w.capture_model(source,out/'plecs_model',config['channels'])
name=source.stem
try:
    try:proxy.plecs.close(name)
    except xmlrpc.client.Fault:pass
    proxy.plecs.load(capture.as_posix())
    times=np.unique(np.r_[np.arange(0,.005,2e-7),.005,np.arange(.1,.2,2e-7),.1,.2,np.arange(.2998,.3,2e-7),.3])
    started=time.perf_counter()
    result=proxy.plecs.simulate(name,{'SolverOpts':{'TimeSpan':.3,'Timeout':180,'OutputTimes':times.tolist(),'OutputTimesOption':'specified'}})
    elapsed=time.perf_counter()-started
    rt=np.asarray(result['Time']);values=np.asarray(result['Values'])
    if values.shape==(7,len(rt)):values=values.T
    assert values.shape==(len(rt),7) and np.all(np.isfinite(values))
    signals={ch['pulse']:values[:,i] for i,ch in enumerate(config['channels'])}
    np.savez_compressed(out/'plecs_waveforms.npz',time=rt,**signals)
    summary['plecs']={'status':'COMPLETED','end':float(rt[-1]),'samples':len(rt),'rpc_wall_seconds':elapsed,'capture_sha256':w.sha(capture)}
    print('PLECS',summary['plecs'],flush=True)
finally:
    proxy.plecs.close(name)

baseline=json.loads((case/config['baseline']).read_text(encoding='utf-8'))
rows=[]
mask=(rt>=.1)&(rt<=.2)
stats=w.mode_statistics(rt[mask],{n:v[mask] for n,v in signals.items()},list(signals),[.1,.2],config['switching_schedule'])
for ch in config['channels']:
    n=ch['pulse'];record=baseline.get('channels',{}).get(n,{}).get('statistics',{})
    for metric in ('rms','max','mean'):
        actual=stats[n][metric];ref=record.get('values',{}).get(metric)
        tolerance=ch['atol']+.01*abs(ref) if ref is not None else None
        rows.append({'channel':n,'metric':metric,'plecs_live':actual,'old_gui':ref,'passed':abs(actual-ref)<=tolerance if ref is not None else None})
w.dump(out/'plecs_vs_old_gui_statistics.json',rows)
for kind,limits in [('startup',(0,.005)),('steady',(.2999,.3))]:
    fig,axes=w.plt.subplots(7,1,figsize=(12,13),sharex=True)
    ids=np.flatnonzero((rt>=limits[0])&(rt<=limits[1]))
    for ax,ch in zip(axes,config['channels']):
        ax.plot(rt[ids]*1000,signals[ch['pulse']][ids],lw=.8,label='PLECS live')
        ax.set_ylabel(ch['pulse']+' ('+ch['unit']+')');ax.grid(alpha=.2)
    axes[0].legend();axes[-1].set_xlabel('Time (ms)');fig.suptitle('Flyback original model - PLECS only');fig.tight_layout();fig.savefig(out/(kind+'.png'),dpi=130);w.plt.close(fig)
summary['old_gui_statistics_passed']=sum(r['passed'] is True for r in rows)
w.dump(out/'summary.json',summary)
lines=['# Flyback retry: original PULSE / live PLECS','',
'本次从原始 PLECS 重新生成了 PULSE 网表。求解器二进制未修改，未增加寄生元件，未连接原副边参考面。','',
'| PULSE 网表 | 状态 | 有效终点 | 诊断 |','|---|---|---:|---|']
for r in summary['runs']:lines.append(f"| {r['variant']} | {r['status']} | {r['effective_end']} s | {r['diagnostic'].get('subcode')} |")
lines+=['',f"原始 PLECS 模型独立完成 0.3 s，采集 {len(rt)} 个时间点、7 个通道。与旧 GUI 基准的统计通过数：{summary['old_gui_statistics_passed']}/21。",'',
'fresh_primary_reference_0 仅将原边 REF1 改名为特殊节点 0，副边 REF2 及所有独立节点仍保留。它仍在 t=0 报错，说明只修正原边参考不足以解决问题。当前原版只特别处理节点 0，独立副边公共电位自由度没有获得单独的坐标参考；该接口限制是明确的阻塞因素，尚未证明是唯一因素。','',
'没有把 REF1/REF2 都改成 0；这种操作会合并电端口节点，不能用来声称保留隔离拓扑。也没有把理想变压器替换为带未声明漏感的近似耦合电感。','',
'本次结论：PLECS 原电路正常运行；原版 PULSE 对当前保留隔离拓扑的转换仍未完成有效仿真，因此没有可供数值比较的 PULSE 有效波形。','',
'[PLECS 启动](startup.png) · [PLECS 稳态](steady.png) · [逐项执行记录](summary.json) · [实时 PLECS 与历史基准统计](plecs_vs_old_gui_statistics.json)']
(out/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('REPORT',out/'REPORT.md',flush=True)
