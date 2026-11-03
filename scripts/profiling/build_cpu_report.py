#!/usr/bin/env python3
"""Build the report from saved Linux measurements, without running simulations."""
import csv
import gzip
import hashlib
import json
import pathlib
import re
import statistics
import subprocess

root=pathlib.Path(__file__).resolve().parents[2]
raw=root/'reports/a010-cpu-profile-20261103/native-evidence'
out=root/'docs/reports/a010_cpu_profile_20261103';out.mkdir(parents=True,exist_ok=True)
e=json.loads((raw/'collected.json').read_text(encoding='utf8'))
h=json.loads((raw/'linux-sampling/analysis-functions/hotspots.json').read_text(encoding='utf8'))
runs=[r for r in e['ledgers']['campaign']['runs'] if not r['label'].startswith('reconstruction')]
off=next(r for r in runs if r['label']=='500ms_off');on=next(r for r in runs if r['label']=='500ms_on')
sample=e['ledgers']['sampling']['runs'][0];q=on['report'];phases=q['performance_phases'];groups=h['groups']
assert not subprocess.check_output(['git','diff','6e5dea9bc5f7c03a5258a738725df474433a20b5','--','src','include','apps','CMakeLists.txt'],cwd=root)
counts={}
for line in (raw/'linux-call-counts/perf-stat.csv').read_text().splitlines():
    fields=line.split(';')
    if len(fields)>2 and fields[0].isdigit():counts[fields[2].split(':')[-1]]=int(fields[0])
assert set(counts)=={'multiply_digits','decimal_origin','flow_compatible','bind_observations'}
boundaries={}
with gzip.open(raw/'linux-sampling/perf-script-functions.txt.gz','rt',encoding='utf8') as f:
    for line in f:
        m=re.search(r'\s([0-9.]+):\s+(?:1\s+)?pulse_a010_20261103:(write_entry|write_return):',line)
        if m:boundaries[m[2]]=float(m[1])
write_wall=boundaries['write_return']-boundaries['write_entry']
payload=lambda r: [(s['kind'],s['sha256']) for s in r['archive']['sections'] if s['kind']!=1]
assert payload(off)==payload(on)==payload(sample)
twenty=next(r for r in runs if r['label']=='20ms_off_1')
count_run=e['ledgers']['call_counts']['runs'][0]
assert payload(twenty)==payload(count_run)

columns=['platform','run','target_seconds','profile_enabled','phase','wall_seconds','calls','mean_seconds_per_call','percent_of_completion_wall','completion_wall_seconds','exit_wall_seconds','process_cpu_seconds','measurement_basis']
phase_rows=[]
for r in runs:
    for name in ('mode','flow','roots','original_checks','closure','archive_append'):
        p=r['report']['performance_phases'].get(name)
        phase_rows.append(dict(zip(columns,['linux',r['label'],r['report']['simulated_seconds'],r['profile_enabled'],name,p['seconds'] if p else '',p['calls'] if p else '',p['seconds']/p['calls'] if p else '',100*p['seconds']/r['completion_wall_seconds'] if p else '',r['completion_wall_seconds'],r['exit_wall_seconds'],r['cpu_total_seconds'],'builtin steady_clock wall; off fields unmeasured, not zero'])))
with (out/'PHASE_TIMINGS.csv').open('w',newline='',encoding='utf8') as f:
    w=csv.DictWriter(f,fieldnames=columns);w.writeheader();w.writerows(phase_rows)

hotspots=list(csv.DictReader((raw/'linux-sampling/analysis-functions/hotspots.csv').open(encoding='utf8')))
for row in hotspots:
    n=row['function'];key=next((k for k,needle in [('multiply_digits','multiply_digits('),('decimal_origin','decimal_origin_from_binary_time('),('flow_compatible','Flow::compatible('),('bind_observations','bind_observations(')] if needle in n),None)
    row['entry_count_20ms_probe']=counts[key] if key else ''
    row['entry_count_scope']='independent 20ms counter run; not a 500ms invocation count' if key else 'not instrumented; sample hits are not calls'
    row['full_run_known_invocations']=''
    for needle,value in [('Flow::Flow(pulse::Mode',q['flow_statistics']['constructions']),('portfolio_original_check(',q['original_equation_cache']['checks']),('engineering::next_events(',q['root_queries']),('PevtArchive::Data::equation(',on['archive']['archive_counts']['equation_calls']),('PevtArchive::write(',1)]:
        if needle in n:row['full_run_known_invocations']=value
with (out/'FUNCTION_HOTSPOTS.csv').open('w',newline='',encoding='utf8') as f:
    w=csv.DictWriter(f,fieldnames=list(hotspots[0]));w.writeheader();w.writerows(hotspots)

telemetry=json.loads((raw/'linux-sampling/proc-telemetry.json').read_text())
e['sampling_analysis']=h;e['entry_counts_20ms']=counts;e['write_boundary_probe']={**boundaries,'wall_seconds':write_wall}
e['resource_telemetry']=telemetry;e['payload_sha256_equal_off_on_sampling']=True;e['payload_sha256_equal_20ms_off_counter']=True
e['scope_update']='User requested Linux only; Windows campaign stopped; completed reconstruction retained but excluded from all analysis below.'
for ledger in e['ledgers'].values():ledger['runs']=[r for r in ledger['runs'] if not r['label'].startswith('reconstruction')]
e['primary_sampling_export']='linux-sampling/perf-script-functions.txt.gz (physical ELF function frames; no inline expansion)'
e['auxiliary_export_notes']='Inline-expanded exports are retained as supplemental evidence. A redundant srcline export was cancelled after the physical-function export completed; it is not a statistical input.'
e['text_identity']={'linux_release_and_symbols':'8661f1d27e7c37342a44e4b3c62e7118bef45e77ccd0aaab68db3fccdd8795cd','flags':'Release -O3 -DNDEBUG; sampling adds -g1 only; -ffp-contract=off -fno-fast-math unchanged'}
e['windows_raw_mirror']=str(raw);e['branch']='profiling/a010-cpu-20261103'
e['sampling_command']=['/usr/lib/linux-tools/6.8.0-147-generic/perf','record','-e','cpu-clock','-F','199','-e','pulse_a010_20261103:write_entry','-e','pulse_a010_20261103:write_return','--call-graph','dwarf,16384','-o','/root/a010-cpu-profile-20261103/linux-sampling/perf.data','--','python3']+e['ledgers']['sampling']['command']
e['counter_command']=['/usr/lib/linux-tools/6.8.0-147-generic/perf','stat','--no-big-num','-x',';','-e','pulse_a010_count:multiply_digits,pulse_a010_count:decimal_origin,pulse_a010_count:flow_compatible,pulse_a010_count:bind_observations','-o','/root/a010-cpu-profile-20261103/linux-call-counts/perf-stat.csv','--','python3']+e['ledgers']['call_counts']['command']
e['counter_probe_symbols']=json.loads((raw/'count-probes.json').read_text())
e['write_probe_setup']=['p:pulse_a010_20261103/write_entry /root/pulse-a010-full-fix/build-profile/pulse-solver:0x1c68a0','r:pulse_a010_20261103/write_return /root/pulse-a010-full-fix/build-profile/pulse-solver:0x1c68a0']
e['temporary_probes_removed']=True
e['raw_mirror_verification']={'files_checked':113,'mismatches':0}
e['reproduction_commands']=[
 r'python3 scripts/profiling/run_a010_profile.py --binary /root/pulse-a010-full-fix/build-linux/pulse-solver --case /mnt/d/codex/using\ plecs/PULSE-case-set/rohm-a010-dot-totem-pole-pfc-sync --build-software /root/pulse-a010-full-fix/scripts/build_software.py --out /root/a010-cpu-profile-20261103/linux-campaign --campaign',
 '/usr/lib/linux-tools/6.8.0-147-generic/perf record -e cpu-clock -F 199 -e pulse_a010_20261103:write_entry -e pulse_a010_20261103:write_return --call-graph dwarf,16384 -o perf.data -- python3 scripts/profiling/run_a010_profile.py --binary /root/pulse-a010-full-fix/build-profile/pulse-solver --case CASE --build-software scripts/build_software.py --out SAMPLE_OUT --single .5',
 '/usr/lib/linux-tools/6.8.0-147-generic/perf script --no-inline --show-mmap-events --max-stack 1024 -i perf.data | gzip -1 > perf-script-functions.txt.gz',
 'python scripts/profiling/build_cpu_report.py']
(out/'EVIDENCE.json').write_text(json.dumps(e,ensure_ascii=False,indent=2)+'\n',encoding='utf8')

def label(n):
    if 'multiply_digits(' in n:return 'multiply_digits'
    if 'bind_observations(' in n:return 'bind_observations'
    if 'Flow::compatible(' in n:return 'Flow::compatible'
    return n.split('(')[0]

def gs(name):return groups[name]['cpu_seconds_estimate']
def gp(name):return groups[name]['total_cpu_percent']
lines=['# A010 CPU 性能剖析（Linux）','',
 '日期：2026-11-03。分支 `profiling/a010-cpu-20261103`；求解器基线 `6e5dea9bc5f7c03a5258a738725df474433a20b5`，验证基线 `186c9ed37bd11aa39d24fc2a769a8898a389068c`。已 fetch 核对远端，核心源码、头文件、CLI、CMake 均无差异。','',
 '本轮只分析原始 A010 的仿真计算与完整 trajectory 生成。模型、controller.c、transition.h、初始条件、SAVE_DT=0.1 µs、13 路模拟和 4 路数字输出保持不变。按用户后续指示停止 Windows，波形重建不在本报告统计范围；已完成产物保留。','',
 '## 测量与版本','',
 'AMD Ryzen 5 6600H，WSL2 Ubuntu 24.04、Linux 6.18.54.1、GCC 13.3、CMake 3.28.3。常规计时使用既有 Release；采样副本仅增加 -g1，仍为 -O3 -DNDEBUG，两个 ELF 的 .text SHA256 完全相同，严格浮点选项不变。全部运行的源码指纹为 `e820d1dcb9a84707d6f2333ee965ef188e7be78f5a55511cb963f8e71601ab60`。','',
 '常规测量按 2、5、20、500 ms 顺序进行；20 ms 关闭/开启交错各三次，完整 500 ms 关闭/开启各一次。CPU 时间来自 OS 的子进程 user+system，墙钟从命令启动到完整事件文件写出后的 COMPLETED 通知，另记录进程退出。Python/控制器准备与归档校验在计时之外。原始逐次命令、UTC 时间、PID、文件 SHA256 见 EVIDENCE.json。','',
 '| 运行 | 完成墙钟 / s | CPU / s | 事务 |','|---|---:|---:|---:|']
for r in runs:lines.append(f"| {r['label']} | {r['completion_wall_seconds']:.6f} | {r['cpu_total_seconds']:.6f} | {r['report']['transactions']:,} |")
ov=e['ledgers']['campaign']['20ms_overhead']
lines+=['',f"20 ms 关闭中位数 **{ov['median_seconds']['off']:.6f} s**，开启 **{ov['median_seconds']['on']:.6f} s**，相对差 **{ov['percent']:.3f}%**。负差值属于本轮测量波动，不是加速收益；三次测量不足以给出严格开销上界。完整开/关墙钟分别 {on['completion_wall_seconds']:.6f}/{off['completion_wall_seconds']:.6f} s，同样未观察到可稳定分辨的内置计时开销。",'',
 '## 各窗口阶段墙钟','', '| 窗口 | mode | flow | roots | original_checks | closure | archive_append |','|---|---:|---:|---:|---:|---:|---:|']
for end in (.002,.005,.02,.5):
    selected=[r for r in runs if r['profile_enabled'] and r['report']['simulated_seconds']==end]
    values=[statistics.median(r['report']['performance_phases'][name]['seconds'] for r in selected) for name in ('mode','flow','roots','original_checks','closure','archive_append')]
    lines.append('| '+str(end*1000)+' ms | '+' | '.join(f'{v:.6f}' for v in values)+' |')
lines+=['', '20 ms 行为三次各阶段中位数，其余为单次。完整逐次数据见 PHASE_TIMINGS.csv。500 ms 开启计时的细节如下：','', '| 阶段 | 总墙钟 / s | Scope 次数 | 每次 / µs | 占完成墙钟 |','|---|---:|---:|---:|---:|']
for name in ('mode','flow','roots','original_checks','closure','archive_append'):
    p=phases[name];lines.append(f"| {name} | {p['seconds']:.6f} | {p['calls']:,} | {1e6*p['seconds']/p['calls']:.3f} | {100*p['seconds']/on['completion_wall_seconds']:.2f}% |")
lines+=['', '这些是 steady_clock 墙钟范围，不是互斥 CPU 分类；存在未覆盖区间，也不能把百分比相加视为 100%。original_checks 的 159,037 次 Scope 内每次执行三个检查，真实验证总数为 477,111。flow Scope 只覆盖事务开始时的 Flow 选择/延续，不能代表全部 478,908 次构造。', '',
 '## 独立 CPU 采样','',
 f"使用完整 Ubuntu perf 6.8.12，cpu-clock 199 Hz、DWARF 栈 16 KiB；对同一最新代码另跑完整 500 ms，关闭内置阶段计时。采样运行完成墙钟 {sample['completion_wall_seconds']:.6f} s，退出 {sample['exit_wall_seconds']:.6f} s；CPU {sample['cpu_total_seconds']:.6f} s（user {sample['cpu_user_seconds']:.6f}，system {sample['cpu_system_seconds']:.6f}）。共记录 21,121 个样本，其中目标 PID 的 CPU 样本 **{h['sample_count']:,}** 个；已过滤 Python/编译器。原始 perf.data 为约 336 MB，完整保存。",'',
 'Self 是采样叶函数占比，Total 是包含子调用的栈占比；Total 彼此重叠。CPU 秒为 OS 总 CPU × 样本权重占比的估计，不是独立函数秒表。函数排行以无内联展开的物理 ELF 栈为主；匹配的 libc 调试符号已补齐。内联展开存在优化范围别名，不能当成额外真实调用；补充导出完整保留。', '',
 '| 排名 | 函数（缩写） | Self CPU | Total CPU | 源码/归属 |','|---|---|---:|---:|---|']
for r in hotspots[:20]:
    source=r['source_file_line'];source=source.replace('/root/pulse-a010-full-fix/','').replace('./malloc/./malloc/','glibc/malloc/')
    if 'Flow::compatible' in r['function']:source='src/engineering_flow.cpp（采样指令落在 char_traits.h）'
    lines.append(f"| {r['rank']} | {label(r['function'])[:100]} | {float(r['self_cpu_percent']):.2f}% | {float(r['total_cpu_percent']):.2f}% | {source} |")
lines+=['', 'FUNCTION_HOTSPOTS.csv 保存全部物理函数排名、完整符号、源码行、Self/Total 样本、采样命中/CPU 秒、代表调用栈以及已知调用计数。内联函数不具备可独立探测的入口；其开销记在实际承载代码的物理函数中。','',
 '### 入口计数与调用栈','',
 '独立 20 ms uprobe 入口计数如下。此计数运行约 8.02 s，比正常运行更慢，只用于调用次数；不混入前述基准或内置计时开销。未对 malloc/free 等全部函数设入口探针，相关真实调用频率列为未知，不能把样本数当作调用次数。','',
 '| 函数 | 20 ms 实际调用数 | 每事务调用数（8,306 次事务） |','|---|---:|---:|']
for name,value in counts.items():lines.append(f'| {name} | {value:,} | {value/8306:.3f} |')
lines+=['', '代表性真实路径（完整符号栈见 CSV 和原始导出）：','',
 '- `main → simulate → exact_time_origin → decimal_origin_from_binary_time → multiply_digits`。',
 '- `simulate → closure → engineering::update_mode / portfolio_compile → compile_specified → bind_observations`。',
 '- `simulate → closure → software::Session::execute → Data::call → state_signal → Flow::compatible`。',
 '- `simulate → engineering::next_events → Flow::value / Flow::bounds`。',
 f"采到 engineering::next_events 的栈 **{h['routing']['engineering_next_events_samples']}** 个；`fri::` 和 `first_root.cpp` 均为 **0**。这确认本次 A010 主要根搜索位于 engineering_flow.cpp；零样本不构成数学上的绝不调用证明，但没有证据把 first_root.cpp 当作主要热点。",'',
 '## 十项问题的测量回答','',
 f"1. 约 103 秒主要耗在哪里：本次复现为 {off['completion_wall_seconds']:.2f} s。closure 范围墙钟 47.70 s，mode 11.21 s；物理调用栈中 bind_observations 含子调用约 {gp('bind_observations'):.2f}% CPU，精确时间来源转换 {gp('decimal_origin'):.2f}%，软件 Data::call {gp('software_Data_call'):.2f}%，分配/释放路径并集 {gp('allocation_free_union'):.2f}%。这些口径重叠，不能累加。",'',
 '2. 仍有重复计算：20 ms 入口计数证实 339 万次十进制乘法、4.2 万次兼容性检查、1.9 万次绑定。采样把实际成本定位到这些路径；不是根据调用次数推导 CPU 占比。完整运行仅 26 次模态编译、19 次原方程构建，当前主要问题不是每次重新 LU/QR。','',
 f"3. 每事务平均 CPU：{off['cpu_total_seconds']:.6f} / {q['transactions']} = **{off['cpu_total_seconds']/q['transactions']*1e6:.2f} µs**。这是包含初始化、归档、最终写出和清理的摊销值，不是逐事务计时。",'',
 f"4. 477,111 次原方程验证：阶段墙钟 **{phases['original_checks']['seconds']:.6f} s**；独立采样 portfolio_original_check 含子调用约 **{gs('portfolio_original_check'):.3f} CPU s / {gp('portfolio_original_check'):.2f}%**，摊销约 {gs('portfolio_original_check')/477111*1e6:.2f} µs/次（估计）。",'',
 f"5. 478,908 次 Flow 构造：物理构造函数含子调用约 **{gs('Flow_constructor'):.3f} CPU s / {gp('Flow_constructor'):.2f}%**，约 {gs('Flow_constructor')/478908*1e6:.2f} µs/次（估计）。Flow::continued 约 {gs('Flow_continued'):.3f} CPU s，Flow::compatible 约 {gs('Flow_compatible'):.3f} CPU s；它们不是同一计数口径，不能简单相加。",'',
 f"6. 根搜索：159,036 次 root_queries；阶段墙钟 **{phases['roots']['seconds']:.6f} s**，engineering::next_events 含子调用约 **{gs('engineering_next_events'):.3f} CPU s / {gp('engineering_next_events'):.2f}%**。不是当前主导热点。",'',
 f"7. 归档：append 含子调用约 **{gs('archive_append'):.3f} CPU s**，其中 equation 去重路径约 **{gs('archive_equation_dedup'):.3f} CPU s**（已包含于 append，不能重复加）。最终 PevtArchive::write 入口/返回直接测得 **{write_wall:.6f} s 墙钟**；其物理栈约 **{gs('archive_write'):.3f} CPU s**。此范围包含复制、序列化、SHA256 和文件写入，不是纯磁盘 I/O。",'',
 '8. 可优先减少的重复工作：绑定中的重复范数/缩放准备和临时对象；精确时间转换的重复常量乘法准备与分配；同一不可变软件输入快照逐通道重复兼容性检查。方案和收益假设见 OPTIMIZATION_PLAN.md，本轮没有实施。','',
 '9. 不能安全直接删除：真实状态传播和根定位、原方程/残差校验、联合事件闭合、事务回滚及 C 状态独立性、T128 精确时间来源、完整通道/事件状态记录、完整性哈希。所有缓存都需不可变输入和完整失效条件，不能以计数很大为由跳过校验。','',
 '10. 只选三个核心实现文件进入下一轮：**src/descriptor.cpp、src/time_origin.cpp、src/software.cpp**。分别对应实测绑定、精确时间转换、软件输入读取中的重复检查。runtime.cpp 的快照复制和 engineering_flow.cpp 的兼容性路径是后续结构工作；first_root.cpp 没有进入当前优先级。','',
 '## 资源使用、计数与时间边界','',
 f"关闭 Profile 时总进程 CPU/退出墙钟为 **{100*off['cpu_total_seconds']/off['exit_wall_seconds']:.2f}% 的单逻辑核**。末段 27 个 1 Hz /proc 样本均为 1 个线程，观察到最大 RSS {max(s['rss_kb'] for s in telemetry['samples'])/1048576:.3f} GiB，VmHWM {max(s['hwm_kb'] for s in telemetry['samples'])/1048576:.3f} GiB。遥测在进程启动后才接入，峰值是最终峰值的下界，不宣称整段内存峰值已完整捕获。",'',
 f"simulate 报告范围关闭/开启为 {off['report']['run_seconds']:.6f}/{on['report']['run_seconds']:.6f} s，均包含在线 archive_append；不能称作纯数值求解时间。最终写函数约 {write_wall:.3f} s；程序完成/退出另记。未覆盖差额还包含报告构造、输出缓冲和对象清理，不全部归入写文件。波形重建排除。",'',
 '| 指标 | 500 ms 实测 |','|---|---:|',
 f"| transactions / root_queries | {q['transactions']:,} / {q['root_queries']:,} |",
 f"| mode_compilations / mode_cache_hits | {q['mode_compilations']} / {q['mode_cache_hits']:,} |",
 f"| Flow constructions / continuations | {q['flow_statistics']['constructions']:,} / {q['flow_statistics']['continuations']:,} |",
 f"| basis hits / misses | {q['flow_statistics']['basis_hits']:,} / {q['flow_statistics']['basis_misses']} |",
 f"| original checks / builds / hits | {q['original_equation_cache']['checks']:,} / {q['original_equation_cache']['equation_builds']} / {q['original_equation_cache']['cache_hits']:,} |",
 f"| archive equation requests / definition encodes / hits | {on['archive']['archive_counts']['equation_calls']:,} / {on['archive']['archive_counts']['definition_encodes']} / {on['archive']['archive_counts']['definition_hits']:,} |",'',
 '## 证据与未确定事项','',
 '开、关 Profile 和采样三次完整运行的归档段 2–10 SHA256 逐段一致；20 ms 计数运行也与普通 20 ms 运行的这些段完全一致。段 1 含性能和平台元数据，允许不同。所有归档段 SHA256 均独立核对，17 路公开输出完整。','',
 '原始 perf.data、压缩调用栈、阶段报告、控制器构建记录、事件文件、计数器和匹配二进制均保存在本地，未将二进制产物加入 Git。Windows 镜像：`reports/a010-cpu-profile-20261103/native-evidence/`；WSL 原始目录：`/root/a010-cpu-profile-20261103/`。EVIDENCE.json 保存逐文件字节、SHA256、绝对路径、机器、命令和时间。','',
 '尚未确定：所有 malloc/模板函数的真实调用次数；部分 libstdc++ 外部源码行；采样统计误差及截断/尾调用造成的 Total 低估；长时稳定性和严格计时开销上界；各方案的实际收益。少量内联范围与写函数真实边界冲突，因此主结论采用物理函数栈，不拿内联别名当真实入口。','',
 '本轮不重做波形精度验收，也不声称既有 CH006/CH007 逐点偏差已解决。没有修改核心源码，没有执行优化方案，没有用缩短案例或减少通道获得完整运行结果。','']
(out/'CPU_PROFILE.md').write_text('\n'.join(lines),encoding='utf8')
plan='''# 下一轮优化方案（本轮未实施）

所有收益均为估计，不是测试结果。以物理调用栈的 CPU 预算确定优先级，保留完整状态、事件、回滚、精确时间与校验语义；不得把调用频率当作 CPU 占比。不同路径与分配开销重叠，不将估计收益直接相加。

| 顺序 | 文件与具体工作 | 实测含子调用预算 | 收益估计与假设 |
|---|---|---|---|
| 1 | src/descriptor.cpp：bind_observations 中对同一不可变 A 的行范数缓存；每次回填的 N 列范数/B 行范数只算一次；复用 scratch 缓冲，保持原残差表达式和规约顺序 | 18.79 CPU s / 18.04% | 假设可减少该路径 10–30%，约 1.9–5.6 CPU s；未验证，原残差检查全部保留 |
| 2 | src/time_origin.cpp：复用精确整数转换的工作缓冲和可复用常量准备，审查避免每次转换大量小对象分配；仍输出逐位相同的十进制来源 | 17.42 CPU s / 16.72% | 假设减少该路径 30–50%，约 5.2–8.7 CPU s；不得改用近似 double 时间或改变 T128 定义 |
| 3 | src/software.cpp：同一不可变输入快照批量读取时只验证一次 Flow 兼容性，逐通道保留原 observe/dot/BOOL/literal 分支与原坐标；C 控制器及其独立状态不变 | 软件调用 13.28 CPU s，其中与兼容性检查交集约 4.95 CPU s | 假设减少交集 50–80%，约 2.5–4.0 CPU s；失效范围必须严格限定在同一次不可变快照 |
| 4 | runtime.cpp / Mode、RunState 相关结构：共享不可变方程/映射，减少检查点与候选状态对静态部分的深复制；动态状态和回滚仍独立 | Mode 复制约 16.22 CPU s，RunState 复制约 7.85 CPU s；彼此和前三项重叠 | 可能有收益，但需结构/头文件变更和更广回归，不纳入第一轮只改三文件的承诺 |
| 5 | engineering_flow.cpp：兼容性检查证明和快照生命周期绑定，复用已有验证结果；不能用指针或 mode.id 单独代替完整有效性条件 | Flow::compatible 8.52 CPU s | 软件批处理已覆盖其中部分，剩余收益需另量，不能重复计算 |
| 6 | pevt.cpp：避免去重键/临时块重复分配，缓冲序列化与写出，保持完整事件切片、方程、哈希和协议 | append 5.47 CPU s（其中去重 3.33），最终写 1.78 CPU s | 仅为次级预算；不删除诊断或物理输出，不把全部总用时归因于 I/O |

三文件首轮选择是 descriptor.cpp、time_origin.cpp、software.cpp，来自实际 CPU 证据；不是因为它们都属于上一次五文件补丁。任何精确整数转换的新实现若超出缓冲复用，应单独审查，不视作本轮授权。

后续验证门槛：同原始网表与控制器；2/5/20/500 ms；事件 T128、事务顺序、前后模态、完整状态/值集/Flow 归档段一致；全部 17 通道保留；原方程残差/容差/校验次数不减；C 状态及回滚测试通过；20 ms 开关计时各至少三次。若出现数值路径差异，保留最小复现，不通过放宽容差或换参考数据处理。

根定位只占约 2.73%，完整 A010 的主要栈没有出现 fri::/first_root.cpp，因此不优先重构该文件；LU/QR、矩阵指数、根判据、联合事件和物理模型不在这些建议的删除范围。
'''
(out/'OPTIMIZATION_PLAN.md').write_text(plan,encoding='utf8')
print('Created five requested artifacts:',out)
print('CPU per transaction us:',off['cpu_total_seconds']/q['transactions']*1e6)
print('Full write boundary seconds:',write_wall)
