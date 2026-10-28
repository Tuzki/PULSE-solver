from pathlib import Path
import difflib,json,sys
root=Path(r'D:\codex\pulse-solver-v1.15win')
sys.path.insert(0,str(root/'scripts'))
import windows_compare as w
np=w.np;out=root/'reports/primitive_translation_20261027';validation=out/'block_validation_delivery'
load=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
checks=load(out/'solver_before_sha256.json');integrity=[]
for item in checks:
 p=Path(item['Path']);integrity.append({'path':str(p),'before':item['Hash'].lower(),'after':w.sha(p),'unchanged':item['Hash'].lower()==w.sha(p)})
assert all(x['unchanged'] for x in integrity)
release=load(root/'reports/island_reference_fix_20261027/build_manifest.json')
original=Path(r'D:\codex\pulse-solver-v1.15\pulse-solver-v1.15')
source_checks=[]
for p in [p for folder in ['src','include','apps'] for p in (original/folder).rglob('*') if p.is_file()]+[original/'CMakeLists.txt']:
 relative=p.relative_to(original).as_posix();expected=release['modified_files'].get(relative,{}).get('after',w.sha(p))
 source_checks.append({'file':relative,'expected':expected,'actual':w.sha(root/relative),'unchanged':expected==w.sha(root/relative)})
assert all(x['unchanged'] for x in source_checks)
w.dump(out/'solver_integrity.json',{'all_unchanged':True,'cli_sha256':w.sha(root/'build/pulse-solver.exe'),'before_after':integrity,'all_26_release_sources':source_checks})

tests=load(validation/'summary.json');continuous={'absolute_value','transfer_first_order','transfer_resonant','continuous_pi','continuous_affine_product'}
assessed=[]
for row in tests:
 name=row['test'];dest=validation/name;entry=dict(row)
 if row['status']=='ERROR':
  native=load(dest/'pulse/simulation_report.json');entry.update(assessment='LIMIT_TIME_RESOLUTION',diagnostic=native['diagnostic'],effective_end=native['simulated_seconds'])
 else:
  entry['assessment']='PASS_SAMPLED_AND_EDGES'
  if name not in continuous:
   with np.load(dest/'comparison.npz') as z:
    a=np.flatnonzero(np.abs(np.diff(z['pulse']))>1e-4)+1;b=np.flatnonzero(np.abs(np.diff(z['plecs']))>1e-4)+1
    same=len(a)==len(b);error=float(np.max(np.abs(z['time'][a]-z['time'][b]))) if same and len(a) else None
    entry.update(pulse_edges=len(a),plecs_edges=len(b),max_saved_edge_time_difference_s=error)
    if not same or error is not None and error>2e-6:entry['assessment']='BOUNDARY_DIFFERENCE_NOT_FULL_PASS'
 assessed.append(entry)
w.dump(out/'module_assessment.json',assessed)
counts={key:sum(r['assessment']==key for r in assessed) for key in sorted(set(r['assessment'] for r in assessed))}
assert counts=={'BOUNDARY_DIFFERENCE_NOT_FULL_PASS':1,'LIMIT_TIME_RESOLUTION':1,'PASS_SAMPLED_AND_EDGES':35},counts

# Reviewable plots from already captured data; no simulator reruns.
fig,axes=w.plt.subplots(3,2,figsize=(13,9))
for ax,name in zip(axes.ravel(),['switch_boolean_data','zoh_cascade','continuous_pi','transfer_resonant','pwm_sampling_4','held_product_same_clock']):
 with np.load(validation/name/'comparison.npz') as z:
  ax.plot(z['time']*1000,z['plecs'],color='#333333',lw=1.4,label='PLECS');ax.plot(z['time']*1000,z['pulse'],color='#dc5a32',lw=.8,label='PULSE')
 ax.set_title(name,fontsize=10);ax.set_xlabel('Time (ms)');ax.grid(alpha=.2)
axes[0,0].legend();fig.suptitle('Primitive control translations | unchanged PULSE solver');fig.tight_layout(rect=[0,0,1,.96]);fig.savefig(out/'module_overlays.png',dpi=140);w.plt.close(fig)
with np.load(validation/'pwm_sampling_2/comparison.npz') as z:
 mask=(z['time']>=.000345)&(z['time']<=.000355)
 fig,ax=w.plt.subplots(figsize=(9,3));ax.plot(z['time'][mask]*1e6,z['plecs'][mask],'o-',label='PLECS');ax.plot(z['time'][mask]*1e6,z['pulse'][mask],'x--',label='PULSE');ax.set_xlabel('Time (us)');ax.set_ylabel('PWM output');ax.legend();ax.grid(alpha=.2);ax.set_title('Retained boundary difference: command step meets carrier threshold');fig.tight_layout();fig.savefig(out/'boundary_difference.png',dpi=140);w.plt.close(fig)

batch=load(out/'similar_cases_delivery/summary.json');assert len(batch['cases'])==14
lines=['# 用现有原语扩展 PLECS 控制模块翻译及验证','',
'本轮严格遵守“不允许修改仿真器”：只修改独立转换器与验证脚本。Windows PULSE CLI/DLL 及对应发布版的 26 个核心源码/构建文件均保持不变，见 solver_integrity.json。当前 CLI SHA256 为 `'+w.sha(root/'build/pulse-solver.exe')+'`。','',
'## 结论','',
'已补齐一批控制模块原语映射并做实际 PLECS/PULSE 对照。37 个模块级用例中，35 个满足采样值和适用的边沿检查；1 个自然 PWM 用例有边界单点差异；1 个双速率时钟用例被现有时间来源检查拒绝。后两项不计为完整通过。','',
'A002 Boost PFC 和两个 Vienna PFC 已从“模块无法展开”推进到生成候选原语网表，但三者均在连续非线性运算处被当前编译器拒绝，尚无有效 PULSE 轨迹。本轮没有新增完整电路对照通过，不沿用模块通过来代替整机通过。','',
'## 已实现映射','',
'| PLECS 模块 | 现有 PULSE 原语组合 | 验证及范围 |','|---|---|---|',
'| SignalSwitch | CMP/SEL，布尔控制可直接 SEL | REAL/BOOL 数据，>= 与 > 的零阈值分支；控制端口实际为 4，数据为 2/3 |',
'| ZeroOrderHold | 周期 EVENT + REG；必要时零延时事件分层 | 单速率、级联、输入阶跃与采样同刻；不接受未验证采样反馈环 |',
'| Continuous PI | MATH + INT | 内部参数、零初态、无复位、无限饱和上下限；未擅自离散化 |',
'| TransferFunction / PR | 连续状态空间 MATH + INT | 标量、适当有理传递函数、零初态；一阶与谐振结构已对照 |',
'| Min/Max、Abs | CMP + SEL + 仿射 MATH | 标量，含 Abs 连续过零 |',
'| Symmetrical PWM | EVENT、REG、INT、CMP、SEL | 六种采样方式，另测三种非零相位；自然载波输入跳变重合边界例单列 |',
'| Product | 冻结系数转仿射 MATH；两个保持值用 MATH OP=MUL/DIV | 同时钟的两个采样值乘法通过；连续×连续不改写成采样乘法 |',
'| 逻辑及比较枚举 | CMP、SEL | 复核全部六种逻辑和四种大小比较，避免只按枚举猜测 |','',
'采用零延时微步保持同一物理时刻的级联采样次序，没有额外引入一个采样周期的延迟。周期时间字面量避免无必要的 17 位十进制来源差异；多速率时间限制未绕过。','',
'## A002 的真实阻塞','',
'PFC/Product1 的两个输入分别来自连续 PI 输出和连续交流电压归一化信号。即使 PI 输入先经过 ZOH，积分状态仍随物理时间连续变化；PI 输出不是保持值。候选网表忠实保留该乘法，因此触发：','',
'```text\nCONTINUOUS_NONAFFINE\ndiscrete MATH requires held REAL inputs\nMATH_D105_PRODUCT\n```','',
'v1.1 格式规范第 8.2 节明确限制 MATH 操作码的动态输入必须为事件间保持 REAL；src/semantics.cpp 对此有实际检查。这是当前连续表达域的限制，不是仍缺 SignalSwitch 映射，也不意味着离散乘法不能表达。独立的两个 INT 连续输出相乘最小用例复现了同一拒绝；同一时钟下两个 REG 输出相乘则逐点匹配。','',
'本次没有把连续 PI、PR 或乘法输入偷偷增加 ZOH，没有更改原采样周期、原语、源码、阈值、预算。这里证明的是当前逐模块映射不能直接表达该连续关系，并未证明任何整控制器等价变换都不可能。','',
'[A002 候选网表与实际诊断](similar_cases_delivery/rohm-a002-d-boost-pfc-v001/result.json) · [连续乘法最小复现](continuous_product_guard/diagnostic.json) · [源控制模块审计](pfc_control_audit.json)','',
'原始 A002 PLECS 已独立完成 0.5 s，采集七个电气通道，见 [参考记录](pfc_original_plecs/result.json) 与 [原模型概览](pfc_original_plecs/overview.png)。这是 PLECS 单边运行证据，不是 PULSE 对照通过。','',
'## 37 个模块用例的最终判定','',
'每例约 4001 个保存时间点，保存间隔 1 µs。连续/稳定采样值采用预先设置的绝对误差 1e-4；通过用例中连续值最大差约 1.2e-7。跳变左右附近点单列后，还额外比较边沿数量及保存网格上的边沿时间（2 µs 限制），不据此宣称亚采样精度。','',
'| 用例 | 最终判定 | 说明 |','|---|---|---|']
for r in assessed:
 note=r.get('diagnostic',{}).get('subcode','')
 if r['assessment']=='BOUNDARY_DIFFERENCE_NOT_FULL_PASS':note=f"PULSE {r['pulse_edges']} / PLECS {r['plecs_edges']} 个保存边沿；输入跳变与阈值重合"
 elif r['assessment']=='PASS_SAMPLED_AND_EDGES':note=f"稳定采样值最大绝对差 {r['max_abs_error']:.4g}"
 lines.append(f"| {r['test']} | {r['assessment']} | {note} |")
lines+=['','[完整模块结果](module_assessment.json) · [代表性叠加图](module_overlays.png) · [保留的边界差异](boundary_difference.png)','',
'多速率失败例为 Ts=200 µs 与 300 µs 的两路独立 EVENT 周期钟，报 TIME_RESOLUTION_UNRESOLVED。它证明当前这种直接时钟映射仍有实现限制；未改检查规则，也未声称多速率在所有其他原语组合下都不可表达。公共主时钟调度等改写尚未实现验证。','',
'## 14 个同类案例重新检查','',
'三个案例成功生成候选网表但编译拒绝连续非线性；另外 11 个仍有变频/三电平 PWM、消隐时间或显式测量映射等转换缺项。没有新增完整通过案例。','',
'| 案例 | 本轮阻塞 |','|---|---|']
for c in batch['cases']:
 reason=c.get('diagnostic',{}).get('subcode') or c.get('error','').replace('\n',' ').split('{')[0]
 lines.append(f"| {c['case']} | {reason} |")
lines+=['','## 使用与证据','',
'独立转换器位于 tools/plecs_conversion/convert_rohm.py，基于原 compare 转换器扩展；原 compare 工具与冻结案例未改。windows_compare.py 优先加载本地扩展，但仍复用已冻结案例的网表。旧 Buck/Boost/Flyback 的仿真器和网表未变；本轮没有重复运行它们，也不把旧通过误记为新案例通过。','',
'- solver_integrity.json：CLI/DLL 与核心源码不变证据。',
'- translator_changes.patch：仅转换器新增逻辑。',
'- block_validation_delivery/：每个模块的 PLECS、候选网表、原始波形、日志。',
'- module_assessment.json：在稳定值初筛之上追加边沿/时钟限制后的最终判定。早期 summary.json 的 PASS 只表示稳定值检查，不可取代最终判定。',
'- similar_cases_delivery/：最后一次全案例尝试及编译诊断。',
'','本轮结果限定于已测条件：非零初态传递函数、带饱和/复位的 PI、向量 PWM、未验证的采样反馈环等仍明确拒绝。若继续原 PFC，需要研究保持原语约束的整控制器等价变换，或在另行明确误差要求后研究控制器离散化；本轮没有执行这些替换。']
(out/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
old=w.LIBRARY/'tools/convert_rohm.py';new=root/'tools/plecs_conversion/convert_rohm.py'
(out/'translator_changes.patch').write_text(''.join(difflib.unified_diff(old.read_text(encoding='utf-8').splitlines(True),new.read_text(encoding='utf-8').splitlines(True),fromfile='a/convert_rohm.py',tofile='b/convert_rohm.py')),encoding='utf-8')
readme='''# PLECS control primitive mappings

Independent extension of the frozen comparison-library converter. No solver
changes are required or performed by this tool. Emitting a candidate Markdown
netlist does not guarantee the solver accepts its expression phase or timing.

See ../../reports/primitive_translation_20261027/REPORT.md for scope, validation,
the retained PWM boundary discrepancy and the independent-clock limitation.
Current A002/Vienna PFC candidates fail CONTINUOUS_NONAFFINE; they are not PASS.
Continuous products are never silently replaced by sampled products. Nonzero
transfer-function initial states, reset/saturated PI and unverified feedback
sample loops are rejected. Keep original model parameters and schedules.

The fixed-parameter scalar mappings tested here include SignalSwitch, ZOH,
continuous PI, proper transfer functions, Abs, MinMax and symmetrical PWM.
Future mappings must be independently compared against native PLECS first.
'''
(root/'tools/plecs_conversion/README.md').write_text(readme,encoding='utf-8')
print(json.dumps({'module_counts':counts,'all_solver_files_unchanged':True,'report':str(out/'REPORT.md')},indent=2))
