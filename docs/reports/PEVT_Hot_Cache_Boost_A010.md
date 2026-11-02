# PULSEES1 精确热缓存优化：Boost 与 A010

日期：2026-11-02。分支：`experiment/pevt-hot-cache`。基线：`c86e74c023a8a305d848f890b630647eceed45c4`。

## 源码改动

- `src/pevt.cpp`：增加容量为 4 的最近方程实例缓存。逐项比较所有归档相关矩阵、映射、守卫、布尔量、区域和数值策略；浮点数组用原始位比较。精确命中后复用方程实例 ID，未命中走原编码路径。
- `src/runtime.cpp`：每个密集采样点只判断一次 Flow/Mode 兼容性，空模拟通道时跳过该判断。这部分用于波形输出与重建，不计作事件生成加速。
- `.gitignore`：排除独立优化版 Windows 构建目录。
- `scripts/benchmark_pevt_vs_plecs.py`：仅比较实时 PLECS 与优化版，设置十倍事件生成终止上限，分开记录结束通知、进程退出、波形重建时间；支持明确标注的短窗口诊断。

依据交接包候选实现。交接说明明确：候选此前仅通过补丁结构测试，没有编译运行验证；本轮才进行 C++ 构建与验证。没有采用删除三个公开 REAL 监测输出的诊断模型。原网表、控制器、求根、状态传播、数值策略和容差保持现状。

## 编译与原生测试

| 平台 | Release | 通过/总数 | 失败 | 跳过 | CTest 用时 |
|---|---|---:|---:|---:|---:|
| Windows GCC 16.2 | 成功 | 26/26 | 0 | 0 | 21.99 s |
| WSL2 Ubuntu 24.04 GCC 13.3 | 成功，原生 x86-64 ELF | 26/26 | 0 | 0 | 11.90 s |

本次只做 Boost、A010 的案例验证；未运行全部 ROHM 案例。

## 仿真用时与输出大小

仿真时间从启动命令到事件文件写完后收到 COMPLETED 通知；另存进程退出墙钟。PLECS 从 simulate 调用到返回。控制模块编译、模型加载、事后文件复制、波形重建不计入仿真时间。顺序执行，无编译或其他仿真并发。

| 案例 | 程序 | 物理时长 | 仿真用时 | 文件/目录大小 | 结果 |
|---|---|---:|---:|---:|---|
| Boost | PLECS | 0.3 s | 10.0998 s | 19.200312 MB | COMPLETED |
| Boost | Windows 优化 PULSE | 0.3 s | 7.6464 s | 17.488134 MB | COMPLETED |
| Boost | Linux 优化 PULSE | 0.3 s | 6.5046 s | 17.488078 MB | COMPLETED |
| A010 | PLECS | 0.5 s | 14.7137 s | 32.000312 MB | COMPLETED |
| A010 | Linux 优化 PULSE | 目标 0.5 s，实际终止时间未知 | 运行 147.1867 s 后终止 | 未取得完整文件 | TIME_LIMIT_EXCEEDED |
| A010 | Windows 优化 PULSE | — | 未运行 | — | 按上限停止后续工作 |

A010 十倍上限为 **147.137404 s**。GNU timeout 终止原生 ELF，WSL 返回信号码 9；进程查询确认已退出。强制终止时没有最终报告或完整 `.pevt`，空目录不作为有效的 0 B 输出结果。

大小采用十进制 MB。PLECS 为返回 MAT，PULSE 为事件文件及外部报告目录。Boost PLECS 为 300,001 个参考时间点；PULSE 保留原 SAVE_DT=0.2 µs。A010 保留原初值、控制器、全部公开输出与原 SAVE_DT。

Boost 单独重建耗时：Windows 13.3476 s，Linux 9.2408 s；这些时间不计入上述仿真时间。

## 精度

Boost 的实时 PLECS 时间及数值与案例库原参考 CSV 逐位相同。Windows、Linux 优化版均完成 0.3 s，30,003 个提交事务，并将事件文件重建至原始密集网格后比较案例库 7 个参考通道。

两平台全网格 mean/rms/max 统计均为 **20/21**；判据为 channel.atol + 1% × |参考值|，不做时间平移或过滤。该诊断不替代完整历史窗口验收。

| 未通过项 | PLECS | 优化 PULSE | 绝对误差 | 允许误差 |
|---|---:|---:|---:|---:|
| CH003 最大值 (A) | 15.364982075 | 15.038709641 | 0.326272434 | 0.153749821 |

这是已有的 PLECS 峰值偏差；本轮未改变模型或容差。逐点 RMSE、最大误差及全部统计条目见证据 JSON。

**A010 完整精度未完成**：十倍上限先触发，未启动完整重建。不能将 Boost 结果或交接包的短时诊断当成 A010 完整通过。

## 当前边界与后续诊断

两项优化尚未使 A010 在十倍上限内完成。A010 的 REAL 监测输出进入模态编译缓存键的问题不在此次两项改动中；不能通过删除这些输出绕过。用户要求暂时停止完整仿真并调查原因，当前版本作为可审计优化候选推送，不宣称 A010 问题已解决。

用户随后授权相同原模型的 50 ms PLECS/Linux 短切片诊断；独立目录 `reports/pevt-opt-a010-50ms-20261102`。短切片不是 0.5 s 完整验收。提交准备时的状态保存在证据 JSON；最终诊断结论另行记录。

## 本地证据与运行入口

- [机器可读证据](PEVT_Hot_Cache_Boost_A010_Evidence.json)
- Boost：`reports/pevt-opt-boost-20261102/ledger.json`。用户要求取消原版比较时该批已完成；此报告与证据只展示 PLECS、优化版数据。
- A010：`reports/pevt-opt-a010-20261102/ledger.json`。
- Windows：`build-event-opt-windows/pulse-solver.exe`。
- Linux：`/root/pulse-pevt-opt/build-linux/pulse-solver`。
- 原始交接包和构建产物留在忽略目录，不提交二进制。

```powershell
python scripts/benchmark_pevt_vs_plecs.py --case-set ../PULSE-case-set --out reports/NEW --native-out /root/NEW --win-event build-event-opt-windows/pulse-solver.exe --linux-event /root/pulse-pevt-opt/build-linux/pulse-solver --linux-source /root/pulse-pevt-opt --only rohm-c002-d-boost rohm-a010-dot-totem-pole-pfc-sync --max-event-plecs-ratio 10
```
