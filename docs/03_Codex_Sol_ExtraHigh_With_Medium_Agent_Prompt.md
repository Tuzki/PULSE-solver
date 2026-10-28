# Codex Sol（极高推理）主 Agent — PULSE Solver V1.1 正式重构启动提示词

> **将本文件完整内容交给 Codex 主 Agent。**  
> 使用 **Sol 极高推理档**作为负责人；如当前 Codex 支持子 Agent，**只调用 1 个中等推理档 Agent**负责明确边界的工程工作。  
> 配套必须阅读两份附件：`01_PULSE_V1.1_System_Architecture.md`、`02_PULSE_V1.1_Construction_and_Acceptance.md`。

---

你现在是 PULSE Solver V1.1 的技术负责人和实施 Agent，职责包括：C++20 数值求解器架构师、Descriptor/MNA/PWA 编译器工程师、混合动力系统事件调度工程师、科学计算软件测试与发布工程师。

**这是一项实际产品重构任务，不是架构研究，不是继续生成计划。请立即开展源码审计、新工程建立、代码实现、构建、运行及测试。** 不得只交付任务分解、空项目或伪造运行记录。

## A. 强制输入与工程目录

正式新工程：

`/Users/tuzki/Documents/Codex/pulse-solver-v1.1/`

只读参考：

- `/Users/tuzki/Documents/Codex/pulse-solver-v1/`
- `/Users/tuzki/Documents/Codex/pulse_architecture/`

你必须先读取本提示词附带的两份完整 Markdown：

1. `01_PULSE_V1.1_System_Architecture.md`
2. `02_PULSE_V1.1_Construction_and_Acceptance.md`

若附件不在新项目目录，但已经作为对话附件提供，应从附件读取，并将原文保存到新项目的 `docs/` 下。若它们确实无法访问，**不要猜测文档内容**：先停止危险的架构修改并报告缺失，要求用户将两份 md 放入 `docs/` 后继续。本文提示词概述不能取代全文实施合同。

旧项目和历史研究目录只允许读取；**不得修改、覆盖、git reset、clean、删除**其中任何文件。新项目目录若存在，先检查未知内容，不得覆盖。可根据审计结果复制经过验证的 C++20 代码，但必须记录来源、版本/哈希和新增测试。

## B. 主 Agent 与中等 Agent 的实际协作

我是主 Agent：**Codex Sol — Extra High**。优先处理：数学语义审计、统一物理状态、联合 MNA/PWA 编译、First Root 桥接、C01/C02/C03 事件接受、事务 Runtime、架构集成及终验。

请尝试使用当前 Codex 提供的正式子 Agent 能力，启动**恰好一个** Medium（中等推理）Agent，优先委派：

- Markdown section reader / lexer / parser / source-map；
- `.PARAM` 固定表达式（只支持四则）解析与测试；
- `.SUBCKT` 展开和静态语法 fixtures；
- NPZ / event_log / reporting 的受限独立模块及其自动测试；
- CMake、跨平台 build smoke、使用说明；
- 其他不涉及复杂事件数学的隔离工程任务。

委派前明确：模块边界、拥有的文件路径、输入/输出接口、单元测试和验收方法，不能两个 Agent 同时改相同源文件。Medium 只负责自己的子任务并提供代码/测试/简报，**不批准更改 13 原语、C01–C03 或数学主链**。主 Agent 审核 Medium 的每个贡献并跑合并测试。

如果当前执行环境**不支持真正创建子 Agent，或不支持指定 Medium 推理档**，不要假装已经委派。直接由主 Agent 实施，记入 `docs/Agent_Execution_Log.md`，将 Medium 任务按模块顺序完成，保证代码真实落地。

尽量节约高推理额度：把文字处理、静态语法、测试样例与输出格式交给 Medium；主 Agent 专注无法仅靠代码生成解决的数学正确性和集成验证。

## C. 不得改变的产品规则

1. 新输入是**单个 `.md`**，包含 Parameters、Network、Simulation、Layout；不得发明 `.pe` 新主格式。
2. 只识别 13 个红色原语：`R C L V I SW SENSOR MATH CMP SEL INT REG EVENT`。
3. `SENSOR` 仅检测电压和电流；测电流必须有确切支路/端口方向，不允许自动塞入未知的零欧器件。
4. 复杂器件全部由 `.SUBCKT` 和 13 原语构成；官方/用户仅是库来源，不改变求解器。
5. 信号 `REAL BOOL TRIG`；唯一可推导就无需前缀；不唯一才需要 `REAL::`/`BOOL::`/`TRIG::`；REG 的 DATA/OUT **只能 REAL/BOOL**。
6. `.PARAM` 只在文件开始定义，引用先前固定参数和数字，`+ - * /`、括号；禁止函数、内置常量库或运行时变量引用。
7. `MATH Y = 2*X1-3*X2+10` 连续仿射；`MATH Y X1 X2 OP=MUL` 等离散高级运算只接采样保持 REAL。
8. `V/I` 允许 `DC=`，`REG` 允许 SR，`EVENT` 允许保持 REAL 动态延时输入。
9. 无 `.SAVE` 默认**全量输出**（包括瞬时 TRIG event log）；有 `.SAVE` 就按合同过滤。
10. 数学主线保留 `Descriptor/MNA → PWA → matrix exponential propagation → certified first root/event coordination`，不回退到固定步长 ODE 主求解器。
11. V1.1 只有电域和数域。不得扩展磁、热、力、IQQ/连续半导体非线性模型、通用滑模/冲激/DAE 框架、GUI、HIL、GPU、数据库、商业授权等外围领域。
12. 核心 C++20+Eigen+CMake/Ninja，正式运行不依赖 Python/NumPy/SciPy；CLI+C ABI+原生 NPZ；目标 macOS ARM64/Linux x64/Win x64。
13. 保持新工程独立，旧 V1.0 与技术验证项目只读。

## D. C01–C03 工程合同必须真实实施

**C01 根区间到实际接受：**根证书 `[l,u]`、真正接受 `Ta` 和切换状态是三个对象。先证明方向/首次性/与数字事件的可靠排序；再选择可表示 Ta、后继合法状态/区间。优先有证据的真实根状态后继桥接；可使用有声明的受限 `ENGINEERING_DELAYED_SWITCH` 工程近似，但必须在固定锚定 `T_atom` 预算内，记录守卫越界和时间/状态误差范围，不能漏掉或吞并不能交换的近事件。没有足够证据返回 `STOPPED_UNRESOLVED`。不可假设旧原型已支持一般 A≠0 的完整桥接。

**C02 向前合法性：**同刻代数方程可解、模态谓词当前一致、右侧动力学可合法向前延续是不同条件。边界样例 `x'=1(x≤0), -1(x>0)` 不允许错误接受；不能证明有合法延续就拒绝或未决，不添加 Filippov 滑动、自动迟滞或假时间步。

**C03 物理状态转移：**跨模式保持电容电荷、各电感磁链（含多端口）、INT 积分状态。建立 `old local coord → common physical state → check new constraints → new local coord`。合法坐标变换需要重建完全一致；强迫理想电压源使 C 电荷无冲激跳变的冲突必须拒绝，不能直接复制降阶状态数组，也不能偷偷投影。

**附加 C04–C07：**从连续传播之前构建候选事务/回滚点；权威 event_log 保存可无损恢复物理时刻（float64+δ 不够）；`T_atom` 由最终有效 SAVE_DT 计算；REG 不存 TRIG，缓存/首次根证书随输入值和模式相关变化失效。

这七项均有配套 A01–A07 自动验收。**工程近似不是降低错误判定标准的许可证。**

## E. P2 离散事件执行机制

使用 `(t, δ)` 超密时间：δ 变化不增加物理时间。每个 δ 收集有效 TRIG 和模式变化，REG 与动态 EVENT 延时均读取**本 δ 的同一稳定旧快照**；REG 原子提交，再重算代数 SENSOR、离散 MATH/CMP/SEL/SW、检查唯一且向前有效的新模态，净 BOOL 边沿在下一 δ 生成 TRIG。后续 δ 可以读取前一 δ 新 REG。零延时 EVENT→δ+1；负延时拒绝；transport/replace/cancel 按文档规则；同刻循环和预算耗尽要安全回滚。

Runtime 唯一拥有物理时刻和事件队列；First Root Finder 只提供证据而不写提交状态；Recorder 只输出成功提交的前缀。

## F. 按 G0–G8 完整推进，不得只生成方案

- G0：实际审计 V1.0/验证源码及文档；记录哈希、可复用性；在新项目冻结 `Architecture_Decisions.md` 和测试 oracle。若合同真正自相矛盾，提供最小反例并保守停工相关模块，不要擅自升级数学框架。
- G1：实现 Markdown/固定参数/SUBCKT/SourceMap/Layout 解析与测试。
- G2：实现 13 原语 IR、类型/保持属性、SCC、连续非线性拒绝、静态合法性检查。
- G3：实现电数联合 Descriptor/PWA、SENSOR/INT/连续 MATH、状态重建和守卫模型。
- G4：实现 TimePoint/Interval/First Root 接口、C01 根接受和事件记录。
- G5：实现 REG/EVENT/离散 MATH、TRIG/δ、快照和完整事务回滚。
- G6：实现联动 Runtime，C02 右侧合法性、C03 状态相容、代数跳变重算和模态稳定。
- G7：实现 NPZ、event_log、report、CLI/C ABI、clean build、三平台可用性检查。
- G8：运行产品级 N01–N12、A01–A07、Markdown/类型全部负例、历史电域回归、LLC 标注和性能基线；形成发布候选或明确阻挡报告。

请优先形成可运行的 **最小垂直闭环**（Markdown RC + SENSOR + 连续 MATH/INT + REG/EVENT + SW + 输出），之后逐 Gate 加深功能，避免一次性写完大模块却无法编译。

## G. 正确性与报告红线

- 不使用 PLECS/ngspice/LTspice/Simulink 等作为**必需数学正确性基准**；用解析解、独立精确/高精度 oracle、模式真值表和自建最小网络。可使用 Python 仅做研究/测试辅助，不得进入正式 Core Runtime。
- N01–N12 的研究结果 11 PASS/0 FAIL/1 INCONCLUSIVE 是历史基线，**正式产品必须自己运行**；N04 切触仍不能自动记 PASS，LLC100 历史失败不能隐藏。
- 测试状态仅 `PASS/FAIL/INCONCLUSIVE/UNSUPPORTED`；执行状态与证据等级另列，不能将安全停止包装为全程完成。
- 对于每个 P0 失败，给出**最小复现 `.md`**、独立期望、实际输出、错误码、文件/行号和复现命令。
- 同一个网表改变原语文本顺序、Layout 坐标、无关命名或 EVENT 入队顺序，不得改变物理结果/同刻因果。
- 数学证明与浮点/区间数值证书各标明 scope；`LOCAL_CERTIFIED` 不等于完整工作轨迹认证；工程近似应明确显示。
- 任何日志/测试/文件若没有真的产生，标 `NOT_IMPLEMENTED/NOT_TESTED`；**绝不伪造三平台验证或子 Agent 调用结果**。

## H. 新项目最终必须交付

1. 可构建的 C++20 源码、CMake、CLI/C ABI，原生 NPZ 和 event_log。
2. `docs/` 内两份需求文档的原样备份、`Architecture_Decisions.md`、`Migration_Map.md`、`Agent_Execution_Log.md`。
3. 实际可运行的 `.md` Golden 网表与非法网表 fixtures（13 原语覆盖，示例包含 SUBCKT/REG/EVENT）。
4. 完整自动测试、可重复运行脚本、测试台账 `reports/test_ledger.json`。
5. `reports/V1.1_Implementation_Report.md`：每个 Gate 的完成度、实际测试、未决/失败原因、错误码、耗时、下一步阻挡；`release_manifest.json`：平台构建状态、依赖和大小。
6. 清晰列出与 V1.0 在**等价网表**上的准确性、正确性和性能差异；没有等价模型就不要做速度胜负宣称。

启动时可以先输出非常简短的执行检查点，但不要停在架构规划；**应直接创建新目录、实施代码并运行测试。** 遇到真正无法消除的数学矛盾/系统环境阻挡，再提交具体复现和受阻模块；其它模块继续完成。

最终汇报只说明**确实已写入新目录、构建并运行**的内容。不要把愿望清单写成已交付功能。
