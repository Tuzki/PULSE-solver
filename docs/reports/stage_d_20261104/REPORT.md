# Stage D 完整合入与 A010 500 ms 回归

日期：2026-11-04（Asia/Shanghai）。基线：`performance/stage-c-20261103`，`fa2bc5ee4aab588ee91fb5b0513c692493799f7e`。独立分支：`performance/stage-d-20261104`。

## 验收结果

Windows/Linux Release 构建成功，两平台全部 **35/35 CTest 通过，0 失败、0 跳过、0 禁用**。两平台六点 A010 故障回滚快照与已验收 Stage C 完全一致。Linux 原生 A010 完整 **500 ms，COMPLETED**，正式仿真执行 **1 次**。

从命令启动到事件归档写成并返回完成通知为 **47.617847 s**；进程退出总墙钟 **47.677999 s**。与保存的 Stage C **57.716774 s** 比较，少 **10.098927 s / 17.50%**，墙钟比 **1.2121×**。OS CPU 少 **16.93%**。PEVT 第 **2–10 段**的记录数、长度及 SHA256 全部相同，原方程检查仍为 **477,111 次**。

## 完整合入范围

原附件 SHA256：`99ba4a6604ea9ad329a5ca2fd8b945abea6102c0f30dd4a4e1957f798f9f000c`。

先核对附件 manifest 的全部 10 个文件，再对固定 Stage C 执行 `apply_stage_d.py --repo <repo> --dry-run` 和正式应用；七个原有文件的全部锚点均通过。没有省略任何附件优化模块。原有六个无关未跟踪文件保留，未纳入提交。

| 模块 | 实际保留的 Stage D 实现 |
|---|---|
| D1 模态绑定 | Model 编译时建立冻结部件索引；held 表达式使用只查询的哈希表；线程局部 N/B/scale 矩阵工作区；512 项有界完整动态输入绑定缓存。 |
| D2 Flow | 单 guard 的轻量观察 Mode；观察行哈希后比较完整原始字节；同 Basis、原始锚点和 local_rate 的 24 阶 Taylor 状态共享；每条观察行继续独立投影及计算误差尺度。 |
| D3 事件归档 | value/state 使用完整 binary64 位向量键；实例和部件模态使用无歧义整数对键；查询向量复用；保持首次插入 ID 顺序、原编码与 PULSEES1 格式。 |
| 可观测性与测试 | 输出 `stage_d_rebound_cache` 命中/未命中计数，新增 helper 和集成 CTest；保留附件安装器及辅助比较/分析脚本，新增单次完整 Linux 回归入口。 |

修改：`include/pulse/core.hpp`、`src/semantics.cpp`、`src/descriptor.cpp`、`src/engineering_flow.cpp`、`src/pevt.cpp`、`src/runtime.cpp`、`CMakeLists.txt`；新增 `include/pulse/stage_d_runtime.hpp` 及测试/工具。修订后的安装器能够从固定 Stage C 重现全部七个生产/构建文件的最终规范化文本，见 `GENERATOR_REPRODUCTION.json`。

完整动态缓存键包含 bits、segments、全部 REG 的 binary64 位及数值策略，缓存位于一个 Model 的 ScopedModeCache 内。命中仍调用原 `instantiate_cached()`，重新执行物理状态约束、残差与候选重建检查；不缓存已接受状态。分类所需尺度随不可变模板保留，接受实例才清除其自身尺度指针。浮地参考行仍重建和验证。

Flow 共享只沿相同原始锚点的构造/继续路径传播。观察投影显式核对 Basis 指针及 local_rate；继续路径使用原锚点。24 阶递推表达式、阶数、long double 精度和逐观察行系数表达式保留。

## 集成修复与源码审计

1. Windows 首次 CMake 配置找不到 Python。重新指定现有 `Python3_EXECUTABLE` 后成功；没有改系统设置或移除依赖检查。失败日志保留。
2. 附件 helper 测试使用 `assert`，Release 的 `NDEBUG` 会使其不执行。测试文件在包含 `<cassert>` 前局部取消该宏，确保检查运行；求解器 Release 选项不变。
3. 新增独立 `stage_d_integration`，覆盖冻结索引、完整动态键、+0/-0、512 项淘汰、COW 污染隔离、不同物理状态重新检查、分类候选禁止传播、零/正负近零/快极点、幂零系统、多个观察行、不同锚点及变 guard 继续的逐位比较。安装器同步安装该测试。
4. 保留原文件的既有混合换行，避免全文件格式变化。`git diff --check` 按 CRLF 文件使用 `cr-at-eol` 检查，通过。

没有遇到必须修改数值算法或放宽容差才能解决的编译/集成问题。`instantiate_cached` 和候选重建检查正文、`engineering::next_events` 正文与 Stage C 相同；`runtime.cpp` 仅增加两行缓存报告。传播、工程模态、数值策略、T128、物理本构、状态坐标、事件内核、软件加载及 first_root 源文件均逐字节不变，明细在 `EVIDENCE.json`。模型、控制器、参考数据未修改。

## 双平台构建与测试

| 平台 | 工具链 | CTest | 失败 / 跳过 / 禁用 | 测试墙钟 |
|---|---|---:|---:|---:|
| Windows x86-64 | GCC 16.2、CMake 4.4、Ninja | 35/35 | 0 / 0 / 0 | 16.01 s |
| WSL2 Ubuntu 24.04 x86-64 | GCC 13.3、CMake 3.28.3、Ninja | 35/35 | 0 / 0 / 0 | 4.44 s |

原 Stage C 的 33 项全部保留，增加两个 Stage D 测试。Linux 另执行仓库 `scripts/run_validation.py --suite compatibility`，结果成功。完整测试列表、单项时间在 `TESTS.csv`。

两平台 Release 保留 `-O3 -DNDEBUG -ffp-contract=off -fno-fast-math` 和 `EIGEN_DONT_PARALLELIZE`。Linux 使用原生 ELF 求解器及 ABI=2 ELF 控制模块。Windows 和 Linux 实际运行报告的同一源码指纹：

`459855195e09b82a5195392e55a9351a85ec5879baffab2e5ec843ab6fd74842`。

故障点：`after_queue`、`after_reg`、`after_mode`、`after_propagation`、`before_output`、`retry_after_closure`。两平台均与各自保存的 Stage C 快照比较，全部相同；比较完整 internal/physical 原始位、软件实例状态字节及调用数、REG/软件输出、有效队列、generation、版本、事件、诊断与策略失败记录。取消未知来源中间项的 Stage C 负向测试及原事务重试测试也继续通过。探针不链接进求解器程序。

## Linux A010 完整单轮性能

机器：AMD Ryzen 5 6600H，6 核/12 逻辑 CPU，WSL2 Ubuntu 24.04。编译、CTest 和 Windows 故障测试结束后单独启动正式仿真；没有并行编译，也未加载采样器、分配观察器或阶段计时。

案例：`rohm-a010-dot-totem-pole-pfc-sync`。同一原始网表、controller.c、transition.h、初始条件及经 manifest 检查的控制模块，CLI 设定 `--t-end 0.5 --output-format trajectory`。保留 SAVE_DT=0.1 µs、13 路模拟和 4 路数字输出，未改为简化模型。

正式开始：2026-11-04 **01:34:15.901873 +08:00**。原始命令及 UTC 时间保存在 `measurement.json`。

| 指标 | Stage C 保存基准 | Stage D 本轮 |
|---|---:|---:|
| 终止时刻 / 状态 | 0.5 s / COMPLETED | 0.5 s / COMPLETED |
| 启动至归档写成及完成通知 | 57.716774 s | **47.617847 s** |
| 启动至进程退出总墙钟 | 57.768550 s | **47.677999 s** |
| OS CPU，user + system | 58.17 s | **48.32 s** |
| user / system CPU | 56.62 / 1.55 s | 46.92 / 1.40 s |
| 峰值 RSS | 1,162,484 KiB | 1,162,056 KiB |
| 内部 run_seconds（独立口径） | 53.704109 s | 42.880181 s |
| PEVT 文件 | 162,836,778 B | 162,836,834 B |
| 事务 / 根查询 | 159,037 / 159,036 | 159,037 / 159,036 |
| 模态编译 | 26 | 26 |
| 原方程检查 / 构建 / 缓存命中 | 477,111 / 19 / 477,092 | 477,111 / 19 / 477,092 |
| Flow 构造 / 继续 | 478,908 / 234,237 | 478,908 / 234,237 |

完成通知口径包含程序启动、初始化、仿真计算、事件归档和文件写出。总进程墙钟另包含清理退出。控制模块预编译、故障探针、离线哈希比较和波形重建不计入；没有实施本轮波形重建。

正式 Stage D **仅一次**，没有重跑取最快值。Stage C 复用前次保存的同机结果，已核验原始归档 SHA256；不是本轮交替多次统计，因此 17.50% 是本次单轮观察值，未声称统计置信度或长期稳定加速比。原 132.829099 s 停止上限未触发。

RSS 下降 **428 KiB / 0.0368%**，没有明显内存下降。文件多 **56 B**，来自元数据变化，数据段完全相同。

绑定缓存实测 `hits=225216`、`misses=152175`，合计 377,391 次查找，命中率 **59.6771%**。命中分支复用精确绑定模板，仍执行新物理状态进入检查；其余 152,175 次走实际绑定路径。原方程验证没有减少。Flow 构造次数也没有减少，本次不能据此宣称临时 Flow 构造已消除。

## 事件与精度回归

- Stage C 整文件 SHA256：`4430815d2bf95a1d9a6f86535b5de1371d0c54fd86d34ed086c810c959dc22cf`。
- Stage D 整文件 SHA256：`3d94981aea68ca2501ab6b1b4430ccb1b39b333febe280706dda0f5b1932c7ef`。
- 原严格 `stage_c_verify.py` 重新验证各段自身摘要，并比较第 **2–10 段**记录数、长度和 SHA256：全部相同，`different_simulation_sections=[]`。
- 第 1 段包含计时、源码指纹和新增缓存统计，不同；没有声称整文件字节相同。
- 16 项规定的报告字段均相同，包括事件/事务数、原方程检查、最终软件状态/输出、T_END、SAVE_DT、T_atom 和全部 17 通道注册。
- 未通过探索性误差比较器放宽验收；没有删除边沿、时间平移、减少通道或修改参考。
- 本轮未重新运行 PLECS、未重建 17 路波形。确认范围是完整 PEVT 仿真数据段逐位回归及上述报告字段相同。Stage C 已知的 PLECS CH006/CH007 各 18 个逐点超限仍作为继承限制保留，未声称已解决。

## 证据与未确定项

`EVIDENCE.json` 包含输入/控制模块、源码、二进制、命令、工具链、全部 CTest、双平台回滚、原始计时、完整报告与产物 SHA256；`PERFORMANCE.csv` 为单轮定量对照；`PEVT_COMPARISON.json` 为原严格比较器输出；`APPLY_MANIFEST.json` 为附件完整应用记录。

本地原始日志：`D:\codex\using plecs\pulse-linux-port\reports\stage-d-20261104\`。Linux 源码/Release：`/root/pulse-stage-d-20261104/`；原始性能与事件文件：`/root/stage-d-regression-20261104/benchmark/500ms-stage-d/`。大归档、二进制及构建目录留在本地，不上传 Git。

本轮没有遗留构建、CTest、回滚或完整 A010 严格归档回归失败。未测量 Stage D 各模块 Self/Total CPU、分配次数与字节量；不能把整体少 10.10 秒分摊为 D1/D2/D3 的各自收益。附件的多轮 50 ms、探索性误差及 profiler 入口保留为工具，本轮按用户要求使用完整 500 ms 单次结果验收，没有用微基准替代。
