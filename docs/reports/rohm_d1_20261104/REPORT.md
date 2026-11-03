# Stage D1：ROHM 全库与 PLECS 对比

2026-11-04；每例运行一次，按案例串行执行。

求解器代码 `05fb315f8126561a74b45fb06bf2654b0d138800`；案例库 `13660577132de41c37c1c47576c02941d21c532a`。
同一 Linux Release ELF，SHA256 `1c8a0a4624fcef6be7ad9d6e7b83379910196a9310dc1ded0e45bd21d30e9cc0`。

19 例尝试运行 D1，10 例完整交付，9 例运行/输出/环境失败；另 1 例未转换。完整交付的 10 例中，8 例用时少于 PLECS，2 例多于 PLECS。

完整网格逐点和统计指标均在比较阈值内：B-004-D。A010 统计 21/21，但有 36 个逐点超差；B012 统计 39/63，约 366 万个通道采样值超差。

## 范围与口径

共 20 例，19 例有 PULSE 输入；包含历史只验证过短窗口及尚未验收的转换候选。C019-DOT 没有 PULSE 网表。每例使用案例库原输入与 MCU 源码，通过 CLI 指定原厂完整终点；部分网表原声明是短窗口，本次延长至对应 PLECS 完整时长，未改动源文件、SAVE_DT、控制器或物理参数。

PLECS 4.8.2 在 Windows 本机运行；D1 在 WSL2 Ubuntu 原生 Linux 运行。计时从发起仿真至 COMPLETED 通知；PLECS 为 simulate RPC 完成并返回 MAT，D1 包含 CLI 启动、解析、计算、事件归档及写文件。另存 D1 进程退出时间。模型加载、控制模块编译、完整性核对及 WSL 启动不计入。此口径没有测量鼠标/UI 延迟。

机器：AMD Ryzen 5 6600H，6 核/12 逻辑 CPU；Ubuntu 24.04.5，GCC 13.3，CMake 3.28.3。Release 使用 `-O3 -DNDEBUG -ffp-contract=off -fno-fast-math`，C++20。没有加载 CPU profiler、阶段计时或分配计数器。完整机器及构建信息见 EVIDENCE.json。

每例上限为本次 PLECS 用时的 10 倍；现有运行时预算保留最后提交状态，看门狗额外 30 秒仅供失败诊断及归档清理，超限结果不能记为完成。预算在事务边界检查；未及时返回时，实际进程可能持续至 10 倍加 30 秒的硬终止点。C012-D 本次被外部终止，未取得最后有效状态；具体停留阶段尚未定位。这不是所有进程都在精确 10 倍时刻退出的保证。失败或部分输出不参与完成用时比。

空间为 D1 事件文件 PEVT 和全部生成输出，与 PLECS 原始 1 µs 网格 MAT 导出对比；SUMMARY.csv 另列原库 CSV 字节数。格式及通道数量不同，文件比例不等于同编码压缩率。所有 PULSE 原输出通道均保留。波形重建仅供精度核对，其耗时和文件体积均不计入表格。

精度使用完整 1 µs 参考网格，逐通道 `atol + 1% × |PLECS|`；`atol` 沿用 provenance.json，不调整时轴、不删除开关边沿。分别核对 fresh PLECS 和原库固定 CSV。均值/RMS/最大值统计通过数与逐点超差同时列出；统计全部通过不代表每点通过。重建在原始参考网格取样；仅覆盖网格点，不构成连续时间误差认证。

## 完整仿真结果

状态数量：`{"COMPLETED": 10, "OUTPUT_FAILED": 1, "STOPPED_UNRESOLVED": 3, "TIME_LIMIT_EXCEEDED": 4, "ENVIRONMENT_FAILURE": 1, "NOT_CONVERTED": 1}`。

| Case | 终点 s | D1 状态 | PLECS s | D1 s | D1/PLECS | PEVT MiB | PLECS MAT MiB | 文件比 |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| A-002-D | 0.500 | COMPLETED | 44.607 | 11.478 | 0.257 | 56.632 | 30.518 | 1.856 |
| A-010-DOT | 0.500 | COMPLETED | 14.070 | 42.533 | 3.023 | 155.293 | 30.518 | 5.089 |
| A-011-D | 0.500 | COMPLETED | 44.208 | 26.123 | 0.591 | 140.384 | 30.518 | 4.600 |
| A-021-D | 0.500 | OUTPUT_FAILED | 306.984 | — | — | — | 72.480 | — |
| A-021-DOT | 0.500 | STOPPED_UNRESOLVED | 31.571 | — | — | 224.878 | 57.221 | — |
| B-004-D | 0.500 | COMPLETED | 10.470 | 6.722 | 0.642 | 40.345 | 41.962 | 0.961 |
| B-004-DOT | 0.500 | COMPLETED | 10.196 | 7.166 | 0.703 | 40.442 | 41.962 | 0.964 |
| B-009-D | 0.500 | TIME_LIMIT_EXCEEDED | 14.256 | — | — | 15.890 | 49.591 | — |
| B-011-DOT | 0.500 | STOPPED_UNRESOLVED | 22.563 | — | — | — | 68.665 | — |
| B-012-DOT | 0.500 | COMPLETED | 33.422 | 190.889 | 5.712 | 118.809 | 83.924 | 1.416 |
| C-002-D | 0.300 | COMPLETED | 9.919 | 2.659 | 0.268 | 16.671 | 18.311 | 0.910 |
| C-006-D | 0.300 | COMPLETED | 11.355 | 2.504 | 0.220 | 16.073 | 18.311 | 0.878 |
| C-010-D | 0.300 | COMPLETED | 10.681 | 5.223 | 0.489 | 31.887 | 18.311 | 1.741 |
| C-011-D | 0.400 | COMPLETED | 41.360 | 25.207 | 0.609 | 195.879 | 30.518 | 6.418 |
| C-012-D | 0.300 | TIME_LIMIT_EXCEEDED | 42.113 | — | — | — | 22.888 | — |
| C-012-DOT | 0.300 | ENVIRONMENT_FAILURE | 112.359 | — | — | — | 22.888 | — |
| C-014-D | 0.200 | TIME_LIMIT_EXCEEDED | 48.506 | — | — | — | 15.259 | — |
| C-014-DOT | 0.200 | TIME_LIMIT_EXCEEDED | 48.200 | — | — | — | 15.259 | — |
| C-019-D | 0.200 | STOPPED_UNRESOLVED | 117.430 | — | — | 0.100 | 22.889 | — |
| C-019-DOT | 0.150 | NOT_CONVERTED | 88.342 | — | — | — | 11.444 | — |

失败行的 PEVT 大小仅为已提交前缀，不能与完整 PLECS 输出作体积收益比较。

## 精度

| Case | fresh 统计通过 | 逐点超差（通道×采样点） | 固定 CSV 统计通过 | 缺失参考通道 |
|---|---:|---:|---:|---|
| A-002-D | 21/21 | 24892 | 21/21 | — |
| A-010-DOT | 21/21 | 36 | 21/21 | — |
| A-011-D | 21/21 | 33596 | 21/21 | — |
| A-021-D | 未比较（原参考 54 项） | — | 未比较 | MOS_JUNCTION_TEMP_C;MOS_HEATSINK_TEMP_C;DIODE_JUNCTION_TEMP_C;DIODE_HEATSINK_TEMP_C |
| A-021-DOT | 未比较 | — | 未比较 | — |
| B-004-D | 30/30 | 0 | 30/30 | — |
| B-004-DOT | 29/30 | 4008 | 29/30 | — |
| B-009-D | 未比较 | — | 未比较 | — |
| B-011-DOT | 未比较 | — | 未比较 | — |
| B-012-DOT | 39/63 | 3659336 | 39/63 | — |
| C-002-D | 20/21 | 17562 | 20/21 | — |
| C-006-D | 17/21 | 10296 | 17/21 | — |
| C-010-D | 13/21 | 26580 | 13/21 | — |
| C-011-D | 17/27 | 95055 | 17/27 | — |
| C-012-D | 未比较 | — | 未比较 | — |
| C-012-DOT | 未比较 | — | 未比较 | — |
| C-014-D | 未比较 | — | 未比较 | — |
| C-014-DOT | 未比较 | — | 未比较 | — |
| C-019-D | 未比较 | — | 未比较 | — |
| C-019-DOT | 未比较 | — | 未比较 | — |

各通道 RMSE、MAE、最大绝对误差、最坏时刻及逐点通过率见 CHANNEL_ACCURACY.csv；统计实际值、参考值、容差及通过判据见 STATISTIC_CHECKS.csv。

A002 的 PULSE 离散控制与原 PLECS 连续控制不同，结果差异不能直接归因于求解器数值误差。A021-D 的热通道若缺失，按未覆盖记录，不能判整例精度通过。

## 停止、失败与限制

- **rohm-a021-d-vienna-pfc**：OUTPUT_FAILED，最后有效时刻 `0.5`，返回用时 178.183 s；诊断 `{"subcode": "OUTPUT_ERROR", "message": "event stream exceeds 512 MiB"}`。
- **rohm-a021-dot-vienna-pfc**：STOPPED_UNRESOLVED，最后有效时刻 `0.152583`，返回用时 58.975 s；诊断 `{"subcode": "ALL_EVENT_ALGORITHMS_FAILED", "message": "event_closure: CANDIDATE_LINEAR_RESIDUAL; compile_or_propagate: UNPREDICTED_GUARD_JUMP"}`。
- **rohm-b009-d-motor-driver**：TIME_LIMIT_EXCEEDED，最后有效时刻 `0.04009260406202532`，返回用时 144.232 s；诊断 `{"subcode": "WALL_BUDGET", "message": "caller wall budget reached; committed prefix preserved"}`。
- **rohm-b011-dot-npc-t-inverter**：STOPPED_UNRESOLVED，最后有效时刻 `0.0`，返回用时 0.049 s；诊断 `{"subcode": "INITIAL_MODE_CYCLE", "message": "initial mode classification cycles; provide a physically regular initial model"}`。
- **rohm-c012-d-llc-half-bridge**：TIME_LIMIT_EXCEEDED，最后有效时刻 `None`，返回用时 451.693 s；诊断 `{"watchdog": "External SIGKILL after budget + 30s; no final state available", "diagnostic": {}}`。
- **rohm-c012-dot-llc-half-bridge**：ENVIRONMENT_FAILURE，最后有效时刻 `None`，返回用时 — s；诊断 `"Memory/swap pressure observed, WSL process query failed with WSAETIMEDOUT; Ubuntu-24.04 terminated to recover. No final CPU/time/state/archive evidence. OOM kill not confirmed."`。
- **rohm-c014-d-llc-full-bridge**：TIME_LIMIT_EXCEEDED，最后有效时刻 `0.03687823945424704`，返回用时 499.264 s；诊断 `{"subcode": "WALL_BUDGET", "message": "caller wall budget reached; committed prefix preserved"}`。
  退出/归档诊断：`{"code": 11, "message": "event stream exceeds 512 MiB", "source": {"column": 1, "file": "", "line": 0, "path": ""}, "subcode": "OUTPUT_ERROR", "top_level_error": "OUTPUT_ERROR", "unresolved": false}`。
- **rohm-c014-dot-llc-full-bridge**：TIME_LIMIT_EXCEEDED，最后有效时刻 `0.03378417620090184`，返回用时 495.232 s；诊断 `{"subcode": "WALL_BUDGET", "message": "caller wall budget reached; committed prefix preserved"}`。
  退出/归档诊断：`{"code": 11, "message": "event stream exceeds 512 MiB", "source": {"column": 1, "file": "", "line": 0, "path": ""}, "subcode": "OUTPUT_ERROR", "top_level_error": "OUTPUT_ERROR", "unresolved": false}`。
- **rohm-c019-d-phase-shift-full-bridge**：STOPPED_UNRESOLVED，最后有效时刻 `1.000000101694618e-07`，返回用时 0.033 s；诊断 `{"subcode": "ALL_EVENT_ALGORITHMS_FAILED", "message": "compile_or_propagate: PHYSICAL_CONSTRAINT_VIOLATION"}`。
- **rohm-c019-dot-phase-shift-full-bridge**：NOT_CONVERTED，最后有效时刻 `None`，返回用时 — s；诊断 `"No PULSE netlist in original case library"`。

本轮未修改求解器、数值容差、原方程检查或模型。已运行完成但精度不一致的案例保留为差异结果，不将其标为精度 PASS。这些是参考网格上的输出差异；本轮没有将所有差异归因为 D1 数值回归，也没有通过时间对齐或排除边沿更改比较结果。每例仅一次用时测量，没有统计置信区间；Windows 与 WSL 文件系统及导出格式不同。

计算报告可在事件归档前写成。A021-D 的原始 report 虽写 COMPLETED，实际因 PEVT 512 MiB 上限返回非零且没有完成通知；汇总按 OUTPUT_FAILED，保留原始 native-result.json 并在 EVIDENCE 中注明测量状态纠正。测试工具现已要求成功退出且收到完成通知，求解器未改动。

C012-DOT 在 07:02:24 的快照显示 WSL 总内存 7534 MiB、可用 25 MiB，2 GiB 交换空间已用 1566 MiB；随后 WSL 返回 WSAETIMEDOUT。为恢复后续测试终止了该发行版。原 worker 的 RUNNING 快照与非零退出保留，汇总为 ENVIRONMENT_FAILURE。没有最终墙钟/CPU/峰值 RSS 或最后有效仿真时刻；不能确认 Linux OOM killer 是否介入。资源快照在 EVIDENCE 的 machine-c012-dot-memory-pressure.txt 字段。

## 证据与复现

`EVIDENCE.json` 包含原输入/参考哈希、二进制身份、全部原生报告字段、资源数据、命令及原始证据路径。`FAILURES.json` 保留失败诊断；`NATIVE_LOGS.json` 保存原始 GNU time、stderr 和控制模块编译日志。大体积 PEVT/MAT/波形不提交。

- Windows 原始证据：`D:\codex\using plecs\pulse-linux-port\reports\rohm-d1-20261104\batch`
- Linux 原始证据：`/root/rohm-d1-20261104/<case>/`（stdout/stderr、GNU time、原模块与事件归档）。
- 执行工具：`scripts/validate_rohm_d1.py`、`scripts/rohm_d1_native.py`；汇总工具：`scripts/report_rohm_d1.py`。

```powershell
python scripts/validate_rohm_d1.py --case-set "D:\codex\using plecs\PULSE-case-set" --out reports/rohm-d1-20261104/batch
python scripts/report_rohm_d1.py --case-set "D:\codex\using plecs\PULSE-case-set" --batch reports/rohm-d1-20261104/batch --out docs/reports/rohm_d1_20261104 --collect-native
```

执行需要已有 PLECS RPC 服务、numpy/scipy、WSL 原生 D1 与 replay 程序。新测量应指定新的输出目录及 native-out；中断续跑保留 ledger。

## 原生测试与完整性

计时测试结束后执行 Linux Release compatibility/CTest：36 项，通过 36、失败 0、跳过 0。原始输出见 CTEST.log、COMPATIBILITY.json。

结束后按 provenance 再次核对 269 个原始文件哈希，全部一致。10 例完整交付的原 .SAVE、求解报告和重建导出的通道集合均一致，未减少模拟、数字或控制通道。EVIDENCE 中 saved_channel_audit 保留各层通道列表，core_diff_vs_D1 为空。
