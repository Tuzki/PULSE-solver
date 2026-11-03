# Codex integration: PULSE Stage D full runtime patch

**任务：** 把压缩包提供的 Stage D 运行时源码合入 PULSE Solver，独立提交源码；再以 Stage C 基线做可复现实测。不得把上轮独立微基准的 66.75 倍当作求解器加速比。

## 基线

- GitHub: `Tuzki/PULSE-solver`, Stage C ref `fa2bc5ee4aab588ee91fb5b0513c692493799f7e`
- Case: `Tuzki/PULSE-case-set/rohm-a010-dot-totem-pole-pfc-sync/pulse/netlist.md`, with `controller.c`, `transition.h`
- 50 ms: `--t-end 0.05 --output-format trajectory`; 原有 17 通道、0.1 us SAVE_DT 均不变。

## 合入步骤

1. 基于 Stage C 建立单独 D 开发分支。保持 Stage C 文件不混入别的变更。
2. 对本包 `scripts/apply_stage_d.py --repo <checkout> --dry-run`；核对源码锚点，再实际执行并保存 manifest。
3. 编译 Windows/Linux Release，运行全部 CTest；任何编译/符号、Eigen 或生命周期问题由 Codex 基于完整源解决，不能删检查、放宽容差。
4. 对 D 代码检查完整动态值缓存的有效性：全寄存器 bitwise 键、mode bits/segments、strategy、Model 生命周期、分类/接受状态差别、浮地参考及 Mode 重分类；验证缓存命中 **依然执行** 进入检查。
5. 验证 Flow 所有 Taylor 共享点对应同一 Basis、同一 anchor、同一 local_rate；复测 near-zero-pole 与状态微差跨事件保持。
6. PEVT 所有类型化键必须按原协议的位级含义去重，保留 ID 首次插入顺序，尤其 +0/-0、符号位、模式负区段及重复事件。
7. **实际构建后** 用 `scripts/run_ab_50ms.py` 在同机完成三对以上交替对照，并保存 `RESULT.json`, `timing.csv`, perf/alloc 原始记录；可先探索性误差验收，后尝试 strict。
8. 分别报告 ①总仿真时间、②分配器请求与 CPU、③Mode/Binding CPU 和动态重绑定命中率、④PEVT CPU、⑤其他 CPU，以及 RSS/PEVT 字节数；每个数字有原始证据和测量范围。
9. 如某项优化使速度倒退，定量报告后修复或明确回退该路径；不得把 Stage D 设为假阳性。
10. 将 D 完整源码、集成修复、全部测试、Profiling 与 50 ms 定量报告单独 commit，供之后增量改善。

**最终验收原则：** 至少提供真实 Stage C 50ms 时间与真实 Stage D 50ms 时间，同机相同 Release 条件；先有数值与事件对照，再给倍数。首次探索性实验不强制 bitwise PEVT，但后续完整验收必须明确恢复严格回归要求。

## 核心变更代码文件

`include/pulse/core.hpp`, `src/semantics.cpp`, `src/descriptor.cpp`, `src/engineering_flow.cpp`, `src/pevt.cpp`, `src/runtime.cpp`, `CMakeLists.txt`, plus `include/pulse/stage_d_runtime.hpp` and `tests/stage_d_runtime.cpp`.

## 不应过度宣称

该包是**上述所有运行时热点优化的实际源代码**，不是仅有设计图；但不包括把整个求解器彻底重写为新的全量 IR/事件字节码。对更广的 IR 架构规划不能宣称已经实现。没有完成完整工程编译与 A010 仿真前，所有 D 性能收益均属未知。
