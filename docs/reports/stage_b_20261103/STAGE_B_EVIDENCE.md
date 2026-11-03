# Stage B 增量补丁合入与验证

日期：2026-11-03。分支：`performance/stage-b-20261103`。基线：`fe6859dbba117f36116615004f4dff392f3525cf`。

## 实际范围

已按用户指定命令执行生成器，全部 8 个原有文件 Git blob 和唯一锚点匹配，输出 9 份完整源码及 `stage_b_full_sources.zip`。核心 8 文件与新增测试均保持生成器输出字节，未补写剩余 B 或阶段 C。

附件实际只实现低风险前置增量：不可变共享缓存模板；同步单次兼容性验证的 Flow 延续 API；提交状态只读检查点引用；任务输入/输出名称预解析。它没有完成 ModeDefinition/ModeBinding 彻底分离或事务 COW journal。完整边界见随本报告保存的 [CODEX_HANDOFF.md](CODEX_HANDOFF.md) 和 [B_REMAINING.md](B_REMAINING.md)。

| 核心文件 | 附件改动 |
|---|---|
| descriptor.cpp | 缓存条目 shared_ptr<const Mode>；绑定返回的 Mode 仍按值生成 |
| engineering.hpp / engineering_flow.cpp | checked continuation API；无检查分支保持 private，不跨事务缓存证书 |
| runtime.cpp | checkpoint 改为提交状态 const 引用，候选和 propagation_old 仍独立；重试恢复原检查点 |
| state_coordinates.hpp/.cpp / software.cpp | 预解析 selectors 和输出键；按当前快照保持原读取顺序和 Flow 分支 |
| CMakeLists.txt / stage_b_shared_flow.cpp | 新增真实核心测试 |

额外调整只在测试脚本：记录 COMPLETED 通知和 OS CPU、保持时间上限、复用并核对固定 Stage A 基准二进制 SHA256。独立回滚验证程序不链接进 pulse-solver；原求解器没有增加自写的 B/C 实现。

## Windows/Linux 编译与 CTest

| 平台 | Release | CTest | 失败 / 跳过 | 测试墙钟 |
|---|---|---|---:|---:|
| Windows x86-64 GCC 16.2 | 成功 | 30/30 | 0 / 0 | 14.05 s |
| Linux x86-64 Ubuntu 24.04 GCC 13.3 | 成功 | 30/30 | 0 / 0 | 5.08 s |

包含原 29 项与新增 Stage B 测试；软件 ABI/状态独立性、三策略重试、事务回滚、缓存、状态传播及事件/归档检查未禁用。Release、严格浮点编译选项和全部原检查保持不变。

## Linux A010 完整 500 ms

使用原始 A010 网表、controller.c、transition.h、初始条件、T_END=0.5 s、SAVE_DT=0.1 µs、13 路模拟/4 路数字输出。复用已编译的相同 Linux C 控制模块；Windows 未执行此性能仿真。

| 程序 | 实际终止 / 状态 | 完成墙钟 / s | OS CPU / s |
|---|---|---:|---:|
| Stage A（保存的单轮基准） | 0.5 s / COMPLETED | 72.830654 | 72.850649 |
| Stage B（本轮一次） | 0.5 s / COMPLETED | 68.084811 | 69.251800 |

相对保存的 Stage A 72.83 s，本次墙钟下降 **6.52%**，比值 **1.070×**。基线二进制 SHA256 已核对；不是同时重新测量的 A/B 对照，也不是多轮中位数，不据此声称稳定加速倍数。

计时从命令启动到事件文件写成后的 COMPLETED 通知；进程退出时间另存。控制器准备、归档哈希检查、波形重建和独立 CPU 采样均不计入。保留此前 132.829099 s 十倍上限，未触发。

两版均为 **159,037 次事务、26 次模态编译、159,036 次根查询**；原方程验证 **477,111** 次、构建 19 次、命中/回填 477,092 次。事件归档第 2–10 段的记录数和 SHA256 全部一致。

段 1 包含源码、性能和版本元数据，允许不同。没有通过减少检查、事件或输出通道提速。

## 波形、精度和回滚

本轮实际重建完整 5,000,001 点、17 通道波形；时间和全部公开波形数组与 Stage A 逐位相同。重建约 70.52 s，单独保存，不计入仿真性能。

PLECS 精度参考复用 Stage A 已保存的实时捕获，本轮没有重新运行 PLECS。原全网格 mean/rms/max 检查为 **21/21**；CH006/CH007 仍各有 **18/500,001 点**超过原逐点判据，最大绝对差分别约 **528.30429 V / 0.36990958 A**。未平移时间、滤边沿、改参考或放宽容差；对基线回归通过不等于对 PLECS 的完整逐点精度通过。

独立验证程序分别链接两版本 pulse_core，检查 after_queue、after_reg、after_mode、after_propagation、before_output、retry_after_closure 六个故障点。提交状态向量按位、完整 MCU 状态字节和调用计数、REG/控制输出、事件队列、generation、事件记录、诊断及重试结果均完全一致。该验证程序不进入求解器构建或数值路径。

## 已停止的后续检查

6.52% 为小幅单轮收益，已按交接要求启动独立 CPU 采样；原始采样在用户停止指令前完成，约 225.311 MB、14,165 个记录样本，保存于 WSL 原目录。用户随后要求“不用继续验证，推送结果”，因此未继续解析采样，也未进行额外函数入口计数。

**Flow 兼容调用总次数、Mode 复制总次数、本轮函数热点及剩余瓶颈归因尚未测出。** 不以缓存命中、Flow 构造或调用栈样本数代替这两个计数，也不把静态源码推测当作 CPU 结论。

## 产物

编译源码指纹：`846bb00786b2c46a47edbb629dfb38a0c3f37348e7ea0dc8601a1014794c6f9e`。

- [原始统计、文件指纹和结果](STAGE_B_EVIDENCE.json)
- [单轮定量数据](PERFORMANCE.csv)
- 完整修改源码 ZIP：本地 `reports/stage-b-20261103/stage_b_full_sources.zip`。
- 本地原始结果：`reports/stage-b-20261103/`；WSL：`/root/stage-b-regression-20261103/`。大归档、波形及二进制未提交 Git。

结论：附件增量 B 合入、两平台 Release/全部 CTest、Linux 500 ms 事件/17 通道/精度回归与六点回滚一致性已完成。剩余完整 B 重构、阶段 C 和用户取消的进一步性能分析均未实施。
