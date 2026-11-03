# Stage C C1/C2/C3/C4 合入与定量回归

日期：2026-11-03。基线：`performance/stage-b-cow-20261103`，`44207f2e863db73b234a1e778f72838ffe1b5e13`。新分支：`performance/stage-c-20261103`。

## 最终结果

Windows/Linux Release 均成功；最终全部 CTest 均 **33/33，0 失败、0 跳过**。两平台 A010 六点故障回滚与 COW 基线完全一致。Linux A010 完整 **500 ms / COMPLETED**，最终修复版墙钟 **57.716774 s**，相对保存的 **61.601002 s** 基准减少 **3.884227 s / 6.31%**；OS CPU 从 **62.19 s** 降至 **58.17 s**，减少 **6.46%**。峰值 RSS 增加 **172 KiB / 0.0148%**，未观察到内存下降。

最终 PEVT 第 **2–10 段**记录数、长度和 SHA256 全部一致；实际重建的 **5,000,001 点、17 路公开波形及时间数组逐位一致**。附件严格比较器要求的 17 项报告字段均相同。

## 合入内容

附件 ZIP SHA256：`c56d04f92b6dc696dd6726ebaee76e75a7ad7c968b09a9a9b112fdd04f843dca`。

在固定基线建立独立分支，以干净的临时 worktree 执行 `apply_stage_c.py . --in-place`，保留原工作区的六个无关未跟踪文件。原始包、生成结果和失败日志均保存。

| 项目 | 实际源码改动 |
|---|---|
| C1 | 新 event_kernel.hpp/.cpp 预编译 REG、DELAY、EDGE、PERIODIC 规则；runtime 直接使用。保持规则顺序、旧快照读取、精确文本 cycle key。 |
| C2 | REG/MCU 输出按需分离；无效 deadline 清理无操作时不分离；周期 Time/来源只解析一次；Flow 基于有持有者固定生命周期的 COW 身份查找 Basis，保留原值键缓存和原计算。 |
| C3 | 仅当定义/绑定共享同一 COW 存储时复用其字节相同结论；其他比较及动态 observer/residual-reference 校验保留。PEVT 编解码、字段和事件记录保持原样。 |
| C4 | 新事件内核 CTest、附件严格比较器、单轮 Linux 测量入口、缓存/取消/来源故障补充测试。 |

最终六个原有生成文件可由修复后的生成器全部 27 个唯一锚点重现。相对初次生成的生产源码，仅 runtime 的来源校验问题额外修正；新增测试扩展了实际取消/transport 时间、generation、160 个 Basis 的淘汰/生命周期和来源故障检查。新增测试在 Release 下仍执行。

未更改根定位、模态转换、状态传播、LU/QR、矩阵指数/特征分解的数值公式与运算顺序、T128、容差、物理模型或控制器 ABI。Basis 数值构造和值键函数、PEVT write/read 源码均与基线相同；其他关键数值源文件的字节检查见 EVIDENCE.json。

## 已定位并修复的问题

**1. 生成器基线哈希错误。** 包内将 pevt.cpp 的校验值写成 COW 之前的 `ec1cbd9...`，首次执行拒绝应用。已核对固定提交中的真实 blob `f533c9fdeb71362e1424c57486ec5932109cc9d6` 并修正；未关闭版本、干净工作区、blob 或唯一锚点检查。原值、修正值见 GENERATOR_REPAIR.json。

**2. 附件 C2 取消后的来源校验漏检。** 原 `check_agenda_origins` 会跳过含无法解析来源的相邻对。取消中间未知来源条目后，之前未直接比较的两个已知来源会成为相邻项。因此原包“仅删除即可由传递性保证不变量”的前提不充分。

故障注入用例只扰动测试 Model 的来源元数据，不改 A010：三条延迟的有效时刻依次为 1/2/3，中间来源未知，两侧来源冲突；0.5 时取消中间项。实际差分为：

| 核心版本 | 结果 | 已提交终止时刻 |
|---|---|---:|
| COW 基线 | STOPPED_UNRESOLVED / TIME_RESOLUTION_UNRESOLVED | 0 s |
| 附件原版 | **错误地 COMPLETED** | 4 s |
| 最终修复 | 与 COW 完整 JSON、诊断、事件和检查点相同 | 0 s |

修复：新增有效 agenda 变化标记，CANCEL 和 REPLACE 的 generation 变化后都重做原校验；新插入 deadline 时仍校验，初始化及周期重排后的校验保留。只有有效队列完全不变时复用此前结果。没有删除检查或放宽判据。回归用例已加入 `stage_c_event_kernel`，独立差分探针源码为 `tests/stage_c_origin_probe.cpp`。

**3. 本地 Linux 初次配置的准备脚本问题。** 外层命令展开了目录循环变量，导致源码复制到错误层级、CMake 报缺少源码；改用独立 Python 复制并重建后通过。这是测试准备问题，非求解器编译缺陷。初次错误日志仍留存。

## 双平台编译与测试

| 平台 | 工具链 / 构建 | 最终 CTest | 失败 / 跳过 | 测试墙钟 |
|---|---|---:|---:|---:|
| Windows x86-64 | GCC 16.2、CMake、Ninja / Release | 33/33 | 0 / 0 | 14.08 s |
| WSL2 Ubuntu 24.04 x86-64 | GCC 13.3、CMake 3.28.3、Ninja / Release | 33/33 | 0 / 0 | 4.45 s |

原 32 项全部保留，新增 Stage C 测试。严格浮点选项为 `-O3 -DNDEBUG -ffp-contract=off -fno-fast-math`，保留 `EIGEN_DONT_PARALLELIZE`。软件 ABI、实例状态独立性、事务三策略重试、联合事件、缓存、解析、传播、根搜索及 PEVT/重建协议测试全部实际执行。

六个 A010 故障点：after_queue、after_reg、after_mode、after_propagation、before_output、retry_after_closure。Linux 探针分别链接固定 COW 与最终 Stage C 核心；Windows 最终快照与此前 COW Windows 快照比较。提交向量原始位、完整 MCU 状态字节/调用次数、REG/软件输出、队列、generation、事件日志、版本、诊断和策略失败记录全部相同。额外探针不进入 pulse-solver。

## Linux A010 正式单轮性能

机器：AMD Ryzen 5 6600H（6 核/12 逻辑 CPU），WSL2 Ubuntu 24.04，Linux 原生 ELF 程序和 ELF 控制模块。

使用 `rohm-a010-dot-totem-pole-pfc-sync` 的同一固定网表、controller.c、transition.h、初始条件及已校验 ABI=2 控制模块，完整 T_END=0.5 s、SAVE_DT=0.1 µs，13 模拟/4 数字通道均保留。输入及模块哈希保存于 EVIDENCE.json。

| 项目 | COW 保存基准 | Stage C 最终修复版 |
|---|---:|---:|
| 仿真时长 / 状态 | 0.5 s / COMPLETED | 0.5 s / COMPLETED |
| 命令开始至事件归档写成、COMPLETED 通知 | 61.601002 s | **57.716774 s** |
| 进程退出总墙钟 | 61.657131 s | 57.768550 s |
| OS CPU，user + system | 62.19 s | **58.17 s** |
| 峰值 RSS | 1,162,312 KiB | **1,162,484 KiB** |
| 报告内部 run_seconds | 57.559146 s | 53.704109 s |
| out.pevt 大小 | 162,836,777 B | 162,836,778 B |
| 事务 / 根查询 / 模态编译 | 159,037 / 159,036 / 26 | 159,037 / 159,036 / 26 |
| 原方程检查 / 构建 / 命中 | 477,111 / 19 / 477,092 | 477,111 / 19 / 477,092 |

墙钟比值为 **1.0673×**，CPU 少 **4.02 s**；RSS 增加约 0.168 MiB，属于此次观察到的小幅增加，不宣称内存优化收益。5 ms 最终前缀双方均 2,393 次事务且数据段摘要相同。

正式最终版本运行一次，基线复用已保存的 61.60 s 单轮结果，并核对其程序、原始归档及完整 measurement.json；不是同期多轮中位数。计时包含启动、初始化、计算、事务归档和文件写出；波形重建、控制器预编译、故障探针和哈希校验排除。OS CPU/峰值 RSS 来自相同 GNU time 方法；不以 WSL CPU 与墙钟的小幅时钟差异推断并行度。

另保留附件原版的一次 57.842473 s 测量及重建结果；来源故障测试发现漏检后，已排除它作为正式验收结果。没有挑选多轮最快值，修复后的数字属于新的源码/二进制。132.829099 s 上限未触发。

## PEVT 和波形逐位验证

- 基线整文件 SHA256：`c414df13572985c0dadce67695902bce171bf1d04a160489561d6e2c893c8f20`。
- 最终整文件 SHA256：`4430815d2bf95a1d9a6f86535b5de1371d0c54fd86d34ed086c810c959dc22cf`。
- 第 **2–10 段**记录数、字节长度、payload SHA256 完全相同。比较器重新计算并核对存储的每段摘要。
- 第 1 段仅六项差异：compile_seconds、parse_and_compile_seconds、parse_seconds、run_seconds，以及两处源码指纹，见 METADATA_DIFFERENCES.json。整文件哈希不同，未声称整个文件字节相同。
- 最终版本实际完整重建，17 个 signal、time 和 metadata 共 **19 个 .npy 成员**未压缩字节 SHA256 一致，包含 dtype、shape 和所有原始浮点字节；无容差比较、时间平移或边沿过滤。样本数 **5,000,001**。
- 附件 `stage_c_verify.py` 同时检查 PEVT、要求的 17 项报告字段和全部波形成员，结果 `PASS_SCOPED_COMPARISON`，无分歧字段。
- 最终重建内部计时 **63.736977 s**，独立进程墙钟约 **65.28 s**，均不计入 57.716774 s 仿真时间。

## 精度边界与尚未测量项

本轮确认对固定 COW 基线的事件和波形逐位回归，通过不等于消除了基线已知的 PLECS 差异。未重新运行 PLECS，CH006/CH007 各 18 个原逐点超限保留，未改参考或判据。

本次实际收益约 6.31%，没有达到附件提及的最终 20 s 愿景。未进行额外函数级采样、内置阶段计时 A/B 或运行时 COW 分离计数，不能把静态修改范围当成 CPU 归因或声称未来加速倍数。最终编译、33 项 CTest、六点回滚、来源故障、500 ms、PEVT 和 17 路逐位回归均无遗留失败。

## 源码和证据

最终两平台源码指纹：`ad516d111e95fdcf9bf226da40bee4ceabc1bc069ad9b308b3d2bbf49bb9b642`。

- EVIDENCE.json：最终测试明细、性能、CPU/RSS、机器/工具链/命令、源码与二进制、模型和原始产物哈希、故障复现、波形和数据段摘要。
- PERFORMANCE.csv：最终基线对照；GENERATION_MANIFEST.json：初次生成文件；GENERATOR_REPAIR.json：生成器版本修正；REFERENCE_HANDOFF.md：附件原始交接文档，其作者环境的未编译状态不代表本报告状态。
- 本地原始证据：`D:\codex\using plecs\pulse-linux-port\reports\stage-c-20261103\`。
- Linux 原始证据：`/root/stage-c-regression-20261103/`，正式结果位于 `benchmark-final/`、`rollback-final/`、`replay-final/`；源码和 Release 构建位于 `/root/pulse-stage-c-20261103/`。来源漏检三版本差分见 `origin-repro/`。
- Git 只保存源码、测试、验证脚本和报告；二进制、大事件归档、波形及缓存留在本地并列出指纹。
