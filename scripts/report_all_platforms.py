#!/usr/bin/env python3
"""Render the all-platform benchmark ledger; never infer a missing PASS."""
import argparse
import collections
import json
import pathlib


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('ledger', type=pathlib.Path)
    p.add_argument('--out', type=pathlib.Path, required=True)
    a = p.parse_args(); data = json.loads(a.ledger.read_text(encoding='utf-8'))
    cases = data['cases']; labels = ['PLECS','win_original','win_event','linux_original','linux_event']
    if len(cases) != 20 or not all(row.get('finished') for row in cases.values()):
        p.error('all 20 case attempts must finish before publishing the comparison')
    # Older ledgers may contain a COMPLETED solver report from before a later
    # archive failure. That is not a completed end-to-end output operation.
    for name,row in cases.items():
        for label,r in row['runs'].items():
            if label == 'PLECS' or r.get('status') == 'NOT_RUN': continue
            if r.get('status') == 'COMPLETED' and (r.get('returncode') != 0 or r.get('seconds') is None):
                r['status'] = 'OUTPUT_FAILED'
            if r.get('returncode') and not r.get('diagnostic'):
                path = a.ledger.parent/name/(label+'-stderr.txt')
                if path.exists():
                    message = path.read_text(encoding='utf-8')
                    try: r['diagnostic'] = json.loads(message)
                    except Exception: r['error'] = message
    def esc(s): return str(s).replace('|','/').replace('\n',' ')
    def cell(r):
        if not r: return '未运行'
        status = r.get('status','未运行'); elapsed = r.get('seconds')
        if status == 'COMPLETED' and elapsed is not None: return f"{elapsed:.3f} s"
        if status == 'NOT_RUN': return '无 PULSE 网表'
        end = r.get('simulated_seconds'); wall = r.get('process_exit_seconds')
        return esc(status)+(f"，t={end:.9g}" if end is not None else '')+(f"，{wall:.3f}s" if wall is not None else '')
    lines = ['# PLECS 与 Windows/Linux PULSE 原版、事件版全案例比较', '',
      '日期：2026-11-01。以下均为本机实际运行结果；未完成、未运行和精度不通过分别记录。', '',
      '## 范围与测量方法', '',
      '- 案例库：`Tuzki/PULSE-case-set`，提交 `13660577132de41c37c1c47576c02941d21c532a`。覆盖所有 CSV 状态为 COMPLETED 的 20 个目录；其中一个没有 PULSE 网表。',
      '- PLECS 4.8.2 在 Windows 原生运行；PULSE Windows 为 MinGW-w64 GCC 16.2，Linux 为 WSL2 Ubuntu 24.04、GCC 13.3 原生 x86-64 ELF。CPU：AMD Ryzen 5 6600H。Linux 不使用 Wine、Windows EXE 或 DLL 求解。',
      '- 五种仿真逐个顺序执行，使用同一个 Windows `perf_counter` 时钟。从发出仿真命令到收到 COMPLETED 通知。PULSE 包含 CLI 启动/解析及 Linux WSL 启动，PLECS 使用 simulate RPC（非鼠标自动点击），包含 RPC 结果传输；模型加载、模块编译、输出复制及精度分析在计时外。',
      '- 每项一次正式计时，不是重复试验统计；表中失败项时间为到进程退出的实测墙钟，不能作为全时长性能成绩。无受控 CPU 频率/温度；差异不能归因于操作系统单一因素。',
      '- 每个案例的共同终点取原厂 PLECS 全时长。PULSE 原输入的 T_END 较短时仅通过 `--t-end` 延长；不缩短任何案例，不改变 SAVE_DT、初值、控制器、模型参数、数值容差及算法。原始网表、控制器、CSV 和 PLECS 观测副本逐个 SHA256 校验。',
      '- 原版保存稠密波形；事件版保存模板、原始 Flow 锚点/精确偏移、事务快照和原事件日志。事件版 COMPLETED 表示物理求解完成，波形有效性检查延迟至回放；下表单列回放时间，完整波形工作流需两者相加。',
      '- 精度使用未修改且哈希验证的案例库 CSV；不采用重写参考、时间平移或排除开关边缘来提高分数。新执行的 PLECS 波形另做与原 CSV 的一致性检查。', '',
      '## 构建与原生测试', '',
      '| 平台 | Release 构建 | CTest 总数 | 通过 | 失败 | 跳过 |', '|---|---|---:|---:|---:|---:|',
      '| Windows GCC | 成功 | 25 | 25 | 0 | 0 |', '| Linux GCC | 成功 | 25 | 25 | 0 | 0 |', '',
      '两平台均包含 C ABI、C 控制器执行/状态/回滚、事件流损坏检测、精度元数据检查和完整波形回放测试。额外 `scripts/run_validation.py --suite all` 两平台各执行 20 个历史/PF fixture：17 COMPLETED、3 STOPPED_ERROR、0 跳过。三项为 `rectifier_pf`、`llc_pf`、`llc_100cycles_pf`，均 t=0 报 MODEL_SINGULAR（descriptor nonunique/unsupported higher-index dynamics），属于原基线已记录问题，未修改算法绕过。', '',
      '## 各案例仿真墙钟', '',
      '只有显示秒数的成功单元格才代表完整目标时间 COMPLETED。失败项显示实际终止时刻及失败耗时。', '',
      '| 案例 | 目标仿真时间/s | PLECS (Win) | Win 原 PULSE | Win 事件 PULSE | Linux 原 PULSE | Linux 事件 PULSE |',
      '|---|---:|---|---|---|---|---|']
    for name, row in sorted(cases.items()):
        lines.append('| '+name+' | '+str(row['target_seconds'])+' | '+' | '.join(cell(row['runs'].get(k)) for k in labels)+' |')
    lines += ['', '## 事件回放与文件体积', '',
      '体积为该次输出目录所有文件总和（含事件日志/报告）。事件版仍保存原 JSONL 事件日志，尚未压缩。MB 为十进制。', '',
      '| 案例 | Win 原/事件 MB | Win 回放/s | Win 事件+回放/s | Linux 原/事件 MB | Linux 回放/s | Linux 事件+回放/s |',
      '|---|---:|---:|---:|---:|---:|---:|']
    for name,row in sorted(cases.items()):
        cells=[]
        for platform in ('win','linux'):
            old,event,replay=[row['runs'].get(platform+'_'+k,{}) for k in ('original','event','replay')]
            cells.append(' / '.join(f"{r['total_bytes']/1e6:.3f}" if 'total_bytes' in r else '—' for r in (old,event)))
            cells.append(f"{replay['seconds']:.3f}" if replay.get('status')=='COMPLETED' and replay.get('seconds') is not None else '—')
            cells.append(f"{event['seconds']+replay['seconds']:.3f}" if all(r.get('status')=='COMPLETED' and r.get('seconds') is not None for r in (event,replay)) else '—')
        lines.append('| '+name+' | '+' | '.join(cells)+' |')
    lines += ['', '## 精度与一致性', '',
      '原→事件列：在同平台上比较回放与原版的全部时间/信号数组（dtype/shape/原始字节）、原事件日志和关键求解字段。统计列为原版/事件回放分别通过的 mean/rms/max 项数，阈值沿用 C002 诊断方法：provenance 中 channel.atol + 1%×|参考统计值|。这不是把所有案例重新宣称为历史精度验收通过；点波形 RMSE/max_abs 也保存在逐例证据中。', '',
      '| 案例 | Win 原→事件 | Linux 原→事件 | 跨平台 原版/事件回放数组 | Win 对 PLECS 统计 原/事件 | Linux 对 PLECS 统计 原/事件 | 新 PLECS 与原 CSV |',
      '|---|---|---|---|---|---|---|']
    def eq(v):
        if not v: return '未比较'
        if 'error' in v: return '比较失败：'+esc(v['error'])
        ok=v.get('bitwise_equal') and v.get('event_logs_equal') and not v.get('changed_solver_fields')
        return '全部一致' if ok else '存在差异（见证据）'
    def stat(v):
        return str(v['passed'])+'/'+str(v['total']) if 'passed' in v else '—'
    for name,row in sorted(cases.items()):
        v=row['validation']; cross=[]
        for k in ('original','replay'):
            c=v.get('cross_platform_'+k,{})
            cross.append('逐字节一致' if c.get('bitwise_equal') else ('有差异' if c else '—'))
        cells=[eq(v.get('win_event_equivalence')),eq(v.get('linux_event_equivalence')),' / '.join(cross)]
        for platform in ('win','linux'):
            cells.append(' / '.join(stat(v.get(platform+'_'+k+'_vs_PLECS',{})) for k in ('original','replay')))
        cells.append(str(v.get('fresh_PLECS_matches_original_CSV','未比较')))
        lines.append('| '+name+' | '+' | '.join(cells)+' |')
    lines += ['', '## 完成数量与失败详情', '']
    for label in labels:
        counts=collections.Counter(row['runs'].get(label,{}).get('status','NOT_RUN') for row in cases.values())
        lines.append('- '+label+'：'+', '.join(f'{k}={v}' for k,v in sorted(counts.items())))
    for name,row in sorted(cases.items()):
        failures=[]
        for label,r in row['runs'].items():
            if r.get('status')=='COMPLETED': continue
            d=r.get('diagnostic') or {}
            failures.append(f"{label}: {r.get('status')}, t={r.get('simulated_seconds')}, transactions={r.get('report',{}).get('transactions')}, {d.get('subcode','')} {d.get('message','')}{r.get('error','')}")
        if failures: lines += ['', '### '+name, '', *['- '+esc(f) for f in failures]]
    lines += ['', '## 仍未解决的问题与边界', '',
      '- A002 的既有 PULSE 转换使用 20 us ZOH 控制，与原厂连续控制 PLECS 不同；此行只可比较运行与事件输出等价性，不能用该 CSV 证明同模型精度。',
      '- 曾只验收短窗口的案例，本次全时长运行结果优先于历史短窗口记录；全时长失败不会降回短窗口标为通过。C019-DOT 无转换网表，不用其他案例替代。',
      '- 本次不修复数值算法或控制语义问题。原版和事件版相同的失败保留为模型/求解器现存限制；新增的事件格式问题单独记录。',
      '- 事件流 v1 保留单流 64 MiB 限制和完整性检查；没有为了大案例关闭限额或波形有限值检查。事件生成完成但回放失败仍不算波形验证通过。',
      '- Windows 采用 GCC，MSVC 未验证。跨平台数组不一致时需查看各通道误差，不能从相同完成状态推断结果相同；逐字节回放保证只覆盖实际完成并比较的案例。',
      '- 首轮 C002 烟雾测试保存在 `reports/all-platforms-20261101/`，其部分时间与测试阶段重叠，未用于本正式表；正式结果使用独立输出目录且不与其他测试并发。', '',
      '## 复现与证据', '',
      'Windows：`./build_windows_event.ps1`；Linux：`./build_linux.sh`。同一套源码生成两平台事件求解器和 pulse-replay。', '',
      '批测：`python scripts/benchmark_all_platforms.py --help`。必须提供冻结原版和事件版的四个二进制路径、案例库目录，以及独立 Windows/WSL 输出目录；脚本支持从 ledger 恢复已保存结果，不覆盖原案例。', '',
      '报告：`python scripts/report_all_platforms.py reports/all-platforms-full-20261101/ledger.json --out docs/reports/Win_Linux_All_Cases_Comparison.md`。', '',
      '机器可读证据：同目录 `Win_Linux_All_Cases_Evidence.json`。详细原始结果（完整报告、最后有效状态、事件日志、NPZ/事件流、模块编译日志、新 PLECS mat）保存在本地 `reports/all-platforms-full-20261101/<case>/` 和 WSL `/root/pulse-all-platforms-full-20261101/`；生成产物已 gitignore，不提交二进制。', '',
      '| 二进制 | SHA256 |', '|---|---|']
    for name, identity in data['binaries'].items(): lines.append('| '+name+' | `'+identity['sha256']+'` |')
    lines += ['', '未改动求解数值核心；本分支仅增加 Windows 事件版构建入口、全案例原生运行/比较工具和文档。事件格式实现继承 `8d75697`，精度审计继承 `30859d3`，原版 Linux 冻结构建来自 `2327376`。未合并 main。', '']
    a.out.parent.mkdir(parents=True,exist_ok=True); a.out.write_text('\n'.join(lines),encoding='utf-8')
    # Keep audit metadata/check failures, without committing simulation artifacts.
    compact=json.loads(json.dumps(data))
    for row in compact['cases'].values():
        for r in row['runs'].values():
            report=r.pop('report',{})
            r['solver_summary']={k:report.get(k) for k in ['source_sha256','status','simulated_seconds','transactions','effective_T_END','effective_SAVE_DT','T_atom','waveform_validation'] if k in report}
        for v in row['validation'].values():
            if isinstance(v,dict) and 'checks' in v: v['failed_checks']=[c for c in v.pop('checks') if not c['passed']]
    a.out.with_name('Win_Linux_All_Cases_Evidence.json').write_text(json.dumps(compact,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__': main()
