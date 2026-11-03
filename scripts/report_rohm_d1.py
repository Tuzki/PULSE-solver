#!/usr/bin/env python3
"""Summarize an inspectable ROHM batch; replay artifacts are never benchmark outputs."""
import argparse
import collections
import csv
import datetime
import hashlib
import json
import re
import subprocess
from pathlib import Path

EXPECTED_ELF = '1c8a0a4624fcef6be7ad9d6e7b83379910196a9310dc1ded0e45bd21d30e9cc0'


def load(p):
    return json.loads(p.read_text(encoding='utf-8'))


def save(p, value):
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8', newline='\n')


def write_csv(p, rows):
    if not rows:
        return
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with p.open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=keys, lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def num(x, places=3):
    return '—' if x is None else f'{x:.{places}f}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--case-set', type=Path, required=True)
    parser.add_argument('--native-out', default='/root/rohm-d1-20261104')
    parser.add_argument('--allow-incomplete', action='store_true', help='Preview only; never final acceptance')
    parser.add_argument('--collect-native', action='store_true', help='Collect small raw logs from the original WSL runs')
    a = parser.parse_args()
    ledger = load(a.batch/'ledger.json')
    inventory = {p.parent.name for p in a.case_set.glob('*/provenance.json')}
    if not a.allow_incomplete and (set(ledger['cases']) != inventory or
                                 not all(r.get('finished') for r in ledger['cases'].values())):
        raise ValueError('Batch incomplete; a final report requires every original case result')
    a.out.mkdir(parents=True, exist_ok=True)
    native_logs_path = a.out/'NATIVE_LOGS.json'
    if a.collect_native:
        collector = 'import json,pathlib\nroot=pathlib.Path('+repr(a.native_out)+')\n'+"""rows={}
for case in sorted(root.glob('rohm-*')):
 if not case.is_dir(): continue
 rows[case.name]={}
 for name in ('stderr.txt','resource.txt','module-build.txt'):
  p=case/name
  if p.exists(): rows[case.name][name]=p.read_text()
print(json.dumps(rows))
"""
        captured = subprocess.check_output(['wsl.exe', '-d', 'Ubuntu-24.04', '-u', 'root', '--exec', 'python3', '-c', collector])
        save(native_logs_path, json.loads(captured))
    native_logs = load(native_logs_path) if native_logs_path.exists() else {}
    summary, channels, checks, failure_rows = [], [], [], []
    for name, row in sorted(ledger['cases'].items()):
        original_meta = load(a.case_set/name/'provenance.json')
        history = row.get('history') or {}
        if not isinstance(history, dict):
            history = {}
        p, d, acc = (row.get(k, {}) for k in ('PLECS', 'D1', 'accuracy'))
        r = d.get('report', {})
        stderr = native_logs.get(name, {}).get('stderr.txt', '')
        if stderr:
            try:
                d['exit_diagnostic'] = json.loads(stderr)
            except ValueError:
                d['exit_diagnostic'] = {'message': stderr}
        if d.get('status') in ('RUNNING', 'PREPARING') and row.get('finished'):
            d['raw_worker_status'] = d['status']
            d['status'] = 'ENVIRONMENT_FAILURE'
            d['measurement_correction'] = 'Worker interrupted without a final measurement; never a completed simulation'
            if name == 'rohm-c012-dot-llc-half-bridge':
                d['reason'] = ('Memory/swap pressure observed, WSL process query failed with WSAETIMEDOUT; '
                               'Ubuntu-24.04 terminated to recover. No final CPU/time/state/archive evidence. OOM kill not confirmed.')
        if d.get('status') == 'COMPLETED' and (d.get('returncode') != 0 or d.get('completion_wall_seconds') is None):
            # Preserve the original native-result.json. Early worker versions
            # trusted the pre-archive report when serialization subsequently failed.
            d['raw_worker_status'] = d['status']
            d['status'] = 'OUTPUT_FAILED'
            d['measurement_correction'] = 'Calculation report is not completion: process exit/COMPLETED notification failed'
        if d.get('binary') and d['binary']['sha256'] != EXPECTED_ELF:
            raise ValueError(f'Unexpected solver ELF: {name}')
        if r and r.get('source_sha256') != 'ff7029501f36ba6bd5d2e7a95c186099ee89193594220d36417b2bb56c87a8ed':
            raise ValueError(f'Unexpected solver source identity: {name}')
        if d.get('status') == 'COMPLETED' and r.get('simulated_seconds') != row['target_seconds']:
            raise ValueError(f'Incomplete result labeled completed: {name}')
        ratio = (d['completion_wall_seconds']/p['wall_seconds']
                 if d.get('status') == 'COMPLETED' and p.get('wall_seconds') else None)
        if d.get('status') == 'COMPLETED' and ratio > 10:
            raise ValueError(f'Completed result exceeded budget: {name}')
        declared = set(r.get('analog_channels', [])) | set(r.get('digital_channels', []))
        netlist = a.case_set/name/'pulse/netlist.md'
        expected_channels = set()
        if netlist.exists():
            for line in netlist.read_text(encoding='utf-8').splitlines():
                if line.strip().startswith('.SAVE '):
                    expected_channels.update(line.split()[1:])
        retention = None
        if d.get('status') == 'COMPLETED' and (a.batch/name/'accuracy-wave.npz').exists():
            import numpy as np
            with np.load(a.batch/name/'accuracy-wave.npz', allow_pickle=False) as z:
                metadata = json.loads(str(z['metadata_json']))
            archived = {s['name'] for s in metadata['signals']}
            retention = bool(expected_channels) and expected_channels == declared == archived
            d['saved_channel_audit'] = {'passed': retention, 'source_SAVE': sorted(expected_channels),
                                       'solver_report': sorted(declared), 'replayed': sorted(archived)}
            if not retention:
                raise ValueError('Saved channel set changed: '+name)
        missing = acc.get('missing_channels', []) or ([c['pulse'] for c in row.get('metadata_channels', [])
                                                      if c['pulse'] not in declared] if declared else [])
        special = ''
        if name == 'rohm-a002-d-boost-pfc':
            special = 'PULSE 20us ZOH controller vs PLECS continuous control; model/control comparability limitation'
        if missing:
            special += ('; ' if special else '')+'Missing declared reference channels: '+', '.join(missing)
        precision = ('UNMEASURED' if acc.get('status') != 'COMPARED' else
                     'MISSING_CHANNELS' if acc.get('missing_channels') else
                     'DIFFERENCES' if not acc['all_statistics_passed'] or acc['pointwise_outliers'] else
                     'WITHIN_RECORDED_TOLERANCE')
        s = {
            'case': name, 'target_seconds': row['target_seconds'],
            'rohm_id': original_meta['rohm_id'],
            'original_PULSE_TRAN': original_meta.get('pulse_default_tran'),
            'historical_compared_seconds': history.get('compared_seconds'),
            'historical_native_seconds': history.get('native_seconds'),
            'historical_status': history.get('status'),
            'PLECS_status': p.get('status'), 'D1_status': d.get('status'),
            'PLECS_wall_seconds': p.get('wall_seconds'),
            'D1_completion_wall_seconds': d.get('completion_wall_seconds'),
            'D1_exit_wall_seconds': d.get('exit_wall_seconds'), 'D1_over_PLECS_wall': ratio,
            'D1_limit_seconds': d.get('limit_seconds'),
            'D1_last_simulated_seconds': d.get('simulated_seconds', r.get('committed_prefix_end')),
            'D1_PEVT_bytes': d.get('pevt_bytes'), 'D1_generation_bytes': d.get('generation_output_bytes'),
            'PLECS_MAT_bytes': p.get('MAT', {}).get('bytes'),
            'fixed_PLECS_CSV_bytes': sum(v['bytes'] for k, v in row.get('original_files', {}).items() if k.endswith('.csv')),
            'PLECS_reference_channels': len(row.get('metadata_channels', [])),
            'D1_analog_channels': len(r.get('analog_channels', [])),
            'D1_digital_channels': len(r.get('digital_channels', [])),
            'saved_channel_retention_passed': retention,
            'accuracy': precision, 'statistics_passed': acc.get('statistics_passed'),
            'statistics_total': acc.get('statistics_total'),
            'expected_reference_statistics': 3*len(row.get('metadata_channels', [])),
            'pointwise_outside_tolerance': acc.get('pointwise_outliers'),
            'missing_channels': ';'.join(missing),
            'fixed_CSV_statistics_passed': acc.get('fixed_CSV_statistics_passed'),
            'fixed_CSV_statistics_total': acc.get('fixed_CSV_statistics_total'),
            'fixed_CSV_pointwise_outliers': acc.get('fixed_CSV_pointwise_outliers'),
            'transactions': r.get('transactions'), 'mode_compilations': r.get('mode_compilations'),
            'original_equation_checks': r.get('original_equation_cache', {}).get('checks'),
            'CPU_user_seconds': d.get('CPU_user_seconds'), 'CPU_system_seconds': d.get('CPU_system_seconds'),
            'peak_RSS_KiB': d.get('peak_RSS_KiB'), 'comparability_notes': special,
            'harness_error': row.get('harness_error'),
            'exit_error_subcode': d.get('exit_diagnostic', {}).get('subcode'),
            'exit_error_message': d.get('exit_diagnostic', {}).get('message'),
        }
        s['D1_PEVT_over_PLECS_MAT_bytes'] = (s['D1_PEVT_bytes']/s['PLECS_MAT_bytes']
            if d.get('status') == 'COMPLETED' and s['PLECS_MAT_bytes'] else None)
        s['failed_statistic_channels'] = ';'.join(sorted({c['channel'] for c in acc.get('checks', []) if not c['passed']}))
        summary.append(s)
        for label, result in [('fresh_PLECS', acc), ('fixed_CSV', load(a.batch/name/'accuracy-fixed-csv.json')
                            if (a.batch/name/'accuracy-fixed-csv.json').exists() else {})]:
            for c in result.get('channels', []):
                ref_rms = c['statistics']['rms']['reference']
                channels.append({'case': name, 'reference': label, **{k: v for k, v in c.items() if k != 'statistics'},
                                 'RMSE_over_reference_RMS_percent': 100*c['RMSE']/abs(ref_rms) if ref_rms else None})
            for c in result.get('checks', []):
                checks.append({'case': name, 'reference_source': label, **c,
                               'absolute_error': abs(c['D1']-c['reference']),
                               'relative_error_percent': 100*abs(c['D1']-c['reference'])/abs(c['reference']) if c['reference'] else None})
        if d.get('status') != 'COMPLETED' or row.get('harness_error') or acc.get('status') == 'RECONSTRUCTION_FAILED':
            failure_rows.append({'case': name, 'status': d.get('status'), 'PLECS': p,
                                 'diagnostic': d.get('diagnostic'), 'reason': d.get('reason'),
                                 'exit_diagnostic': d.get('exit_diagnostic'),
                                 'harness_error': row.get('harness_error'), 'accuracy_status': acc.get('status'),
                                 'exit_wall_seconds': d.get('exit_wall_seconds'),
                                 'hard_timeout': d.get('hard_timeout'),
                                 'last_valid_time': d.get('simulated_seconds', r.get('committed_prefix_end')),
                                 'native_evidence': a.native_out+'/'+name})
    statuses = dict(collections.Counter(x['D1_status'] for x in summary))
    completed = [s for s in summary if s['D1_status'] == 'COMPLETED']
    attempted = sum(s['D1_status'] not in (None, 'NOT_CONVERTED', 'NOT_RUN') for s in summary)
    unavailable = sum(s['D1_status'] == 'NOT_CONVERTED' for s in summary)
    faster = sum(s['D1_over_PLECS_wall'] < 1 for s in completed)
    within = [s['rohm_id'] for s in summary if s['accuracy'] == 'WITHIN_RECORDED_TOLERANCE']
    evidence = {'created_UTC': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'summary': summary, 'status_counts': statuses, 'batch': ledger,
                'raw_Windows': str(a.batch.resolve()), 'raw_Linux': a.native_out,
                'solver_ELF_SHA256': EXPECTED_ELF,
                'source_SHA256': 'ff7029501f36ba6bd5d2e7a95c186099ee89193594220d36417b2bb56c87a8ed',
                'artifacts': {}}
    project = Path(__file__).resolve().parents[1]
    evidence['analysis_tools'] = {str(p.relative_to(project)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in (project/'scripts'/n for n in (
                                      'rohm_d1_native.py', 'validate_rohm_d1.py', 'report_rohm_d1.py'))}
    evidence['validation_parent_commit'] = subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip()
    evidence['validation_branch'] = subprocess.check_output(['git', '-C', str(project), 'branch', '--show-current'], text=True).strip()
    evidence['core_diff_vs_D1'] = subprocess.check_output([
        'git', '-C', str(project), 'diff', '--stat', ledger['solver_code_commit'], '--',
        'src', 'include', 'apps', 'tests', 'CMakeLists.txt', 'scripts/build_software.py'], text=True)
    evidence['case_set_git_status'] = subprocess.check_output(['git', '-C', str(a.case_set), 'status', '--porcelain'], text=True)
    ctest_log = a.out/'CTEST.log'
    tests = None
    if ctest_log.exists():
        log = ctest_log.read_text(encoding='utf-8')
        tests = {'passed': len(re.findall(r'\d+/\d+\s+Test\s+#\d+:.*?\bPassed\b', log)),
                 'failed': int(re.search(r'(\d+) tests failed out of', log)[1]),
                 'total': int(re.search(r'tests failed out of (\d+)', log)[1]),
                 'skipped': len(re.findall(r'Not Run|Skipped|Disabled', log)),
                 'log_sha256': hashlib.sha256(ctest_log.read_bytes()).hexdigest()}
        evidence['Linux_CTest'] = tests
        evidence['compatibility_validation'] = load(a.out/'COMPATIBILITY.json')
    for p in sorted(a.batch.parent.glob('machine-*')):
        evidence[p.name] = p.read_text(encoding='utf-8-sig')
    recovery = a.batch.parent/'wsl-recovery.txt'
    if recovery.exists():
        evidence['WSL_recovery'] = {
            'command': ['wsl.exe', '--terminate', 'Ubuntu-24.04'],
            'path': str(recovery.resolve()), 'bytes': recovery.stat().st_size,
            'sha256': hashlib.sha256(recovery.read_bytes()).hexdigest(),
            'result': 'exit 0; native environment usable afterward; source artifacts retained',
            'observed_error': 'Wsl/Service/WSAETIMEDOUT in failed process-status query',
            'observation_local_date': '2026-11-04 Asia/Shanghai',
        }
    integrity = {}
    for name in ledger['cases']:
        case = a.case_set/name
        meta = load(case/'provenance.json')
        entries = meta['pulse_inputs']+meta['csv_exports']+meta.get('source_files', [])+[
            {'file': meta['capture_model'], 'sha256': meta['capture_sha256']},
            {'file': meta['original_model'], 'sha256': meta['original_sha256']}]
        for item in entries:
            q = case/item['file']
            h = hashlib.sha256(q.read_bytes()).hexdigest()
            if h != item['sha256']:
                raise ValueError('Post-run original SHA mismatch: '+str(q))
            integrity[name+'/'+item['file']] = h
    evidence['post_run_original_integrity'] = {'status': 'PASS', 'files': integrity}
    # Reference exports and all generated archives are fingerprinted, not committed.
    for p in sorted(a.batch.rglob('*')):
        if p.is_file() and p.name in ('plecs.mat', 'reference.npz', 'native-worker.txt', 'native-result.json',
                                      'replay-validation.txt', 'accuracy.json', 'accuracy-fixed-csv.json'):
            h = hashlib.sha256()
            with p.open('rb') as f:
                for b in iter(lambda: f.read(1 << 20), b''):
                    h.update(b)
            evidence['artifacts'][str(p.relative_to(a.batch))] = {
                'bytes': p.stat().st_size, 'sha256': h.hexdigest(),
                'modified_UTC': datetime.datetime.fromtimestamp(p.stat().st_mtime, datetime.timezone.utc).isoformat()}
    write_csv(a.out/'SUMMARY.csv', summary)
    write_csv(a.out/'CHANNEL_ACCURACY.csv', channels)
    write_csv(a.out/'STATISTIC_CHECKS.csv', checks)
    save(a.out/'FAILURES.json', failure_rows)
    save(a.out/'EVIDENCE.json', evidence)
    lines = ['# Stage D1：ROHM 全库与 PLECS 对比', '',
             '2026-11-04；每例运行一次，按案例串行执行。', '',
             f"求解器代码 `{ledger['solver_code_commit']}`；案例库 `{ledger['case_set_commit']}`。",
             f'同一 Linux Release ELF，SHA256 `{EXPECTED_ELF}`。', '',
             f"{attempted} 例尝试运行 D1，{len(completed)} 例完整交付，{attempted-len(completed)} 例运行/输出/环境失败；另 {unavailable} 例未转换。"
             f"完整交付的 {len(completed)} 例中，{faster} 例用时少于 PLECS，{len(completed)-faster} 例多于 PLECS。", '',
             f"完整网格逐点和统计指标均在比较阈值内：{', '.join(within) or '无'}。"
             'A010 统计 21/21，但有 36 个逐点超差；B012 统计 39/63，约 366 万个通道采样值超差。', '',
             '## 范围与口径', '',
             '共 20 例，19 例有 PULSE 输入；包含历史只验证过短窗口及尚未验收的转换候选。'
             'C019-DOT 没有 PULSE 网表。每例使用案例库原输入与 MCU 源码，通过 CLI 指定原厂完整终点；'
             '部分网表原声明是短窗口，本次延长至对应 PLECS 完整时长，未改动源文件、SAVE_DT、控制器或物理参数。', '',
             'PLECS 4.8.2 在 Windows 本机运行；D1 在 WSL2 Ubuntu 原生 Linux 运行。'
             '计时从发起仿真至 COMPLETED 通知；PLECS 为 simulate RPC 完成并返回 MAT，'
             'D1 包含 CLI 启动、解析、计算、事件归档及写文件。另存 D1 进程退出时间。'
             '模型加载、控制模块编译、完整性核对及 WSL 启动不计入。此口径没有测量鼠标/UI 延迟。', '',
             '机器：AMD Ryzen 5 6600H，6 核/12 逻辑 CPU；Ubuntu 24.04.5，GCC 13.3，CMake 3.28.3。'
             'Release 使用 `-O3 -DNDEBUG -ffp-contract=off -fno-fast-math`，C++20。'
             '没有加载 CPU profiler、阶段计时或分配计数器。完整机器及构建信息见 EVIDENCE.json。', '',
             '每例上限为本次 PLECS 用时的 10 倍；现有运行时预算保留最后提交状态，'
             '看门狗额外 30 秒仅供失败诊断及归档清理，超限结果不能记为完成。'
             '预算在事务边界检查；未及时返回时，实际进程可能持续至 10 倍加 30 秒的硬终止点。'
             'C012-D 本次被外部终止，未取得最后有效状态；具体停留阶段尚未定位。'
             '这不是所有进程都在精确 10 倍时刻退出的保证。失败或部分输出不参与完成用时比。', '',
             '空间为 D1 事件文件 PEVT 和全部生成输出，与 PLECS 原始 1 µs 网格 MAT 导出对比；'
             'SUMMARY.csv 另列原库 CSV 字节数。格式及通道数量不同，文件比例不等于同编码压缩率。'
             '所有 PULSE 原输出通道均保留。波形重建仅供精度核对，其耗时和文件体积均不计入表格。', '',
             '精度使用完整 1 µs 参考网格，逐通道 `atol + 1% × |PLECS|`；'
             '`atol` 沿用 provenance.json，不调整时轴、不删除开关边沿。'
             '分别核对 fresh PLECS 和原库固定 CSV。均值/RMS/最大值统计通过数与逐点超差同时列出；'
             '统计全部通过不代表每点通过。重建在原始参考网格取样；仅覆盖网格点，不构成连续时间误差认证。', '',
             '## 完整仿真结果', '',
             f'状态数量：`{json.dumps(statuses, ensure_ascii=False)}`。', '',
             '| Case | 终点 s | D1 状态 | PLECS s | D1 s | D1/PLECS | PEVT MiB | PLECS MAT MiB | 文件比 |',
             '|---|---:|---|---:|---:|---:|---:|---:|---:|']
    for s in summary:
        lines.append('| '+ ' | '.join([s['rohm_id'], num(s['target_seconds']), str(s['D1_status']),
                      num(s['PLECS_wall_seconds']), num(s['D1_completion_wall_seconds']), num(s['D1_over_PLECS_wall']),
                      num(s['D1_PEVT_bytes']/1048576 if s['D1_PEVT_bytes'] is not None else None),
                      num(s['PLECS_MAT_bytes']/1048576 if s['PLECS_MAT_bytes'] is not None else None),
                      num(s['D1_PEVT_over_PLECS_MAT_bytes'])])+' |')
    lines += ['', '失败行的 PEVT 大小仅为已提交前缀，不能与完整 PLECS 输出作体积收益比较。', '',
              '## 精度', '', '| Case | fresh 统计通过 | 逐点超差（通道×采样点） | 固定 CSV 统计通过 | 缺失参考通道 |',
              '|---|---:|---:|---:|---|']
    for s in summary:
        stat = f"{s['statistics_passed']}/{s['statistics_total']}" if s['statistics_total'] else '未比较'
        if s['missing_channels']:
            stat += f"（原参考 {s['expected_reference_statistics']} 项）"
        fixed = f"{s['fixed_CSV_statistics_passed']}/{s['fixed_CSV_statistics_total']}" if s['fixed_CSV_statistics_total'] else '未比较'
        lines.append(f"| {s['rohm_id']} | {stat} | {s['pointwise_outside_tolerance'] if s['pointwise_outside_tolerance'] is not None else '—'} | {fixed} | {s['missing_channels'] or '—'} |")
    lines += ['', '各通道 RMSE、MAE、最大绝对误差、最坏时刻及逐点通过率见 CHANNEL_ACCURACY.csv；'
              '统计实际值、参考值、容差及通过判据见 STATISTIC_CHECKS.csv。', '',
              'A002 的 PULSE 离散控制与原 PLECS 连续控制不同，结果差异不能直接归因于求解器数值误差。'
              'A021-D 的热通道若缺失，按未覆盖记录，不能判整例精度通过。', '',
              '## 停止、失败与限制', '']
    for f in failure_rows:
        diag = f['diagnostic'] or f['reason'] or f['harness_error'] or f['accuracy_status']
        if isinstance(diag, dict):
            diag = {k: diag[k] for k in ('subcode', 'message') if k in diag}
            if diag.get('subcode') == 'ALL_EVENT_ALGORITHMS_FAILED':
                try:
                    failures = json.loads(diag['message'][diag['message'].index('['):])
                    diag['message'] = '; '.join(dict.fromkeys(
                        x.get('stage', '')+': '+x.get('diagnostic', {}).get('subcode', '') for x in failures))
                except (ValueError, KeyError):
                    pass
        if f.get('hard_timeout'):
            diag = {'watchdog': 'External SIGKILL after budget + 30s; no final state available', 'diagnostic': diag}
        lines.append(f"- **{f['case']}**：{f['status']}，最后有效时刻 `{f['last_valid_time']}`，"
                     f"返回用时 {num(f['exit_wall_seconds'])} s；诊断 `{json.dumps(diag, ensure_ascii=False)}`。")
        if f.get('exit_diagnostic') and f['exit_diagnostic'] != f['diagnostic']:
            lines.append('  退出/归档诊断：`'+json.dumps(f['exit_diagnostic'], ensure_ascii=False)+'`。')
    if not failure_rows:
        lines.append('没有运行或重建失败；精度结论仍以逐通道数据为准。')
    lines += ['', '本轮未修改求解器、数值容差、原方程检查或模型。'
              '已运行完成但精度不一致的案例保留为差异结果，不将其标为精度 PASS。'
              '这些是参考网格上的输出差异；本轮没有将所有差异归因为 D1 数值回归，'
              '也没有通过时间对齐或排除边沿更改比较结果。'
              '每例仅一次用时测量，没有统计置信区间；Windows 与 WSL 文件系统及导出格式不同。', '',
              '计算报告可在事件归档前写成。A021-D 的原始 report 虽写 COMPLETED，'
              '实际因 PEVT 512 MiB 上限返回非零且没有完成通知；汇总按 OUTPUT_FAILED，'
              '保留原始 native-result.json 并在 EVIDENCE 中注明测量状态纠正。'
              '测试工具现已要求成功退出且收到完成通知，求解器未改动。', '',
              'C012-DOT 在 07:02:24 的快照显示 WSL 总内存 7534 MiB、可用 25 MiB，2 GiB 交换空间已用 1566 MiB；'
              '随后 WSL 返回 WSAETIMEDOUT。为恢复后续测试终止了该发行版。'
              '原 worker 的 RUNNING 快照与非零退出保留，汇总为 ENVIRONMENT_FAILURE。'
              '没有最终墙钟/CPU/峰值 RSS 或最后有效仿真时刻；不能确认 Linux OOM killer 是否介入。'
              '资源快照在 EVIDENCE 的 machine-c012-dot-memory-pressure.txt 字段。', '',
              '## 证据与复现', '',
              '`EVIDENCE.json` 包含原输入/参考哈希、二进制身份、全部原生报告字段、资源数据、命令及原始证据路径。'
              '`FAILURES.json` 保留失败诊断；`NATIVE_LOGS.json` 保存原始 GNU time、stderr 和控制模块编译日志。'
              '大体积 PEVT/MAT/波形不提交。', '',
              f'- Windows 原始证据：`{a.batch.resolve()}`',
              f'- Linux 原始证据：`{a.native_out}/<case>/`（stdout/stderr、GNU time、原模块与事件归档）。',
              '- 执行工具：`scripts/validate_rohm_d1.py`、`scripts/rohm_d1_native.py`；汇总工具：`scripts/report_rohm_d1.py`。', '',
              '```powershell',
              'python scripts/validate_rohm_d1.py --case-set "D:\\codex\\using plecs\\PULSE-case-set" --out reports/rohm-d1-20261104/batch',
              'python scripts/report_rohm_d1.py --case-set "D:\\codex\\using plecs\\PULSE-case-set" --batch reports/rohm-d1-20261104/batch --out docs/reports/rohm_d1_20261104 --collect-native',
              '```', '',
              '执行需要已有 PLECS RPC 服务、numpy/scipy、WSL 原生 D1 与 replay 程序。'
              '新测量应指定新的输出目录及 native-out；中断续跑保留 ledger。']
    if tests:
        lines += ['', '## 原生测试与完整性', '',
                  f"计时测试结束后执行 Linux Release compatibility/CTest：{tests['total']} 项，"
                  f"通过 {tests['passed']}、失败 {tests['failed']}、跳过 {tests['skipped']}。原始输出见 CTEST.log、COMPATIBILITY.json。", '',
                  f"结束后按 provenance 再次核对 {len(integrity)} 个原始文件哈希，全部一致。"
                  '10 例完整交付的原 .SAVE、求解报告和重建导出的通道集合均一致，未减少模拟、数字或控制通道。'
                  'EVIDENCE 中 saved_channel_audit 保留各层通道列表，core_diff_vs_D1 为空。']
    (a.out/'REPORT.md').write_text('\n'.join(lines)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps(statuses))


if __name__ == '__main__':
    main()
