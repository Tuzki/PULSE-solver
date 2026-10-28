from pathlib import Path
import csv,difflib,hashlib,json,sys
root=Path(r'D:\codex\pulse-solver-v1.15win')
sys.path.insert(0,str(root/'scripts'))
import windows_compare as w
out=root/'reports/island_reference_fix_20261027'

def load(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,v):w.dump(p,v)
old=load(root/'reports/windows_compare_20261027_final/summary.json')
summaries=[load(out/x/'summary.json') for x in ['flyback_live','buck_boost_live','other_cases']]
cases=[c for s in summaries for c in s['cases']]
assert len(cases)==20
baseline={c['case']:c for c in old['cases']}
groups={'rohm-c010-d-flyback-v002':'flyback_live','rohm-c006-d-buck-v001':'buck_boost_live','rohm-c002-d-boost-v002':'buck_boost_live'}
for name,group in groups.items():
    dest=out/group/name
    entry=next(c for c in cases if c['case']==name)
    assert entry['statistics_passed']==entry['statistics_total']==21
    assert entry['netlist_sha256']==baseline[name]['netlist_sha256']
    config=load(dest/'case_snapshot.json')
    source=Path(entry['source_case'])/config['source_model']
    capture=dest/'plecs_model'/source.name
    before=w.parse(source.read_text(encoding='utf-8-sig').splitlines())[0]
    reduced=w.parse(capture.read_text(encoding='utf-8-sig').splitlines())[0]
    blocks=reduced[0]['children'];assert not w.subs(before[0]['children'],'Terminal')
    blocks[:]=[n for n in blocks if n['key']!='Terminal']
    schematic=w.subs(blocks,'Schematic')[0]
    schematic[:]=[n for n in schematic if not (n['key']=='Component' and w.scalar(n['children']).get('Name','').startswith('WIN_') or n['key']=='Connection' and w.scalar(n['children']).get('DstComponent','').startswith('WIN_'))]
    assert reduced==before
    review={'original_model_structure_preserved':True,'original_pulse_netlist_unchanged':True,'status':'STATISTICS_PASS_WAVEFORM_MATCH_WITH_SAMPLING_LIMITS','images_sha256':{kind:w.sha(dest/(kind+'.png')) for kind in ['startup','steady']},'scope':'Seven electrical channels; startup and steady shape/frequency/phase. No sub-sample timing claim; thermal skips remain.'}
    if group=='buck_boost_live':
        # PULSE output and events are already compared bitwise. Also compare
        # captured references so a previous visual review can be carried forward.
        with w.np.load(root/'reports/windows_compare_20261027_final'/name/'plecs_waveforms.npz') as a,w.np.load(dest/'plecs_waveforms.npz') as b:
            review['plecs_reference_arrays_identical']=set(a.files)==set(b.files) and all(w.np.array_equal(a[k],b[k]) for k in a.files)
        assert review['plecs_reference_arrays_identical']
        review['visual_basis']='Prior reviewed overlays; both PULSE waveforms/events and live PLECS arrays identical to that batch.'
    else:review['visual_basis']='Both newly generated startup and steady overlays directly inspected.'
    save(dest/'visual_review.json',review)

prefix=load(out/'forward_prefix_02/summary.json')
assert prefix['statistics_passed']==prefix['statistics_total']==27
save(out/'forward_prefix_02/visual_review.json',{'conclusion':'PREFIX_WAVEFORM_MATCH_WITH_SAMPLING_LIMITS','images_sha256':{k:w.sha(out/'forward_prefix_02'/(k+'.png')) for k in ['startup','steady']},'scope':'Visual review of startup and final 100 us within the valid prefix; full 0.4 s run is NOT PASS.'})
native=load(out/'native_bitwise_regression.json');buckboost=load(out/'buck_boost_bitwise_regression.json')
assert native['all_passed'] and buckboost['all_passed']
manifest={'baseline_binary_sha256':w.sha(out/'baseline/build/pulse-solver.exe'),'patched_binary_sha256':w.sha(root/'build/pulse-solver.exe'),'patched_dll_sha256':w.sha(root/'build/libpulse_solver.dll'),'modified_files':{},'original_source_directory':r'D:\codex\pulse-solver-v1.15\pulse-solver-v1.15','authorization':'User explicitly authorized the isolation-reference solver fix and Flyback/Buck/Boost/other-case verification; historical compare solver-boundary records remain unchanged.'}
diff=[]
for file in ['include/pulse/core.hpp','src/semantics.cpp','src/descriptor.cpp','CMakeLists.txt','docs/Engineering_Contract.md','scripts/windows_compare.py']:
    oldfile=out/'baseline'/file;newfile=root/file
    manifest['modified_files'][file]={'before':w.sha(oldfile),'after':w.sha(newfile)}
    diff.extend(difflib.unified_diff(oldfile.read_text(encoding='utf-8').splitlines(True),newfile.read_text(encoding='utf-8').splitlines(True),fromfile='a/'+file,tofile='b/'+file))
file='tests/electrical_references.cpp';manifest['modified_files'][file]={'before':None,'after':w.sha(root/file)}
diff.extend(difflib.unified_diff([], (root/file).read_text(encoding='utf-8').splitlines(True),fromfile='/dev/null',tofile='b/'+file))
(out/'source_changes.patch').write_text(''.join(diff),encoding='utf-8')
save(out/'build_manifest.json',manifest)

rows=[]
for c in sorted(cases,key=lambda x:x['case']):
    name=c['case'];b=baseline[name]
    if name in groups:
        status='完整电气对照通过（热域等原跳过项保留）';details='0.3 s；21/21 统计；波形复核一致'
    elif c.get('pulse_status'):
        reason=c.get('diagnostic',{}).get('subcode','')
        status='有效前缀，完整案例未通过';details=f"{c['effective_end']:.12g} s；{reason}"
        if 'forward' in name:details+='；0.1–0.2 s 的 27/27 前缀统计通过'
    else:status='转换未支持';details=c.get('error','').replace('\n',' ').split('{')[0]
    previous='完整对照通过' if b.get('statistics_passed')==21 else b.get('diagnostic',{}).get('subcode','转换未支持')
    rows.append({'case':name,'before':previous,'after':status,'details':details})
save(out/'review_summary.json',{'full_comparison_passed':3,'prefix_only':3,'conversion_unsupported':14,'native_unchanged':True,'buck_boost_bitwise_unchanged':True,'forward_prefix':prefix,'cases':rows})

lines=['# 独立电气岛参考坐标修复与回归报告','',
'已在 Windows 副本修复独立浮置参考处理；Flyback 完整电气对照通过，Buck/Boost 无保存波形或事件退化。原始 v1.15 目录和 compare 冻结库未修改。','',
'## 修复内容','',
'- 编译时按物理端口连通图建立参考坐标。每个绕组只连接自身端口；磁耦合、传感器与控制信号不合并原副边。',
'- 对每个浮置岛，严格检查公共电位空空间 A*g=0、F*g=0 及 KCL 冗余，随后将一条冗余 KCL 换为本岛参考坐标方程。没有添加接地支路或更改电荷、磁链、INT 状态。',
'- 求解后与缓存命中时继续检查所有原始物理方程（含被替换 KCL）及新增参考坐标残差。',
'- 同岛差模电压正常支持；未定义的跨独立岛电压传感器以明确错误拒绝。V(node) 为相对本岛参考的电位。',
'- 保留现有十三原语、Markdown 语法、C ABI 结构、数值容差、原子时间和事务预算。参考节点按岛内节点名确定性选择；Flyback/Forward 的实际编译参考均为 REF1、REF2 两个独立节点。','',
'## Flyback 必须通过项','',
'直接运行 compare 原冻结 v002 网表（输入 SHA256 与修复前相同），保留 3 mH 励磁电感、500 µF 电容、初态、匝比和隔离拓扑。PULSE 与实时 PLECS 均到达 0.3 s，七个显示电气通道的 RMS/max/mean 共 21/21 项通过原 atol + 1% 相对容差。启动和稳态叠加图已直接复核一致。',
'','[启动叠加图](flyback_live/rohm-c010-d-flyback-v002/startup.png) · [稳态叠加图](flyback_live/rohm-c010-d-flyback-v002/steady.png) · [统计 CSV](flyback_live/rohm-c010-d-flyback-v002/statistics.csv) · [实际参考与端口清单](flyback_reference_inventory.json)','',
'## Buck/Boost 无退化验证','',
'两例均完成 0.3 s，各 21/21 项实时 PLECS 统计通过。进一步逐位比较修复前后全部保存时间轴、通道数组和事件日志：','',
'| 案例 | 时间点 | 保存通道 | 波形逐位一致 | 事件日志逐位一致 |','|---|---:|---:|---|---|']
for name,r in buckboost['cases'].items():lines.append(f"| {name} | {r['samples']} | {r['channels']} | 是 | 是 |")
lines+=['','实时 PLECS 基准数组也与修复前逐位一致，之前复核的叠加波形保持有效。证据见 [逐位回归结果](buck_boost_bitwise_regression.json)。','',
'## 原生测试','',
'- 9/9 CTest 通过。新增用例覆盖独立回路、浮置 RC 与接地 RC 物理状态等价、多绕组隔离、跨侧真实电容及初始电荷、未定义跨岛电压拒绝、浮置电路缓存开关一致性，以及真正冲突电源不能被掩盖。',
'- 20 个历史回归中仍有 19 个完成。原有 rectifier_pf 在同一有效终点 9.800004338636422 µs 因事务预算停止。',
'- 全部 20 例（含未完成例的已提交前缀）的保存波形、事件日志、状态和有效终点均与修复前一致。见 [历史回归逐位对比](native_bitwise_regression.json)。','',
'## 全部 20 个 compare 案例重测','',
'完整对照通过由修复前的 2 个增加到 3 个。另外 3 个原先 t=0 奇异的案例已进入有效仿真，但仍受其他问题限制，不能计为完整通过。14 个案例仍停在转换器未支持的控制模块/测量映射阶段。','',
'| Case | 修复前 | 修复后 | 说明 |','|---|---|---|---|']
for r in rows:lines.append('| '+ ' | '.join(r[k].replace('|','/') for k in ['case','before','after','details'])+' |')
lines+=['','## Forward 有效前缀','',
'原定 0.4 s 的同参数尝试运行至 0.24999976295501686 s，因原事务预算停止。没有提高预算或通过缩短原案例将其标为 PASS。复用该运行已提交的 PULSE 数据，与独立 PLECS 对照 0.1–0.2 s，九通道 27/27 项统计通过，启动与 0.2 s 附近稳态叠加图已复核。此结论只覆盖有效前缀。',
'','[前缀统计与状态](forward_prefix_02/summary.json) · [逐项统计](forward_prefix_02/statistics.json) · [启动](forward_prefix_02/startup.png) · [稳态](forward_prefix_02/steady.png)','',
'两个单相逆变器现在都运行到 0.8 µs，报 UNPREDICTED_GUARD_JUMP，原 t=0 的参考奇异已消除；未为它们增加寄生参数或改动换模算法。','',
'## 版本、范围与复现','',
'本次用户明确授权修复求解器参考 bug；该授权只用于此修复，历史禁止修改求解器的报告仍作为旧版记录保留。源码差异见 [补丁](source_changes.patch)，二进制与修改文件哈希见 [构建清单](build_manifest.json)。修改前源码、CLI 和 DLL 已保存在 baseline/，可用于复核和恢复。',
'','- 修改前 CLI SHA256：`'+manifest['baseline_binary_sha256']+'`。',
'- 修改后 CLI SHA256：`'+manifest['patched_binary_sha256']+'`。',
'','PLECS 使用本机正版 4.8.2 后台 RPC。采集窗为初始 5 ms、统计窗和末尾细节；没有宣称所有连续时刻的全历史逐点误差。截图不测量亚采样间隔误差，热域/损耗原跳过项保留。Flyback 的通过属于当前模型/工况的电气对照。',
'','所有新工具、缓存、临时目录与结果继续位于 D 盘；复用已安装 Codex Python。',
'','复跑：项目根目录 `./build_windows.ps1`；`./compare_windows.ps1 -Case rohm-c010-d-flyback,rohm-c006-d-buck,rohm-c002-d-boost`。其他案例结果保存在 other_cases/；每次自动对照创建新批次。']
(out/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')

p=root/'WINDOWS.md';s=p.read_text(encoding='utf-8')
s=s.replace('原目录和原 compare 库未修改。`src`、`include`、`apps` 和 CMakeLists.txt 共 26 个文件逐字节与原版一致。','原目录和原 compare 库未修改。当前 Windows 副本已按用户授权加入独立电气岛参考坐标修复；初始版本的 26 文件一致性记录属于修复前历史证据。\n\n**最新结果**：[隔离参考修复与完整回归报告](reports/island_reference_fix_20261027/REPORT.md)。Flyback 通过，Buck/Boost 全部保存波形及事件日志与修复前逐位一致。')
s=s.replace('8/8 CTest','9/9 CTest').replace('最终实时 PLECS 对照批次见 `reports/windows_compare_20261027_final/REPORT.md`。','最新实时 PLECS 对照和全案例重测见 `reports/island_reference_fix_20261027/REPORT.md`；旧 final 批次为修复前基线。')
p.write_text(s,encoding='utf-8')
p=root/'README.md';s=p.read_text(encoding='utf-8')
note='''
## Windows independent-reference fix (2026-10-27)

The Windows fork now assigns independent local voltage coordinates to physical
electrical islands while preserving all original KCL residuals and storage state.
Flyback completes 0.3 s and passes 21/21 live PLECS statistics. Buck/Boost saved
waveforms and event logs are bit-identical to the original Windows baseline.
Nine CTest targets pass; all 20 historical outputs/prefixes are unchanged,
including the pre-existing rectifier_pf transaction-budget stop. See
[the detailed report](reports/island_reference_fix_20261027/REPORT.md).
'''
assert '## Windows independent-reference fix' not in s
p.write_text(s+note,encoding='utf-8')
print(json.dumps({'report':str(out/'REPORT.md'),'full_passed':3,'prefix_only':3,'conversion_unsupported':14,'new_binary':manifest['patched_binary_sha256']},indent=2))
