# D1 Linux A010 完整 500 ms 实测

2026-11-04。求解器提交：05fb315f8126561a74b45fb06bf2654b0d138800。

采用已通过 D1 验收的 Linux Release ELF，SHA256 为 1c8a0a4624fcef6be7ad9d6e7b83379910196a9310dc1ded0e45bd21d30e9cc0。原 A010 网表、控制器、初始条件、SAVE_DT=0.1 µs、13 模拟/4 数字输出保持一致。T_END=0.5 s，输出 trajectory，完整运行一次。

| 指标 | Stage D 保存基准 | D1 本次 |
|---|---:|---:|
| 启动至归档写成及 COMPLETED 通知 | 47.617847 s | **41.142489 s** |
| 启动至进程退出总墙钟 | 47.677999 s | **41.192035 s** |
| OS CPU，user + system | 48.32 s | 41.03 s |
| 峰值 RSS | 1,162,056 KiB | 1,171,692 KiB |
| 终止时刻 / 状态 | 0.5 s / COMPLETED | 0.5 s / COMPLETED |
| 事务 / 模态编译 | 159,037 / 26 | 159,037 / 26 |
| 原方程检查 | 477,111 | 477,111 |
| PEVT 字节数 | 162,836,834 | 162,836,833 |

完成通知口径少 **6.475358 s / 13.5986%**。Stage D 复用已核验程序和归档的同机单次结果；D1 本次运行一次，未做多轮统计。计时包含启动、初始化、仿真计算、事件归档及写文件；不包含构建、控制模块编译、哈希核对或波形重建。没有加载计数器、LD_PRELOAD 分配观察器或 CPU profiler。

原严格比较器验证 PEVT 第 **2–10 段**记录数、长度、SHA256 全部一致，规定的 16 项报告字段一致，结果 PASS_SCOPED_COMPARISON。第 1 段含源码与运行元数据，整文件摘要不同。

峰值 RSS 增加 **9,636 KiB（约 9.41 MiB）**；不宣称本次峰值内存下降。只增加实测证据，求解器源码未再修改。

详细数据及命令：BENCHMARK_500MS.json；严格比较：PEVT_500MS_COMPARISON.json。

Linux 原始目录：/root/stage-d1-regression-20261104/benchmark-500ms/。完整 PEVT、stdout/stderr、GNU time 原始输出及 measurement.json 均保留在该目录，大二进制不提交 Git。
