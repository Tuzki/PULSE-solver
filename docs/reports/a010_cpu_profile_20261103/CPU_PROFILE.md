# A010 CPU 性能剖析（Linux）

日期：2026-11-03。分支 `profiling/a010-cpu-20261103`；求解器基线 `6e5dea9bc5f7c03a5258a738725df474433a20b5`，验证基线 `186c9ed37bd11aa39d24fc2a769a8898a389068c`。已 fetch 核对远端，核心源码、头文件、CLI、CMake 均无差异。

本轮只分析原始 A010 的仿真计算与完整 trajectory 生成。模型、controller.c、transition.h、初始条件、SAVE_DT=0.1 µs、13 路模拟和 4 路数字输出保持不变。按用户后续指示停止 Windows，波形重建不在本报告统计范围；已完成产物保留。

## 测量与版本

AMD Ryzen 5 6600H，WSL2 Ubuntu 24.04、Linux 6.18.54.1、GCC 13.3、CMake 3.28.3。常规计时使用既有 Release；采样副本仅增加 -g1，仍为 -O3 -DNDEBUG，两个 ELF 的 .text SHA256 完全相同，严格浮点选项不变。全部运行的源码指纹为 `e820d1dcb9a84707d6f2333ee965ef188e7be78f5a55511cb963f8e71601ab60`。

常规测量按 2、5、20、500 ms 顺序进行；20 ms 关闭/开启交错各三次，完整 500 ms 关闭/开启各一次。CPU 时间来自 OS 的子进程 user+system，墙钟从命令启动到完整事件文件写出后的 COMPLETED 通知，另记录进程退出。Python/控制器准备与归档校验在计时之外。原始逐次命令、UTC 时间、PID、文件 SHA256 见 EVIDENCE.json。

| 运行 | 完成墙钟 / s | CPU / s | 事务 |
|---|---:|---:|---:|
| 2ms_on | 0.590231 | 0.591231 | 953 |
| 5ms_on | 1.446355 | 1.448423 | 2,393 |
| 20ms_off_1 | 5.219480 | 5.120062 | 8,306 |
| 20ms_on_1 | 5.368200 | 5.147236 | 8,306 |
| 20ms_off_2 | 5.213598 | 5.107596 | 8,306 |
| 20ms_on_2 | 5.189286 | 5.117915 | 8,306 |
| 20ms_off_3 | 5.274724 | 5.191667 | 8,306 |
| 20ms_on_3 | 5.175376 | 5.131357 | 8,306 |
| 500ms_off | 106.330088 | 104.372768 | 159,037 |
| 500ms_on | 106.046038 | 104.120964 | 159,037 |

20 ms 关闭中位数 **5.219480 s**，开启 **5.189286 s**，相对差 **-0.578%**。负差值属于本轮测量波动，不是加速收益；三次测量不足以给出严格开销上界。完整开/关墙钟分别 106.046038/106.330088 s，同样未观察到可稳定分辨的内置计时开销。

## 各窗口阶段墙钟

| 窗口 | mode | flow | roots | original_checks | closure | archive_append |
|---|---:|---:|---:|---:|---:|---:|
| 2.0 ms | 0.066334 | 0.012784 | 0.024202 | 0.029450 | 0.227478 | 0.030000 |
| 5.0 ms | 0.162703 | 0.031362 | 0.059900 | 0.069337 | 0.568037 | 0.071505 |
| 20.0 ms | 0.573875 | 0.115301 | 0.191110 | 0.245709 | 2.113722 | 0.261969 |
| 500.0 ms | 11.212275 | 2.494920 | 2.831776 | 4.699389 | 47.698182 | 5.929806 |

20 ms 行为三次各阶段中位数，其余为单次。完整逐次数据见 PHASE_TIMINGS.csv。500 ms 开启计时的细节如下：

| 阶段 | 总墙钟 / s | Scope 次数 | 每次 / µs | 占完成墙钟 |
|---|---:|---:|---:|---:|
| mode | 11.212275 | 159,037 | 70.501 | 10.57% |
| flow | 2.494920 | 159,037 | 15.688 | 2.35% |
| roots | 2.831776 | 159,036 | 17.806 | 2.67% |
| original_checks | 4.699389 | 159,037 | 29.549 | 4.43% |
| closure | 47.698182 | 159,037 | 299.919 | 44.98% |
| archive_append | 5.929806 | 159,037 | 37.286 | 5.59% |

这些是 steady_clock 墙钟范围，不是互斥 CPU 分类；存在未覆盖区间，也不能把百分比相加视为 100%。original_checks 的 159,037 次 Scope 内每次执行三个检查，真实验证总数为 477,111。flow Scope 只覆盖事务开始时的 Flow 选择/延续，不能代表全部 478,908 次构造。

## 独立 CPU 采样

使用完整 Ubuntu perf 6.8.12，cpu-clock 199 Hz、DWARF 栈 16 KiB；对同一最新代码另跑完整 500 ms，关闭内置阶段计时。采样运行完成墙钟 105.833461 s，退出 105.884212 s；CPU 104.184832 s（user 102.704855，system 1.479977）。共记录 21,121 个样本，其中目标 PID 的 CPU 样本 **21,057** 个；已过滤 Python/编译器。原始 perf.data 为约 336 MB，完整保存。

Self 是采样叶函数占比，Total 是包含子调用的栈占比；Total 彼此重叠。CPU 秒为 OS 总 CPU × 样本权重占比的估计，不是独立函数秒表。函数排行以无内联展开的物理 ELF 栈为主；匹配的 libc 调试符号已补齐。内联展开存在优化范围别名，不能当成额外真实调用；补充导出完整保留。

| 排名 | 函数（缩写） | Self CPU | Total CPU | 源码/归属 |
|---|---|---:|---:|---|
| 1 | multiply_digits | 14.17% | 16.14% | src/time_origin.cpp:59 |
| 2 | __memcmp_avx2_movbe | 8.81% | 8.82% | ./string/../sysdeps/x86_64/multiarch/memcmp-avx2-movbe.S:416 |
| 3 | bind_observations | 8.75% | 18.04% | src/descriptor.cpp:739 (discriminator 4) |
| 4 | _int_malloc | 6.61% | 11.90% | glibc/malloc/malloc.c:3980 |
| 5 | malloc | 4.26% | 15.50% | glibc/malloc/malloc.c:3328 |
| 6 | cfree@GLIBC_2.2.5 | 3.57% | 8.24% | glibc/malloc/malloc.c:3398 |
| 7 | _int_free | 3.53% | 3.53% | glibc/malloc/malloc.c:4608 |
| 8 | malloc_consolidate | 3.45% | 4.91% | glibc/malloc/malloc.c:4876 |
| 9 | __memmove_avx_unaligned_erms | 2.99% | 3.11% | ./string/../sysdeps/x86_64/multiarch/memmove-vec-unaligned-erms.S:660 |
| 10 | Flow::compatible | 2.62% | 8.17% | src/engineering_flow.cpp（采样指令落在 char_traits.h） |
| 11 | Eigen::internal::gebp_kernel<double, double, long, Eigen::internal::blas_data_mapper<double, long, 0 | 2.53% | 2.71% | third_party/eigen-3.4.0/Eigen/src/Core/GenericPacketMath.h:215 |
| 12 | unlink_chunk.isra.0 | 2.32% | 2.32% | glibc/malloc/malloc.c:1614 |
| 13 | pulse::engineering:: | 2.03% | 3.70% | third_party/eigen-3.4.0/Eigen/src/Core/AssignEvaluator.h:517 (discriminator 1) |
| 14 | std::_Rb_tree_increment | 1.59% | 1.60% | ??:? |
| 15 | std::_Rb_tree<std::__cxx11::basic_string<char, std::char_traits<char>, std::allocator<char> >, std:: | 1.20% | 3.64% | third_party/eigen-3.4.0/Eigen/src/Core/util/Memory.h:203 |
| 16 | Eigen::internal::gemm_pack_lhs<double, long, Eigen::internal::const_blas_data_mapper<double, long, 0 | 1.19% | 1.19% | /usr/lib/gcc/x86_64-linux-gnu/13/include/emmintrin.h:169 |
| 17 | pulse::portfolio_original_check | 1.18% | 4.28% | /usr/include/c++/13/bits/basic_string.h:804 |
| 18 | pulse::engineering::Flow::bounds | 1.16% | 1.22% | /usr/include/c++/13/cmath:220 |
| 19 | std::_Rb_tree_node<std::pair<std::__cxx11::basic_string<char, std::char_traits<char>, std::allocator | 0.86% | 7.10% | third_party/eigen-3.4.0/Eigen/src/Core/util/Memory.h:182 |
| 20 | Eigen::internal::general_matrix_vector_product<long, double, Eigen::internal::const_blas_data_mapper | 0.86% | 0.86% | third_party/eigen-3.4.0/Eigen/src/Core/products/GeneralMatrixVector.h:234 (discriminator 1) |

FUNCTION_HOTSPOTS.csv 保存全部物理函数排名、完整符号、源码行、Self/Total 样本、采样命中/CPU 秒、代表调用栈以及已知调用计数。内联函数不具备可独立探测的入口；其开销记在实际承载代码的物理函数中。

### 入口计数与调用栈

独立 20 ms uprobe 入口计数如下。此计数运行约 8.02 s，比正常运行更慢，只用于调用次数；不混入前述基准或内置计时开销。未对 malloc/free 等全部函数设入口探针，相关真实调用频率列为未知，不能把样本数当作调用次数。

| 函数 | 20 ms 实际调用数 | 每事务调用数（8,306 次事务） |
|---|---:|---:|
| multiply_digits | 3,399,429 | 409.274 |
| decimal_origin | 13,255 | 1.596 |
| flow_compatible | 42,025 | 5.060 |
| bind_observations | 18,953 | 2.282 |

代表性真实路径（完整符号栈见 CSV 和原始导出）：

- `main → simulate → exact_time_origin → decimal_origin_from_binary_time → multiply_digits`。
- `simulate → closure → engineering::update_mode / portfolio_compile → compile_specified → bind_observations`。
- `simulate → closure → software::Session::execute → Data::call → state_signal → Flow::compatible`。
- `simulate → engineering::next_events → Flow::value / Flow::bounds`。
采到 engineering::next_events 的栈 **575** 个；`fri::` 和 `first_root.cpp` 均为 **0**。这确认本次 A010 主要根搜索位于 engineering_flow.cpp；零样本不构成数学上的绝不调用证明，但没有证据把 first_root.cpp 当作主要热点。

## 十项问题的测量回答

1. 约 103 秒主要耗在哪里：本次复现为 106.33 s。closure 范围墙钟 47.70 s，mode 11.21 s；物理调用栈中 bind_observations 含子调用约 18.04% CPU，精确时间来源转换 16.72%，软件 Data::call 12.75%，分配/释放路径并集 25.88%。这些口径重叠，不能累加。

2. 仍有重复计算：20 ms 入口计数证实 339 万次十进制乘法、4.2 万次兼容性检查、1.9 万次绑定。采样把实际成本定位到这些路径；不是根据调用次数推导 CPU 占比。完整运行仅 26 次模态编译、19 次原方程构建，当前主要问题不是每次重新 LU/QR。

3. 每事务平均 CPU：104.372768 / 159037 = **656.28 µs**。这是包含初始化、归档、最终写出和清理的摊销值，不是逐事务计时。

4. 477,111 次原方程验证：阶段墙钟 **4.699389 s**；独立采样 portfolio_original_check 含子调用约 **4.463 CPU s / 4.28%**，摊销约 9.35 µs/次（估计）。

5. 478,908 次 Flow 构造：物理构造函数含子调用约 **3.102 CPU s / 2.98%**，约 6.48 µs/次（估计）。Flow::continued 约 4.354 CPU s，Flow::compatible 约 8.515 CPU s；它们不是同一计数口径，不能简单相加。

6. 根搜索：159,036 次 root_queries；阶段墙钟 **2.831776 s**，engineering::next_events 含子调用约 **2.845 CPU s / 2.73%**。不是当前主导热点。

7. 归档：append 含子调用约 **5.472 CPU s**，其中 equation 去重路径约 **3.335 CPU s**（已包含于 append，不能重复加）。最终 PevtArchive::write 入口/返回直接测得 **1.768610 s 墙钟**；其物理栈约 **1.771 CPU s**。此范围包含复制、序列化、SHA256 和文件写入，不是纯磁盘 I/O。

8. 可优先减少的重复工作：绑定中的重复范数/缩放准备和临时对象；精确时间转换的重复常量乘法准备与分配；同一不可变软件输入快照逐通道重复兼容性检查。方案和收益假设见 OPTIMIZATION_PLAN.md，本轮没有实施。

9. 不能安全直接删除：真实状态传播和根定位、原方程/残差校验、联合事件闭合、事务回滚及 C 状态独立性、T128 精确时间来源、完整通道/事件状态记录、完整性哈希。所有缓存都需不可变输入和完整失效条件，不能以计数很大为由跳过校验。

10. 只选三个核心实现文件进入下一轮：**src/descriptor.cpp、src/time_origin.cpp、src/software.cpp**。分别对应实测绑定、精确时间转换、软件输入读取中的重复检查。runtime.cpp 的快照复制和 engineering_flow.cpp 的兼容性路径是后续结构工作；first_root.cpp 没有进入当前优先级。

## 资源使用、计数与时间边界

关闭 Profile 时总进程 CPU/退出墙钟为 **98.11% 的单逻辑核**。末段 27 个 1 Hz /proc 样本均为 1 个线程，观察到最大 RSS 1.085 GiB，VmHWM 1.119 GiB。遥测在进程启动后才接入，峰值是最终峰值的下界，不宣称整段内存峰值已完整捕获。

simulate 报告范围关闭/开启为 102.048090/101.744792 s，均包含在线 archive_append；不能称作纯数值求解时间。最终写函数约 1.769 s；程序完成/退出另记。未覆盖差额还包含报告构造、输出缓冲和对象清理，不全部归入写文件。波形重建排除。

| 指标 | 500 ms 实测 |
|---|---:|
| transactions / root_queries | 159,037 / 159,036 |
| mode_compilations / mode_cache_hits | 26 / 377,391 |
| Flow constructions / continuations | 478,908 / 234,237 |
| basis hits / misses | 483,014 / 10 |
| original checks / builds / hits | 477,111 / 19 / 477,092 |
| archive equation requests / definition encodes / hits | 514,713 / 20 / 514,693 |

## 证据与未确定事项

开、关 Profile 和采样三次完整运行的归档段 2–10 SHA256 逐段一致；20 ms 计数运行也与普通 20 ms 运行的这些段完全一致。段 1 含性能和平台元数据，允许不同。所有归档段 SHA256 均独立核对，17 路公开输出完整。

原始 perf.data、压缩调用栈、阶段报告、控制器构建记录、事件文件、计数器和匹配二进制均保存在本地，未将二进制产物加入 Git。Windows 镜像：`reports/a010-cpu-profile-20261103/native-evidence/`；WSL 原始目录：`/root/a010-cpu-profile-20261103/`。EVIDENCE.json 保存逐文件字节、SHA256、绝对路径、机器、命令和时间。

尚未确定：所有 malloc/模板函数的真实调用次数；部分 libstdc++ 外部源码行；采样统计误差及截断/尾调用造成的 Total 低估；长时稳定性和严格计时开销上界；各方案的实际收益。少量内联范围与写函数真实边界冲突，因此主结论采用物理函数栈，不拿内联别名当真实入口。

本轮不重做波形精度验收，也不声称既有 CH006/CH007 逐点偏差已解决。没有修改核心源码，没有执行优化方案，没有用缩短案例或减少通道获得完整运行结果。
