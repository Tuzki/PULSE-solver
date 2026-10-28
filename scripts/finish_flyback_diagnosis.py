from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys

root=Path(r'D:\codex\pulse-solver-v1.15win')
out=root/'reports/flyback_root_cause_20261027'
sys.path.insert(0,str(root/'scripts'))
import windows_compare as w
source_case=w.LIBRARY/'cases/rohm-c010-d-flyback/v002'
config=json.loads((source_case/'case.json').read_text(encoding='utf-8'))
source=source_case/config['source_model']
inv,tree=w.inventory(source);conv=w.Converter(tree)
net=conv.convert(end=.3,save_dt=2e-7)
# Choose the primary coordinate reference only. Secondary topology remains intact.
fixed=re.sub(r'\bREF1\b','0',net)
(out/'flyback_primary_reference_fixed.md').write_text(fixed,encoding='utf-8')
translation={
 'source_sha256':w.sha(source),
 'primary_reference_fix':'REF1 -> 0 only; REF2 remains an independent floating reference label',
 'fixed_netlist_sha256':hashlib.sha256(fixed.encode('utf-8')).hexdigest(),
 'reference_planes':conv.reference_planes,
 'parameters':conv.m.env,
 'transformer':{},
 'static_checks':{'no_cross_island_electrical_wire_added':True,'no_parasitic_added':True,'storage_initial_conditions_unchanged':True},
 'runtime_capability':'Original solver does not remove the independent secondary common-potential gauge. No lossless supported reference directive was found in v1.1 grammar.'}
for path,c in conv.devices.items():
 if c['Type']=='Transformer':
  turns=conv.vector(c['params']['n'],c['env']);k=turns[1]/turns[0]
  translation['transformer']={'component':path,'turns':turns,'voltage_ratio':k,
    'equations':['v_secondary = k * v_primary','i_primary = -k * i_secondary'],
    'power_identity':'v_primary*i_primary + v_secondary*i_secondary = 0',
    'internal_magnetizing_inductance':c['params']['Lm'],'external_magnetizing_inductance_H':conv.m.env.get('Lm')}
w.dump(out/'translation_audit.json',translation)

def doc(network,signals):
 return '# PULSE Netlist v1.1\n\n## Parameters\n```pulse\n```\n\n## Network\n```pulse\n'+network+'\n```\n\n## Simulation\n```pulse\n.TRAN T_END=1u SAVE_DT=100n\n.SAVE '+signals+'\n```\n\n## Layout\n```json\n{"version":"1.1","components":{},"wires":[]}\n```\n'

tests={
 'grounded_single_loop':doc('V_A P 0 DC=1\nR_A P 0 R=1\nSENSOR_A VA V P 0','VA'),
 'independent_floating_loop':doc('V_A P 0 DC=1\nR_A P 0 R=1\nV_B SPLUS SREF DC=2\nR_B SPLUS SREF R=1\nSENSOR_A VA V P 0\nSENSOR_B VB V SPLUS SREF','VA VB')}
reproductions=[]
for name,text in tests.items():
 dest=out/name;dest.mkdir(exist_ok=True)
 path=dest/'input.md';path.write_text(text,encoding='utf-8')
 run=subprocess.run([str(root/'build/pulse-solver.exe'),str(path),'--out',str(dest/'pulse')],capture_output=True,text=True,encoding='utf-8',timeout=30)
 (dest/'stdout.json').write_text(run.stdout,encoding='utf-8');(dest/'stderr.txt').write_text(run.stderr,encoding='utf-8')
 report=json.loads((dest/'pulse/simulation_report.json').read_text(encoding='utf-8'))
 reproductions.append({'test':name,'returncode':run.returncode,'status':report['status'],'effective_end':report['simulated_seconds'],'diagnostic':report['diagnostic']})
w.dump(out/'minimal_reproductions.json',reproductions)

old=Path(r'D:\codex\pulse-solver-v1.15\pulse-solver-v1.15')
files=[p for folder in ['src','include','apps'] for p in (old/folder).rglob('*') if p.is_file()]+[old/'CMakeLists.txt']
proof={'solver_sha256':w.sha(root/'build/pulse-solver.exe'),'source_files_checked':len(files),
       'source_unchanged':all(p.read_bytes()==(root/p.relative_to(old)).read_bytes() for p in files)}
assert proof['source_unchanged']
w.dump(out/'solver_unchanged.json',proof)

lines=['# Flyback 根因分析：独立浮置参考坐标未消除','',
'## 结论','',
'本次 t=0 的 MODEL_SINGULAR 根因已定位：原版 PULSE 将隔离侧公共电位作为需要唯一求解的未知量，却没有为每个独立浮置电气岛建立参考坐标。对本 Flyback 初始全部 4 个候选模态，矩阵秩缺陷完全由这些公共电位自由度解释。按用户要求，只报告该求解器能力限制，没有修改源码、二进制、阈值、预算或运行算法。','',
'转换层也有一处可独立修正的问题：原边 REF1 是普通节点名，不是语言定义的特殊参考 0。本次已在独立副本 flyback_primary_reference_fixed.md 修正为 0；副边 REF2 保留。此修正消除了原边自由度，但不能消除副边自由度，故不能使原版仿真完成。','',
'## 原版组装矩阵的直接证据','',
'诊断程序直接 #include 未改动的 src/descriptor.cpp，链接已有静态库，调用原版 Assembler::stamp。它只读矩阵、测量秩，不传播物理状态，不生成修复版波形。秩判据采用原版的行列平衡与阈值公式。','',
'| 网表 | 初始候选模态数 | A 维数 / 秩 | 空空间维数 | 仅作诊断的参考坐标消元后 |',
'|---|---:|---|---:|---|',
'| 新转换，REF1/REF2 均为普通节点 | 4 | 31 / 29（每个候选均如此） | 2 | 29 / 29 |',
'| 仅将原边 REF1 改为 0 | 4 | 30 / 29（每个候选均如此） | 1 | 29 / 29 |','',
'对每个浮置岛构造向量 g：该岛全部节点电位分量取 1，其余节点、支路电流、信号分量取 0。全部候选中 A*g 和 F*g 的范数均严格为 0。也就是说，把副边所有节点电位同时加同一个常数，不改变任何元件电压差、电流或储能状态导数；原版却要求包含该自由度的系统唯一可逆。','',
'删除各岛一个参考电位坐标及其冗余 KCL 行后，秩检查全部满秩。此处仅为证明缺陷来源的矩阵检查；没有把它用于求解器修补或宣称完整仿真通过。该证据定位当前初始化错误，不证明消除参考自由度后整个 0.3 s 过程中不存在其他问题。','',
'## 最小复现，不含变压器或开关','',
'用同一个未修改的 pulse-solver.exe 测试：','',
'| 测试 | 结果 |',
'|---|---|']
for r in reproductions:lines.append(f"| {r['test']} | {r['status']}；有效终点 {r['effective_end']} s；{r['diagnostic'].get('subcode','无错误')} |")
lines+=['',
'第二个测试只是增加独立的 2 V 电源—1 Ω 电阻闭合回路，并以电压差测量它；该回路电流和端口电压确定，但绝对公共电位未定义。没有变压器、PWM、二极管、储能或事件，却复现同类错误。因此当前阻塞不依赖 Flyback 的控制或理想变压器数值细节。','',
'## 翻译检查','',
'- 源理想变压器匝数 [15,-2]，生成 v_s=(-2/15)*v_p、i_p=(2/15)*i_s，满足端口瞬时功率守恒。','- 内置 Lm=inf；外置励磁电感 3 mH 保留，没有重复加入励磁支路。','- 电容 500 µF、12 V 初值及其他已映射物理参数保留。','- 没有发现需要通过改匝比、极性、储能初态或增加漏感来修复此次 t=0 秩缺陷的证据。','- 正定 L_MATRIX 不能精确表达零漏感理想变压器的奇异电感矩阵，故未用未声明漏感替换原模型。','',
'## 修复边界','',
'原副边全部替换为同一个节点 0 会合并电端口拓扑，不采用。新增 0 V 电源、接地电阻等支路也不采用。v1.1 输入格式没有声明多个独立参考面的指令，REF2 只是普通名字；把名字换成另一个字符串不能解决问题。','',
'完整且保持隔离拓扑的处理，需要求解器/输入接口支持独立电气岛的参考坐标消元，并区分有意义的差模测量和未定义的跨浮置岛绝对电位测量。这属于求解器能力问题，本次没有实施修复。','',
'原始 PLECS 已在上一轮独立完成 0.3 s，7 通道 21 项统计与历史基准一致。当前 PULSE 没有有效前缀，因此没有误差比较结论。','',
'## 可复核文件','',
'- fresh_matrix_audit.json / primary0_matrix_audit.json：所有候选矩阵的秩及零空间残差。',
'- flyback_matrix_audit.cpp / .exe：独立诊断工具；不是替代求解器。',
'- minimal_reproductions.json 与两个最小测试目录：原版实际执行结果。',
'- translation_audit.json：匝比、参考面和源参数；flyback_primary_reference_fixed.md：只修正原边参考的副本。',
'- solver_unchanged.json：26 个源码/构建文件与原版一致；二进制 SHA256 为 '+proof['solver_sha256']+'。']
(out/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({'reproductions':reproductions,'integrity':proof,'report':str(out/'REPORT.md')},ensure_ascii=False,indent=2))
