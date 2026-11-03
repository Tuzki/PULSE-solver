# Stage C A010 500 ms：执行次数与 CPU 瓶颈剖析

固定代码：`f8138727a45f7213898a87b0a10c94a57eb33c04`，分支 `performance/stage-c-20261103`。采集日期 2026-11-03。未修改 src/include/apps/CMakeLists.txt、模型、控制器、容差或算法；本次只提交分析工具和报告。

## 结论

优先处理反复创建绑定辅助数据、矩阵缓冲和小对象分配，其次处理 observe 投影准备与重复兼容/归档比较。临时 Flow 构造本体不是最大的热点：其在 observe 内约 **0.762 CPU s / 1.21%**；同一路径的局部多项式准备约 **2.365 s**、绑定 COW 复制约 **1.741 s**。直接优化构造次数，不能把整个 observe 的收益都算进去。

分配器独占约 **23.44% / 14.782 CPU s**；bind 连同所有子调用约 **28.15% / 17.750 CPU s**，两者重叠，不能相加。T128 与来源运算独占约 **1.84% / 1.163 s**。实际写系统调用仅约 **0.161 s**；PEVT 内存编码、查找、比较与分配和真正磁盘写出分开计量。

## 方法、精度与测量开销

Linux x86-64，WSL2 Ubuntu 24.04，Ryzen 5 6600H，GCC 13.3。Release 保留 `-O3 -DNDEBUG -ffp-contract=off -fno-fast-math` 和 EIGEN_DONT_PARALLELIZE；只为副本增加 `-g1`，其 .text 与验收版逐字节相同，SHA256 `d2e8a8803411b91ccbc5be1d788acbfbc2109b89c7424b9edc451eea046f3de9`。

采用两个互补的完整 500 ms 诊断通道，而不是混用受干扰的栈：

1. 精确计数：task-scoped eBPF 入口/返回聚合、observe 上下文和只读绑定身份统计、COW 真正分离分支计数、独立 LD_PRELOAD 分配观察器。全部配对探针零丢配、零重入冲突、零 map 错误。独立 100 次调用与嵌套调用校准通过。
2. 主要 CPU 归因：**不安装返回探针，不加载分配观察器**，perf cpu-clock 999 Hz、DWARF 32 KiB 栈，共 **61,912 样本**；另用 perf trace 统计 write/writev/fsync。返回探针会替换返回地址并截断 DWARF 外层栈，因此第一通道 1.8 GB 采样仅留作原始证据，不用于 Self/Total/火焰图。

函数 Self 只计栈顶；Total 每样本中同名物理函数去重后计一次，包含子调用。递归帧不重复叠加同一函数。各模块每个样本只分给一个类别，独占占比总和为 100%。绑定/observe 内部表是各自内部的分解，不能再与全局表相加。

调用次数是入口事件计数，样本数不是调用次数。优化后内联、未布点的函数明确标为未测；TOP20 中 libc/Eigen 等多数未独立布点，不能声称其调用次数已精确获取。函数平均 CPU 成本是独立 CPU 样本估计除以同输入完整运行的精确入口计数，不是精确逐次延迟。探针跨度包括调度与自身开销，另存 FUNCTION_COUNTS.csv，禁止当作纯 CPU 或与嵌套跨度相加。

早先提出的所有函数 CPU 时间相对统计误差 ≤1% **未达成，也不宣称达成**。CSV 附独立样本假设下的 95% Wilson 区间；它不覆盖采样相关性和系统偏差。按用户后续澄清，本轮以真实执行次数和重复比例为主要证据，时间用于排序；没有为追求小热点 1% 反复跑多轮。

## 资源与 61.60 s 基线

| 运行 | 完成墙钟 / s | CPU / s | 峰值 RSS / KiB |
|---|---:|---:|---:|
| Stage B COW，保存的未剖析基准 | 61.601002 | 62.19 | 1,162,312 |
| Stage C，保存的未剖析验收结果 | 57.716774 | 58.17 | 1,162,484 |
| 本轮独立 CPU 栈采样 | 62.099544 | 63.049700 | 1,162,484 |
| 本轮精确计数与分配统计 | 116.658169 | 117.978378 | 1,162,512 |

Stage C 的保存验收结果较 Stage B 快 6.31%；本轮带采样结果不能替代无剖析性能基准，更不能把计数通道的 116.66 s 解释成求解器退化。当前 CPU 样本给出较无剖析 Stage C 增加约 7.6% 的墙钟；计数通道的系统 CPU 达 42.694 s，开销很明显。

CPU 栈通道每 100 ms 读 /proc，共 618 个记录，观察到最大 **1 个目标线程**；分配观察器也仅记录 1 个分配线程。该内核缺少 /proc/PID/io，第一通道的监控因此未取得线程采样；已修正为可选 I/O 字段，使用第二通道完整线程记录和 perf trace 补足，未编造该字段。

## 精确执行次数与重复

完整运行 159,037 次事务、159,036 次根查询、26 次模态编译、477,111 次原方程检查。核心计数：

| 操作 | 完整执行次数 | 含义 |
|---|---:|---|
| observe | 472,296 | 每事务约 2.970 次 |
| Flow 两参数构造 | 478,908 | 含 observe 临时投影 |
| observe 内 Flow 构造 | **357,471** | 全部构造的 74.64%；observe 调用的 75.69% |
| bind_observations | **377,391** | 每事务约 2.373 次 |
| 只读 ObserverBinding 对象 | **26** | 精确地址聚合；总绑定次数校验一致 |
| 绑定路径 COW edit | 3,019,128 | 每次绑定正好 8 次编辑入口 |
| 绑定路径实际 COW 分离 | **377,391** | 每次绑定 1 次 |
| 全部已布点 COW 分离分支 | 734,886 | 其中非绑定 357,495 次；不是全部内联 COW 的泛化计数 |
| Mode 拷贝构造 | 969,125 | 不含未布点赋值或内联变体 |
| Flow compatible | 515,849 | 每事务约 3.244 次 |
| 二进制时间转十进制来源 | 285,107 | 每事务约 1.793 次 |
| PEVT equation 请求 / 比较 | 514,713 / 514,693 | 实际定义编码仅 20 次 |

26 个绑定对象只证明**静态绑定基础**反复使用，不代表它们的动态 held 输入完全相同。不能把 377,391 次矩阵更新都直接判为多余。

可明确定位的重复：`Assembler(...,false)` 每次绑定都会为同一个冻结 Model 的 **70 个 part** 重建 partidx。函数计数乘固定无提前退出的循环规模，推导为 **26,417,370 次索引插入迭代**；这是计数加源码固定循环推导，并非对每个循环回边单独布点。该路径不组装 A/F 等完整方程；避免误称其为 377,391 次重新因子分解。

observe 缓存未命中分支先复制 Mode，再经 COW 克隆包含所有映射的 ModeBinding，随后立即 clear maps、clear guards、替换为单个 OBSERVE row。完整运行 357,471 次进入构造分支，源码说明其整份映射复制随后被丢弃；这是值得重构的具体数据复制，不是仅因调用次数高而下结论。

## bind_observations 内部 CPU 分解

| 内部互斥类别 | 估计 CPU / s | 占 bind Total |
|---|---:|---:|
| matrix_math_and_matrix_buffers | 7.601 | 42.82% |
| strings_and_map_lifecycle | 6.700 | 37.75% |
| COW_binding_clone_including_children | 1.988 | 11.20% |
| mode_id_string_formatting | 1.273 | 7.17% |
| initial_Mode_copy | 0.188 | 1.06% |

依据真实物理调用栈、Eigen/COW/STL 函数和 DWARF 来源分类。矩阵类包含矩阵缓冲分配/复制；字符串类包含 map 节点生命周期，不能称为纯字符计算。COW 类包含其子调用。Assembler 构造在绑定上下文中约 **2.891 CPU s**；单纯模式 ID 格式化约 **1.273 s**，二者与内部表的其他类别存在包含关系，不可额外相加。

## observe 路径 CPU 分解

| 内部互斥类别 | 估计 CPU / s | 占全进程 |
|---|---:|---:|
| local_polynomial_preparation | 2.365 | 3.75% |
| view_binding_COW_clone | 1.741 | 2.76% |
| temporary_Flow_constructor | 0.762 | 1.21% |
| other_allocator_work | 0.552 | 0.88% |
| guard_matching_cache_lookup_and_evaluation | 0.435 | 0.69% |
| view_Mode_copy | 0.096 | 0.15% |

临时构造的精确入口/返回跨度合计 1.889809 s（重探针通道）；独立 CPU 栈估计 0.761745 s，约 **2.131 µs CPU/次**。两者测量口径和开销不同。更大的费用在前置 COW 和局部多项式准备；后者是否能共享必须保留 anchor、basis、行与误差界的完整语义。

## 模块独占 CPU

| 模块 | 独占 CPU | 估计 CPU / s |
|---|---:|---:|
| memory_allocator | 23.44% | 14.782 |
| mode_binding | 17.86% | 11.259 |
| pevt_archive | 10.41% | 6.562 |
| flow_evaluation | 7.85% | 4.946 |
| original_equation_checks | 6.85% | 4.316 |
| flow_compatibility | 6.79% | 4.278 |
| mode_entry_and_compile_residual | 5.26% | 3.316 |
| closure_residual | 4.90% | 3.087 |
| runtime_initialization_other | 2.72% | 1.712 |
| kernel_or_unknown | 2.37% | 1.492 |
| cow_binding_copy | 2.32% | 1.461 |
| state_mode_copy | 2.13% | 1.341 |
| t128_and_origins | 1.84% | 1.163 |
| flow_construction | 1.68% | 1.062 |
| software_control | 1.53% | 0.963 |
| event_scheduling | 0.97% | 0.609 |
| disk_io_kernel | 0.83% | 0.525 |
| root_search_own | 0.17% | 0.105 |
| flow_continuation | 0.11% | 0.069 |

`mode_entry_and_compile_residual` 包含缓存路径后的状态坐标/矩阵进入工作，不能读作 26 次真正编译耗时。根搜索独占只含其自身，包含 Flow 求值时 Total 约 4.46%；closure Total 约 41.19%，扣除独立分类的子工作后自身约 4.90%。C 控制器包装 Data::call Total 约 14.22%，包含观测/兼容等，软件控制自身约 1.53%。

## TOP20 物理函数

| # | 函数（此处截短，完整名称及源码见 CSV） | Self | Total | 精确入口次数 |
|---:|---|---:|---:|---|
| 1 | `__memcmp_avx2_movbe` | 12.19% | 12.20% | not instrumented / possibly inline |
| 2 | `_int_malloc` | 6.15% | 11.17% | not instrumented / possibly inline |
| 3 | `Eigen::internal::gebp_kernel<double, double, long, Eigen::internal::blas_data_mapper<double, long, 0` | 4.35% | 4.66% | not instrumented / possibly inline |
| 4 | `malloc` | 4.17% | 14.68% | not instrumented / possibly inline |
| 5 | `cfree@GLIBC_2.2.5` | 3.64% | 8.66% | not instrumented / possibly inline |
| 6 | `_int_free` | 3.56% | 3.56% | not instrumented / possibly inline |
| 7 | `malloc_consolidate` | 3.39% | 4.42% | not instrumented / possibly inline |
| 8 | `__memmove_avx_unaligned_erms` | 3.31% | 3.60% | not instrumented / possibly inline |
| 9 | `pulse::engineering::(anonymous namespace)::prepare_local(pulse::engineering::FlowData&)` | 3.19% | 5.70% | not instrumented / possibly inline |
| 10 | `pulse::(anonymous namespace)::bind_observations(pulse::Model const&, pulse::Mode const&, std::map<st` | 2.67% | 28.15% | 377391 |
| 11 | `Eigen::internal::gemm_pack_lhs<double, long, Eigen::internal::const_blas_data_mapper<double, long, 0` | 2.56% | 2.56% | not instrumented / possibly inline |
| 12 | `pulse::engineering::Flow::compatible(pulse::Mode const&) const` | 2.21% | 7.49% | 515849 |
| 13 | `std::_Rb_tree_increment(std::_Rb_tree_node_base const*)` | 2.07% | 2.07% | not instrumented / possibly inline |
| 14 | `Eigen::internal::general_matrix_vector_product<long, double, Eigen::internal::const_blas_data_mapper` | 1.83% | 1.83% | not instrumented / possibly inline |
| 15 | `pulse::engineering::Flow::bounds(unsigned long, double, double, int) const` | 1.81% | 1.93% | 662711 |
| 16 | `clear_page_erms` | 1.66% | 1.66% | not instrumented / possibly inline |
| 17 | `pulse::portfolio_original_check(pulse::Model const&, pulse::RunState const&, pulse::Mode const&, Eig` | 1.63% | 7.25% | 477111 |
| 18 | `unlink_chunk.isra.0` | 1.54% | 1.54% | not instrumented / possibly inline |
| 19 | `std::_Rb_tree<std::__cxx11::basic_string<char, std::char_traits<char>, std::allocator<char> >, std::` | 1.40% | 2.56% | not instrumented / possibly inline |
| 20 | `Eigen::internal::general_matrix_vector_product<long, double, Eigen::internal::const_blas_data_mapper` | 1.28% | 1.28% | not instrumented / possibly inline |

完整名称、实际源码、平均 CPU 成本、置信区间见 FUNCTION_HOTSPOTS.csv；真实栈见 TOP20_CALLSTACKS.md。Total 列不能相加。

## 内存与 I/O

公开分配 API 请求 **559,617,285 次**、累计请求 **68,881,827,693 B（68.88 GB）**，失败 0；不是同时存活内存，也不是 RSS。malloc 497,793,125 次，calloc 61,824,119 次，realloc 41 次。free 共 601,714,115 次，其中 free(NULL) 42,096,873 次；非空释放 559,617,242 次，与 malloc+calloc 请求量接近。请求量包含 realloc 的替换大小，不能直接当作新对象数。

观察器自检覆盖 9 个请求、787 字节。自检发现 reallocarray 会委托 realloc，已在工具中抑制嵌套重复计数；正式运行 reallocarray/memalign 等委托 API 次数均为 0，故此工具修正不影响已采集的 malloc/calloc/realloc 结果。保留了采集时动态库及其哈希，未偷偷替换原始证据。

分配器约占 14.782 CPU s；峰值约 1.11 GiB、分配失败为零，主要证据支持**分配/释放周转的 CPU 成本**，不支持“内存不足”。公开 API 之外的直接 mmap 等不计入请求统计。字节量没有按调用栈精确分配给每个模块，不能把采样百分比冒充各模块分配字节。

perf trace：writev 10 次、累计 160.667 ms；write 2 次、累计 0.153 ms，均零错误；未观察到 fsync/fdatasync。系统调用跨度不等于 CPU，也不等于数据已经持久化到物理盘。PEVT 数据文件约 162.84 MB，其编码和去重 Total 约 8.306 CPU s，明显不能全部归给磁盘。

## 优化排序、风险与验证

详见 OPTIMIZATION_PLAN.md。所有收益区间均为**估计**，未实现任何求解器优化；区间和模块占比存在重叠，不能直接相加。建议先做一项、核对精确次数和分配量下降，再核对完整 PEVT/数值行为，最后比较无剖析墙钟。

## 证据与限制

两条完整诊断运行均实际到 0.5 s / COMPLETED，保持全部 13 模拟/4 数字输出。PEVT 2–10 段记录数、长度、SHA256 及要求的全部数值统计，与 Stage C 验收版完全一致。本轮不重建波形、不重跑 PLECS。

原始文件留在 **/root/stage-c-cpu-profile-20261103/**：两个 perf.data、完整物理栈导出、计数、分配、I/O、线程记录、符号二进制与工具校准。EVIDENCE.json 列出实际命令、版本、机器及原始文件 SHA256。Git 仅保存工具、报告、CSV 和约 681 KiB 火焰图，不上传 GB 级采样、二进制或事件文件。

[交互火焰图](FLAMEGRAPH.svg) · [执行次数](FUNCTION_COUNTS.csv) · [资源比较](RESOURCE_COMPARISON.csv) · [绑定拆分](BIND_BREAKDOWN.csv) · [观测拆分](OBSERVE_BREAKDOWN.csv)
