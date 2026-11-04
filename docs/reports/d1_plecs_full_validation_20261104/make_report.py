import csv,json,pathlib,collections
P=pathlib.Path('/workspace/pulse-d1-validation');d=json.loads((P/'evidence.json').read_text());rows=sorted(d['cases'],key=lambda r:r['case']);good=[r for r in rows if r.get('full_trajectory_completed')];comp=[r for r in rows if r.get('accuracy_status')=='COMPARED']
def f(x,n=3):return '—' if x is None else f'{x:.{n}f}'
def reason(r):

 if not r.get('full_trajectory_completed') and r.get('status') in ('COMPLETED','ARCHIVE_WRITE_FAILED') and r.get('generation',{}).get('exit_code')!=0:
  err=P/r['folder']/'generation-log/stderr.txt'
  try:
   return '归档写出失败：'+json.loads(err.read_text()).get('message','')
  except Exception:return '归档写出失败'
 diag=r.get('diagnostic') or {};return r.get('timeout_label') or diag.get('subcode') or r.get('stderr','')[-250:].replace('\n',' ') or r['status']
s=['# PULSE D1 与 PLECS 全时验证报告','',f"固定分支：`{d['solver_branch']}`；提交：`{d['solver_commit']}`。该提交相对 D1 算法修复提交 `05fb315` 仅增加报告，求解器源码相同。案例参考：[PULSE-case-set 固定提交](https://github.com/Tuzki/PULSE-case-set/tree/{d['case_set_commit']})。",'',f"案例集共有 20 例，其中 19 例有 PULSE 网表。已记录 {len(rows)}/20 例；完整生成轨迹 {len(good)} 例，完成全区间精度对照 {len(comp)} 例。",'','## 对照口径','','- PULSE 用时为本次云实例单次进程墙钟：包含 CLI 启动、解析、求解和完整轨迹写出；排除控制模块编译及波形重建。串行运行，不取多次最优值。','- PLECS 用时是 case-set 在 2026-11-01 保存的 PLECS 4.8.2 simulate RPC 测量，来自另一台机器和另一轮执行。用时比只描述这两条记录，不是同机加速比。','- 体积用十进制 MB。事件轨迹占用包括 out.pevt 和 simulation_report.json；另列出核心 out.pevt 大小。重建波形和本次诊断日志不计入轨迹占用。PLECS 体积为原始未压缩参考 CSV 各分片总和；两种存储格式不同。','- 完整仿真窗口使用原厂 PLECS 时长，通过 CLI --t-end 指定，不改网表及控制源。案例库包含历史未通过候选，不能据有网表认定通过。','- 重建单独运行，并指定 1 µs 网格与 PLECS 对齐。时间轴逐点核对，无时轴平移、无开关边沿剔除。若 PULSE 在终点额外输出相隔小于 1 ps 的两个样本，保留最后提交状态与 PLECS 终点对齐。','- 20 点取完整 PLECS 网格中近似等距的 20 个索引，含首尾；逐通道 E(t)=100×|PULSE(t)−PLECS(t)|/mean(|PLECS|)。分母为完整 1 µs 参考网格（含首尾）的绝对值算术平均，零分母百分比留空。','- 另对全波均值、RMS、最小值、最大值逐通道计算差异，百分比同样除以全波绝对值均值。未指定验收阈值，报告偏差而不自行宣布精度通过。','- PULSE 重建的模拟通道以 float32 保存，PLECS CSV 以 17 位有效数字保存；微小差异包含输出量化，1 µs 网格上的结果不构成连续时间精度证明。','- 每进程内存地址空间限制 8 GiB；生成墙钟预算为对应历史 PLECS 用时的 5 倍（超过即停止并标记超时）；重建预算600秒。超时不计作全时长完成，不以有效前缀代替全段精度。','- A002 的 PULSE 是既有20 µs ZOH控制，而PLECS为原厂连续控制；其偏差包含模型/控制差别，不能仅归因于数值算法。','- A021-D 的本轮求解报告列出14个模拟通道，而 PLECS 参考有18个；缺少 MOS_JUNCTION_TEMP_C、MOS_HEATSINK_TEMP_C、DIODE_JUNCTION_TEMP_C、DIODE_HEATSINK_TEMP_C 四个热通道。本轮事件流归档也未完成。','', '## 完整轨迹结果','','| Case | 仿真时长 s | PLECS历史用时 s | PULSE轨迹生成 s | PLECS/PULSE用时比¹ | PLECS CSV MB | 轨迹总 MB | PEVT MB | 精度状态 |','|---|---:|---:|---:|---:|---:|---:|---:|---|']
if comp and (P/'POINTS20.csv').exists() and (P/'STATISTICS.csv').exists():
 points=[x for x in csv.DictReader((P/'POINTS20.csv').open()) if x['error_pct_mean_abs']]
 rms=[x for x in csv.DictReader((P/'STATISTICS.csv').open()) if x['metric']=='rms' and x['error_pct_mean_abs']]
 worst=max(points,key=lambda x:float(x['error_pct_mean_abs']))
 worst_rms=max(rms,key=lambda x:float(x['error_pct_mean_abs']))
 counts={k:sum(r['status']==k for r in rows) for k in ('TIMEOUT_5X_PLECS','ARCHIVE_WRITE_FAILED','STOPPED_UNRESOLVED','STOPPED_ERROR','NO_NETLIST')}
 summary=['## 主要发现','',f"- 19 个有网表案例中，{len(good)} 例完整生成事件流；{counts['TIMEOUT_5X_PLECS']} 例超时，{counts['ARCHIVE_WRITE_FAILED']} 例归档失败，{counts['STOPPED_UNRESOLVED']+counts['STOPPED_ERROR']} 例数值或初始化失败。另有 1 例无网表。",f"- 20 点中最大偏差出现在 {worst['case']} {worst['channel']} 的 {float(worst['time_s']):g} s：PLECS={float(worst['plecs']):.6g}，PULSE={float(worst['pulse']):.6g}，按该通道 PLECS 全波绝对值均值归一化为 {float(worst['error_pct_mean_abs']):.3f}%。",f"- 全波 RMS 统计偏差最大的是 {worst_rms['case']} {worst_rms['channel']}，同一归一化口径下为 {float(worst_rms['error_pct_mean_abs']):.3f}%。各案例的最大值可能来自不同通道。",'']
 idx=s.index('## 对照口径');s[idx:idx]=summary
for r in good:s.append(f"| {r['case']} | {r['target_seconds']:g} | {f(r['plecs_rpc_seconds'])} | {f(r['trajectory_generation_seconds'])} | {f(r['historical_plecs_over_pulse_time_ratio'])} | {f(r['plecs_csv_bytes']/1e6)} | {f(r['trajectory_archive_bytes']/1e6)} | {f(r['segments_bytes']/1e6)} | {r.get('accuracy_status','未取得')} |")
s+=['','¹ 不同机器和批次的测量比，不能解释为同机性能提升。','','## 精度摘要','','下表取各案例所有已对齐电气通道中最大的20点百分比偏差；逐通道、逐时刻数值见 POINTS20.csv。全波统计见 STATISTICS.csv。单个汇总数不代替逐通道结果。','','| Case | 已对照通道数 | 20点最大偏差 % | 缺失通道 |','|---|---:|---:|---|']
for r in comp:s.append(f"| {r['case']} | {r['compared_channels']} | {f(r.get('points20_max_error_pct'),6)} | {', '.join(r.get('missing_channels',[])) or '无'} |")

statfile=P/'STATISTICS.csv'
if statfile.exists():
 stats=list(csv.DictReader(statfile.open()))
 s+=['','### 全波统计值偏差摘要','','逐通道统计值差异除以对应 PLECS 全波绝对值均值。下表每列取本案例已比较通道中的最大值（%）。完整原始统计值及差异见 STATISTICS.csv。','','| Case | 均值偏差 % | RMS偏差 % | 最小值偏差 % | 最大值偏差 % |','|---|---:|---:|---:|---:|']
 for r in comp:
  vals=[]
  for metric in ['mean','rms','min','max']:
   a=[float(x['error_pct_mean_abs']) for x in stats if x['case']==r['case'] and x['metric']==metric and x['error_pct_mean_abs']]
   vals.append(f(max(a) if a else None,6))
  s.append('| '+r['case']+' | '+' | '.join(vals)+' |')
s+=['','## 未完整交付的案例','','| Case | 目标时长 s | 有效仿真终点 s | 返回/停止用时 s | 5倍上限 s | 残留产物 MB² | 状态/诊断 |','|---|---:|---:|---:|---:|---:|---|']
for r in rows:
 if not r.get('full_trajectory_completed'):s.append(f"| {r['case']} | {r['target_seconds']:g} | {f(r.get('simulated_seconds'),9)} | {f(r.get('generation',{}).get('wall_seconds'))} | {f(5*r['plecs_rpc_seconds'])} | {f(sum(r.get('archive_components',{}).values())/1e6)} | {reason(r).replace('|','/')} |")
s+=['','² 失败或超时后残留的轨迹目录文件，可能缺少元数据或完整性校验，不是可交付的完整事件流；不计算其压缩比或精度。','','所有超时标签按原厂 PLECS 历史记录用时的5倍计算。','','## 验证与文件','','- [CTEST.log](CTEST.log)：本轮 Linux Release 原生测试 36/36 通过；[MACHINE.json](MACHINE.json) 记录环境与编译工具。','- [AUDIT.log](AUDIT.log) 记录统计与逐点数值、图件、源文件哈希和报告链接的独立检查。',f"- 所有已运行案例的原始网表/控制源哈希保持一致：{all(r['inputs_unchanged'] for r in rows)}。",'- [SUMMARY.csv](SUMMARY.csv)：逐案例时间和空间占用；[CHANNEL_ACCURACY.csv](CHANNEL_ACCURACY.csv)：逐通道误差；[STATISTICS.csv](STATISTICS.csv)：全波统计；[POINTS20.csv](POINTS20.csv)：20点明细。','- [evidence.json](evidence.json)：版本、二进制及输入哈希、命令、独立计时、资源预算、错误信息、轨迹组件字节数。云环境中的每个案例目录保留原始事件流和重建波形；GitHub 报告只包含统计、逐点数据、图片、证据及复算脚本，不包含大型 PEVT/NPZ 文件。','- 本次没有运行新的 PLECS；没有修改求解算法、网表、控制代码或数值容差。']

s+=['','## 波形叠图','','未完整生成或无法重建波形的案例没有完整叠图；缺少 PULSE 通道时，图中仅展示 PLECS 并标注缺失。图中连线连接参考网格采样点，可能漏掉网格之间的开关边沿。','',('全时图和末 1 ms 图均绘制相应时间范围内参考网格的全部采样点；统计和20点计算均使用完整1 µs 数据。' if (P/'PLOT_MANIFEST.json').exists() else '当前为临时预览图；最终交付前将重新绘制完整参考网格全部采样点。统计和20点计算使用完整1 µs 数据。'),'']
for r in comp:
 plotdir=P/r['folder']/'plots'
 if plotdir.is_dir():
  s+=['### '+r['case'],'','[20点逐通道明细]('+r['folder']+'/POINTS20.csv) · [全波统计明细]('+r['folder']+'/STATISTICS.csv)','','<details><summary>展开通道叠图</summary>','']
  for f in sorted(plotdir.glob('*.png')):s+=['#### '+f.stem,'','!['+f.stem+']('+r['folder']+'/plots/'+f.name+')','']
  s+=['</details>','']
(P/'REPORT.md').write_text('\n'.join(s).rstrip()+'\n')
print(f'{len(rows)} recorded; {len(good)} trajectories; {len(comp)} accuracy comparisons')
