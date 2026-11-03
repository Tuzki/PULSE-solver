# Codex 合入指令：Stage B 分层增量补丁

本压缩包不是全仓库替换件。请使用准确的 Stage A commit `fe6859dbba117f36116615004f4dff392f3525cf` 创建独立 B 分支。先阅读 `README.md` 和 `docs/B_REMAINING.md`，明确此包只实施低风险 B1/B2/B3 前置改造，**尚未实现**整个 ModeDefinition/ModeBinding 的静态/动态物理分离，也尚未完成事务 COW journal。

1. 执行 `python apply_stage_b.py <repo> --in-place --zip <out.zip>`，遇到 SHA/锚点不匹配应停止，不作猜测性套补丁。
2. 检查变更集：8 个原有文件加 1 个新增测试，确认不存在无关修改。运行 Windows/Linux Release CMake 和全部 CTest（原 29 项 + 新增 1 项）。
3. 使用原始 A010 0.5 s、SAVE_DT=0.1 µs、13 模拟/4 数字通道；对照独立 Stage A 基线二进制，做事件归档第 2–10 段 SHA256 位级一致性检查，保持 159037 事务及原方程验证数。
4. 编写 `STAGE_B_EVIDENCE.md/json`，报告 CTest、功能一致性、墙钟/CPU、Flow 兼容次数、Mode 复制次数。如果优化收益不显著，重新 CPU Profiling 并指出原因，不虚报性能。
5. 本包未经整仓编译或 A010 运行，因此合入前必须自行完成编译、回归和失败定位。不要以削减校验、改变 T128、简化 PEVT 或放宽精度为代价。

**未授权的部分**：不要将 README 中“余下结构重构”自动当作已完成的代码提交。若继续做完整 Stage B，先完成 `ModeDefinition`、`ModeBinding`、`RunState` COW journal 的设计审查和独立测试，再分别提交。
