# B1/B2 COW 重构合入与回归

日期：2026-11-03。基线：`performance/stage-b-20261103`，`0cb30419575f9254901882c14aa88d6e01e78f3f`。新分支：`performance/stage-b-cow-20261103`。

## 结果

Windows/Linux Release 均成功，CTest 均 **32/32，通过；0 失败、0 跳过**。Linux A010 完整 **500 ms / COMPLETED**，本轮一次仿真墙钟 **61.601002 s**，相对保存的 Stage B **68.084811 s** 减少 **6.483809 s / 9.52%**，比值 **1.1053×**。

5 ms、500 ms 的 PEVT 第 2–10 段记录数和 SHA256 全部相同；实际重建的 **5,000,001 点、17 路波形以及时间数组逐位一致**。六个故障点的完整回滚快照与旧 B 相同；Windows 新版的六点快照也与 Linux 相同。未实施阶段 C。

## 合入范围与编译问题根因

已在固定基线上执行附件 `scripts/apply_remaining_b.py . --in-place`。ZIP SHA256：`65fe62836366326d727059c3d8978f7c22e48afeab3ad99fda48eadc1a523a4a`。脚本初次生成 34 个文件；附件明确属于未完整编译的候选实现。

- `Mode` 的五个矩阵移入 `ModeDefinition`；观测矩阵、残差矩阵、信号映射和 guards 移入 `ModeBinding`，分别由 `CowValue` 管理。共享读取返回 const 引用，修改仅经 `.edit()` 分离。
- `RunState` 的 regs、software、agenda、generations 改为 COW。冻结检查点和候选共享只读数据，候选写入独立副本；失败仍走原事务丢弃和重试路径。
- `src`、现有测试同步迁移访问接口。控制器读取的旧字节和写入的新字节继续独立；物理/内部状态向量仍按值保存。小型 Mode bools/segments 等仍按值复制，未声称整个 Mode 的全部字段都做到零复制。
- 修复自动迁移将只读遍历、引用、条件判断误判为 `.edit()` 的问题。尤其修正了 const 检查点、Flow 构建、原方程验证和归档比较中的误写访问。
- 修复按名称匹配误改 `engineering::FlowData::guards` 和 `first_root::Result::guards`。后两份 first_root 源文件已恢复为基线字节，未改根搜索算法。
- 修复 Eigen `M << ...` 逗号初始化遗漏的写访问。新增两项测试的 assert 改为 Release 中仍执行的检查，并加强首次分离、异常和提交后旧快照隔离检查。

11 份改动的生产 `.cpp` 经逆向去除 COW 访问与只读 const 标记后，与基线表达式逐字相同；具体审计结果和生成后修复文件哈希保存在 EVIDENCE.json。没有删除数值检查、调整容差、修改物理参数或改变原浮点表达式顺序。`scripts/apply_remaining_b.py` 保存原生成器，实际集成修复以本分支 Git diff 为准。

C++ Mode/RunState 存储接口发生变化，使用旧 C++ 字段的调用者需要重编译并迁移 read/edit；C 求解器 ABI 和软件模块 ABI=2 保持原有契约。

## 编译和测试

| 平台 | Release 工具链 | CTest | 失败 / 跳过 | CTest 墙钟 |
|---|---|---:|---:|---:|
| Windows x86-64 | GCC 16.2、Ninja、CMake | 32/32 | 0 / 0 | 16.11 s |
| WSL2 Ubuntu 24.04 x86-64 | GCC 13.3、Ninja、CMake 3.28.3 | 32/32 | 0 / 0 | 5.11 s |

原 30 项全部保留，新增 `stage_b_cow_transaction`、`cow_value`。涵盖软件域 ABI/实例独立性、网表与模态、状态传播、根与联合事件、缓存、事务回滚、三策略重试及 PEVT/重建协议。Release 使用 `-O3 -DNDEBUG -ffp-contract=off -fno-fast-math`、`EIGEN_DONT_PARALLELIZE`；新增检查不受 NDEBUG 影响。

六点额外探针分别链接旧 B 与新版 `pulse_core`：after_queue、after_reg、after_mode、after_propagation、before_output、retry_after_closure。逐位提交向量、完整 MCU 字节和 invocation、REG/软件输出、agenda、generation、事件、版本、诊断和策略失败列表一致。探针未链接到 pulse-solver。Windows 同一探针的全部结果与 Linux 基准相同。

## A010 Linux 单轮性能

机器：AMD Ryzen 5 6600H，6 核/12 逻辑 CPU，WSL2 Ubuntu 24.04。原案例 `rohm-a010-dot-totem-pole-pfc-sync`；使用此前固定的相同 netlist.md、controller.c、transition.h 和 Linux ELF 控制模块，软件 manifest/依赖/ABI 检查照常执行。原 T_END=0.5 s、SAVE_DT=0.1 µs、13 路模拟和 4 路数字输出均保留。

| 项目 | 原 Stage B | B1/B2 COW |
|---|---:|---:|
| 完整终止时间 / 状态 | 0.5 s / COMPLETED | 0.5 s / COMPLETED |
| 命令开始至归档写成、COMPLETED 通知 | 68.084811 s（保存基准） | **61.601002 s** |
| 进程退出总墙钟 | 68.135646 s | 61.657131 s |
| 操作系统 CPU 时间 | 69.251800 s | 62.19 s |
| 报告 run_seconds | 64.206450 s | 57.559146 s |
| 峰值 RSS | 本基准未记录 | 1,162,312 KiB（约 1.11 GiB） |
| out.pevt | 162,836,775 B | 162,836,777 B |
| 事务数 | 159,037 | 159,037 |
| 根查询 | 159,036 | 159,036 |
| 模态编译 | 26 | 26 |
| 原方程检查 / 构建 / 命中 | 477,111 / 19 / 477,092 | 477,111 / 19 / 477,092 |

5 ms 前缀两版均 2,393 次事务，payload SHA256 相同；短窗墙钟 1.171769 / 0.945542 s。正式 500 ms 仅新版运行一次，旧版使用已保存且核对程序和归档哈希的 68.08 s 基准；不是同期多轮 A/B 或稳定中位数。132.829099 s 上限未触发。CPU 与墙钟计时来源和精度不同，不以两者小幅差异推断并行度。

计时从命令启动至写完事件文件后的 COMPLETED 通知，包含程序初始化、求解、事务归档与写出；不含控制器预编译、哈希比较、故障探针及波形重建。run_seconds 是程序已有内部计时口径，不用它替代端到端墙钟；本轮未额外细分所有内部阶段，也未测运行时 COW 分离总次数或热点，不凭静态结构声称收益来源。

## SHA256 与逐位波形

- 原 PEVT 整文件：`41f8b5ff09eccb42a3c3e278daf0d856c1a2fa6191286ea84e9f03f689209633`。
- 新 PEVT 整文件：`c414df13572985c0dadce67695902bce171bf1d04a160489561d6e2c893c8f20`。
- 第 **2–10 段**所有记录数和 payload SHA256 完全相同，包含方程、状态、事件、传播与终止数据。每段存储的摘要都重新对内容校验。
- 第 1 段只发现六个元数据差异：compile_seconds、parse_and_compile_seconds、parse_seconds、run_seconds 和两处源码指纹。完整列表见 METADATA_DIFFERENCES.json。**整文件哈希不相同，未声称整个 PEVT 文件逐字相同。**
- 因不满足整文件 SHA256 相同的提前结束条件，实际额外完成一次完整重建。17 路公开输出、time 和 metadata 共 19 个 `.npy` 成员的未压缩内容 SHA256 全部一致，连同 dtype/shape/原始浮点字节一起核对，不使用误差容限。
- 重建程序内部计时 66.340401 s，独立进程总墙钟约 67.23 s，全部排除在上述仿真时间之外。逐位检查完成后不再追加性能轮次或其他案例。

## 精度边界与剩余事项

对原 Stage B 的事件/波形回归通过。本轮没有重新运行 PLECS；基线已知的 CH006/CH007 各 18 个逐点超限仍然保留，不能把逐位回归等同于消除这些原有差异，也不能宣称 PLECS 全点精度全部通过。此前 mean/rms/max 为 21/21，详见 Stage B 基线报告。

本次结构迁移没有达到附件提出的最终 20 s 愿景；实测为 61.60 s。未实施阶段 C、额外调度/归档内核改造或数值算法优化。未发现本次回归失败项；运行时复制/分离计数和新的函数热点尚未测量，未写成 PASS。

## 证据与复现

源码指纹，两平台一致：`19711696564f81923ba6102658b2403e274a3fcdb8a4141926d81e0589e0d3ae`。

- EVIDENCE.json：全部测试条目、命令、机器/编译器、程序/源码/模型哈希、PEVT 各段摘要、波形成员摘要、六点回滚和原始产物清单。
- PERFORMANCE.csv：单轮定量比较；MIGRATION_GENERATOR.json：原始生成清单；REFERENCE_HANDOFF.md：附件原始交接说明（其中未编译状态是作者打包时的状态）。
- 本地证据：`D:\codex\using plecs\pulse-linux-port\reports\remaining-b-20261103\`。
- Linux 原始证据：`/root/stage-b-cow-regression-20261103/`；编译目录 `/root/pulse-stage-b-cow-20261103/build-linux/`；旧基线目录保留。
- Git 保存源码、验证脚本和报告，不提交二进制、缓存、大归档或波形。完整原始输出留存本地并记录哈希。

复现入口：`scripts/remaining_b_regression.py --help`，`scripts/compare_remaining_b_waveforms.py --help`；故障探针源码 `tests/rollback_snapshot_probe.cpp`，实际编译/执行命令见 EVIDENCE.json 及原始日志。
