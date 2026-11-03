# Stage B 余下的结构性重构范围（本包未实施）

## B1 大项：真正的 ModeDefinition / ModeBinding 分离

当前本包把 ModeCacheData 的模板改为共享只读实例，但 `Mode` 仍包含 Eigen Matrix、Map、Guard 等大字段，`bind_observations` 仍会复制大字段。这是从强类型不可变缓存切入，而不是完成 Flyweight。

要真正减少大规模拷贝，需要：

- `include/pulse/core.hpp`：新增包含静态矩阵、原子拓扑、分解结果和静态信号映射的 `ModeDefinition`，其所有权为 `shared_ptr<const ...>`；`ModeBinding` 只包含随 REG/状态变化的观察量、残差、局部 guard 和当前分类状态。
- `src/descriptor.cpp`、`src/engineering_mode.cpp`：编译与绑定分开，使用严格依赖键，动态源、PWA 区域和控制输出完整参与失效判断。
- `src/solver_strategy.cpp`、`src/engineering_flow.cpp`：转用新的只读视图，保留原始求根与残差判据；只有静态项可跨事务共享。
- **验证**：复制前后差异基于完整 Mode/PEVT 归档，确保所有时间、状态、方程矩阵位级一致。

## B2 大项：事务增量日志

当前只去掉一次无需独立存在的 checkpoint 深复制，`RunState` 以及 closure 内 `snap` 仍包含大对象。真正的 B2 需要：

- `include/pulse/core.hpp`、`src/runtime.cpp`：把提交状态设为只读，事务 candidate 只记录变化字段；失败时丢弃 candidate 或按 journal 回滚；对软件 C 状态字节数组采用 Copy-on-Write，并保持每次调用独立 ABI 内存。
- `src/software.cpp`、`src/state_coordinates.cpp`：接收只读快照视图，并完成必要字段的动态映射。
- `src/trajectory.cpp`、`src/pevt.cpp`：只在事务正式提交后捕获精确状态/归档快照，不引用可变工作区。
- **验证**：所有失败注入点、三策略重试、旧 checkpoint、MCU 调用计数、PEVT 原生内容严格一致。

## 进入大规模重构前建议的量化门槛

先完整应用本包，运行 500ms A010 性能对照和差异检查。若仍未显著消除 Mode/RunState 复制瓶颈，再对剩余 B1/B2 做类型级大改，不要将结构性改造与时序语义修改混合提交。
