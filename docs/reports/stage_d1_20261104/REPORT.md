# Stage D.1 修复及严格回归

日期：2026-11-04。修复分支：fix/stage-d1-runtime-repair-20261104。父提交为审计分支的 bea2d59da6a450ea79e7dcff9bd3df4bd19e3e60；对照 Stage D 为 b3906c7713f057a763536629b5d7873cb21d34e9。

## 验收结果

Windows/Linux Release 全部 **36/36 CTest 通过，0 失败、0 跳过、0 禁用**；两平台六点 A010 故障回滚快照与 Stage D 完全一致。

Linux A010 完整 **50 ms / COMPLETED**，Stage D 与 D1 的 PEVT **第 2–10 段记录数、长度、SHA256 全部相同**，规定的 16 项数值/事件报告字段相同。两版均 **17,652 次事务、26 次模态编译、52,956 次原方程验证**。本轮重新运行对照和候选程序，没有使用微基准代替完整案例。

附件 D1a、D1b、D1c 全部保留。未发现正确性回归，未触发模块撤回；修复仅在独立分支，不合并 main。原 Stage D 和审计基线保留。

## 补丁应用与源码范围

附件 pulse-stage-d1-20261104.zip，SHA256：

2f50f577d9167beb89c4412eb40064cd5351307d26986820a32de318078e50d0

先在固定 bea2d59 的干净临时 worktree 执行原 apply_stage_d1.py 的 dry-run 和正式应用，全部 **13 个唯一锚点**通过。随后以相同锚点将已核对改动移入修复分支，核对生成的规范化文本与干净应用一致，保留原文件换行。原工作区六个无关未跟踪文件未覆盖、未纳入提交。

| 模块 | 文件 | 实际修改 |
|---|---|---|
| D1a | src/engineering_flow.cpp | same 比较函数使用通用 const 引用，避免 Vector 隐式转换为 Matrix；保留逐元素数值相等及 +0/-0 语义。 |
| D1b | src/descriptor.cpp、src/solver_strategy.cpp、include/pulse/solver_strategy.hpp | 在已有 ScopedModeCache 内增加 512 项 FIFO 坐标 Binding 缓存，源 COW 对象与 L 的完整位模式匹配；首次物化仍执行原矩阵表达式，命中只复用不可变派生 Binding。 |
| D1c | include/pulse/core.hpp、src/descriptor.cpp | ObserverBinding 构造时保存 A 的原归约顺序行范数；绑定时读取，B/N 范数仍动态计算；人工构造对象缺缓存时保留原计算回退。 |
| 回归 | tests/stage_d1_regression.cpp、CMakeLists.txt | 添加原包测试，并补充缓存关闭、外部 Model 不复用、嵌套作用域恢复检查。 |
| 计数/验证 | scripts/stage_d1_validate.py、scripts/auditing/runtime_repetition | 独立计数构建支持 D1 通用比较签名及新增缓存/范数计数；正式求解器不带审计计数器。 |

坐标缓存由每次仿真的 ScopedModeCache 所有。每个条目保留物理源 COW 所有者，防止地址释放重用；外部 edit 会分离。Model 不匹配、容量关闭、源对象变化或 L 位模式变化时不复用。缓存只保存 Binding 及 chart，不保存已接受状态、时间、残差结果或控制器实例状态。

原 compile_specified/instantiate_cached 的物理状态相关检查、accept_mode_entry、所有原方程检查继续执行。Binding 之外的 M、constraints、invariant 及候选尺度变换保留。报告证据同时逐字节核对未修改的传播、根定位、T128、事件内核、PEVT、软件 ABI/加载、状态坐标和物理本构源文件，并核对候选重建/进入检查函数正文。

## 构建、CTest 与回滚

| 平台 | 工具链 | 最终 CTest | 失败 / 跳过 / 禁用 |
|---|---|---:|---:|
| Windows x86-64 | GCC 16.2、CMake、Ninja / Release | 36/36 | 0 / 0 / 0 |
| WSL2 Ubuntu 24.04 x86-64 | GCC 13.3、CMake 3.28.3、Ninja / Release | 36/36 | 0 / 0 / 0 |

原有 35 项全部保留，新增 Stage D1 项。C++ 求解器及其测试的 Release 配置保留 -O3 -DNDEBUG -ffp-contract=off -fno-fast-math 及 EIGEN_DONT_PARALLELIZE；独立 C 测试目标保持原构建配置。Linux 另执行 scripts/run_validation.py 的 compatibility 入口，成功。

新测试检查：完整坐标变换与原表达式逐位相同、重复源复用、源/返回值 COW 隔离、chart 改变、物理源编辑、FIFO 淘汰、新作用域隔离、cache-off、外部 Model、嵌套恢复，以及数值 +0/-0 比较。原事务重试、软件 ABI、联合事件、状态传播及负向来源测试继续运行。

六个故障点：after_queue、after_reg、after_mode、after_propagation、before_output、retry_after_closure。两平台分别对照保存的 Stage D 快照，internal/physical 原始位、软件实例字节/调用次数、REG/软件输出、队列、generation、版本、事件、诊断和策略失败记录全部相同。故障探针只用于验证。

两平台实际运行报告中的同一生产源码指纹：

ff7029501f36ba6bd5d2e7a95c186099ee89193594220d36417b2bb56c87a8ed

## Linux 完整 50 ms 正确性

固定同一 rohm-a010-dot-totem-pole-pfc-sync 网表、controller.c、transition.h 和 ABI=2 ELF 控制模块，使用原 CLI 指定 T_END=0.05 s；保留 SAVE_DT=0.1 µs、13 路模拟、4 路数字输出和原始参数/初始条件。

每版分别完整运行 clean、allocation-only、count 三种程序/观察方式，共 6 次完整案例。所有运行均 COMPLETED。5 组严格比较构成完整对照：D1-clean 对 D-clean、每版 allocation 对本版 clean、每版 count 对本版 clean。比较使用原 stage_c_verify.py，重新验证各段存储的摘要，并比较第 2–10 段及全部要求的报告字段。计数插桩没有改变结果。

| 项目 | Stage D | Stage D1 |
|---|---:|---:|
| 仿真终止时刻 | 0.05 s | 0.05 s |
| 事务 | 17,652 | 17,652 |
| 实际模态编译 | 26 | 26 |
| 原方程验证 / 构建 / 命中 | 52,956 / 19 / 52,937 | 相同 |
| PEVT 大小（clean） | 21,267,391 B | 21,267,391 B |
| 数据段 2–10 | 与 D1 完全相同 | 与 D 完全相同 |

Stage D 整文件 SHA256：9b8ecd52f1c892d124f2e15c1ed58d14df51f55147d94ad37b03332b0cbe6b7b。

Stage D1 整文件 SHA256：4c604b39d6f0a82e1acb05516edda3dce4a514a0ff5f8e61956000e9c65469da。

第 1 段包含源码指纹、自动计时等元数据，因此整文件不同；未声称整文件相同。没有降低容差、忽略错误或减少通道。本轮没有重建波形、运行 PLECS 或运行 500 ms，验收范围为本次 50 ms 严格事件归档回归及原测试。

## 重新测量：公开分配 API

采用审计分支同一方法：对未插桩的 Release ELF 拦截公开 malloc/calloc/realloc/free；另外使用隔离源码计数构建归因路径。工具查重和输出自身的分配排除。两版均单线程、0 计数表溢出、0 分配失败。字节是累计申请量，不是 RSS 或存活内存；没有测量墙钟、CPU 时间或进行 CPU profiling。

本表来自本次新运行的 Stage D 和 D1：

| API | D 次数 | D1 次数 | D 累计字节 | D1 累计字节 |
|---|---:|---:|---:|---:|
| malloc | 43,215,408 | 33,161,098 | 4,779,060,127 | 4,027,493,562 |
| calloc | 5,045,359 | 3,100,731 | 234,815,879 | 157,030,759 |
| realloc | 41 | 41 | 25,480 | 25,480 |
| free，含 NULL | 51,841,564 | 40,124,141 | — | — |
| free(NULL) | 3,580,799 | 3,862,314 | — | — |
| 申请合计 | **48,260,808** | **36,261,870** | **5,013,901,486** | **4,184,549,801** |
| 每事务申请 | 2,734.0136 | 2,054.2641 | 284,041.5526 | 237,058.1125 |

申请减少 **11,998,938 次 / 24.8627%**，累计申请量减少 **829,351,685 B / 16.5410%**。不将累计字节下降解释为峰值内存下降；新增缓存会保留额外对象，未单独测量其峰值内存。

free(NULL) 上升约 7.86%，不是所有操作都下降。完整 API 分布保留在 ALLOCATIONS.csv。插桩会影响编译器对 malloc/calloc 和 free(NULL) 的优化，权威 API 数字只使用未修改 ELF 的拦截结果。两版 count 与 allocation-only 的合计申请次数均完全相同，累计申请字节仅差 56 B / 55 B；见 ALLOCATION_RECONCILIATION.csv。

## COW、范数及重复计算

| 操作 | Stage D | Stage D1 | 实际变化 |
|---|---:|---:|---|
| Flow::compatible 路径的 Eigen 分配 | 5,779,584 | **0** | 隐式 Vector→Matrix 临时对象全部消除；比较次数保留 |
| compatible 比较辅助函数 | 2,935,135 | 2,935,135 | 数值相等检查没有删减 |
| 坐标 Binding 物化/深复制 | 41,234 | **17,806** | 少 23,428 次，56.8172% |
| 新坐标缓存命中 / 未命中 | — | 23,428 / 17,806 | 仅命中复用，首次物化仍执行 |
| Binding COW 深分离合计 | 59,018 | **35,590** | 减少 39.6964% |
| bind 内深分离 | 17,784 | 17,784 | 新绑定输入未跳过 |
| Binding COW 浅复制/赋值 | 204,656 | 281,502 | 增加 37.5489%，包含缓存所有权/返回值管理 |
| Eigen 分配入口 | 21,256,781 | 11,512,269 | 减少 45.8419%；入口次数不同于公开 API 申请次数 |
| 绑定热路径 A 行范数实际归约 | 1,333,800 | **0** | 改为读取不可变缓存 |
| A 行范数缓存填充 | — | **1,950** | 26 个构造出的 ObserverBinding ×75 行 |
| A 范数读取 / 回退计算 | — | 1,333,800 / 0 | 所有实际绑定均命中静态范数 |
| B 行范数 / N 列范数 | 1,333,800 / 88,920 | 相同 | 动态计算保留 |
| 残差 / 候选尺度矩阵计算 | 17,784 / 17,784 | 相同 | 全部新输入继续计算 |
| Flow 构造 / observe | 50,301 / 49,279 | 相同 | 本补丁未处理该公共初始化 |
| Taylor 状态递推 | 14,127 | 14,127 | 原共享行为保留 |
| PEVT 显式 memcmp / 新定义 | 4,908,690 / 20 | 相同 | 本补丁未修改归档 |

A 范数的 D 数字是原绑定循环每行一次归约；D1 分别直接计数缓存填充、读取和回退。表中只比较这条绑定路径，不声称全程序其他线性代数检查中的范数只剩 1,950 次。缓存填充与绑定的完整 A 输入跨对象去重没有另作证明。

完整输入重复核对结果仍为：残差/尺度各 17,784 次请求、17,784 组输入，重复 0；Taylor 递推 14,127 组输入，重复 0。Flow 公共构造部分仍有 36,174 次相同 Basis+原始锚点请求，静态观察投影仍有 36,147 次相同 Basis+row 请求。没有把这些遗留项计作本补丁收益。

坐标缓存只消除可复用的派生物化，没有将每次事务的新物理状态检查缓存为旧结果。17,806 次坐标物化、17,784 次新绑定及 52,956 次原方程验证仍保留。

## 集成过程与尚未测量项

生产源码没有出现构建或正确性失败。两个工具准备问题已定位并解决：Windows 默认临时目录拒绝自检写入，改为工作区临时目录后原自检通过；A 范数循环的计数包装最初漏加大括号，导致仅计数副本编译失败，修复后重新编译并运行全部正式计数。失败日志保留，没有用失败的计数程序生成验收结果。

额外测试只扩展了原包 CTest 的隔离覆盖。没有删减检查、放宽容差、改动软件控制器或数值算法。全套生产/计数构建选项、最终计数器校准、源文件哈希和原始产物指纹均保留。

未测量 D1 的墙钟/CPU 性能、峰值 RSS、完整 500 ms 和新的 PLECS 精度。不能从申请次数下降推导加速倍数，也不能将前一版 47.62 秒作为 D1 成绩。

## 成果与原始数据

- EVIDENCE.json：完整版本、输入/控制模块、构建选项、双平台 CTest、双平台回滚、5 组严格比较、全部计数和产物指纹。
- PATCH_MANIFEST.json：原补丁 13 项操作及字节校验；最终扩展测试的哈希另列在 EVIDENCE.json。
- PEVT_COMPARISON.json：D-clean 与 D1-clean 的原严格比较器结果。
- ALLOCATIONS.csv、ALLOCATION_RECONCILIATION.csv：公开 API 与计数构建对账。
- COUNTS.csv、COUNTS_D.json、COUNTS_D1.json：完整调用计数与每事务值。
- EXACT_REPEATS.csv、PATHS.csv：完整输入重复及逻辑路径归因。
- TESTS.csv：两平台实际执行的全部 72 个测试项。
- REFERENCE_README.md、REFERENCE_VERIFICATION.md：原附件交接信息，不当作本机验收结果。

Windows 原始日志：D:\codex\using plecs\pulse-linux-port\reports\stage-d1-20261104\。

Linux 正式 Release：/root/pulse-stage-d1-20261104/；验证及完整案例：/root/stage-d1-regression-20261104/；隔离计数构建：/root/stage-d1-count-20261104/。

大 PEVT、编译产物和计数 ELF 留在本地，不提交 Git。
