# PULSE Solver V1.1 — 详细施工说明、Agent 分工与验收合同

> 版本：Implementation Plan 1.0 / 2026-10-19  
> 依赖文件：`01_PULSE_V1.1_System_Architecture.md`（同目录）。  
> 目标实施目录：`/Users/tuzki/Documents/Codex/pulse-solver-v1.1/`。  
> 本说明要求 **真实代码、构建、测试、报告**，不仅提交设计或脚手架。

## 0. 施工授权及边界

本次正式开始重构；不得修改 `/Users/tuzki/Documents/Codex/pulse-solver-v1/` 或 `/Users/tuzki/Documents/Codex/pulse_architecture/`。可以**只读**检查、复制并标注来源的已验证 C++ 实现和数据，但**不能**无审计地挪用旧 Python 0.1 Solver，也不允许将早期研究报告的 PASS 当作正式产物的通过证据。

**新工程名与新目录严格为 `pulse-solver-v1.1`**，不是 `pulse-solver-v11` 或在 V1.0 上直接覆写。若目录已存在，先列出文件及 Git 状态，确认安全后增量创建；未知文件不覆盖、不清理。所有施工产物仅写入新项目；构建文件放新项目独立 `build/`、发布包放新项目独立 `dist/`。

**实施原则：**正常模型追求正确、高效和完整；边界不支持模型采用明确工程近似/要求用户增加合理措施/安全拒绝。任何报错不得改变已提交的仿真历史。用户目标中的“不错漏首次根、不选错首根”仍是正确性红线；工程近似只能在公开声明的接受模型下执行。

## 1. 人员、模型与协作

- **主 Agent：Codex Sol，极高推理档**。作为唯一架构/代码集成负责人，独立处理数值算法、事件接受、Compiler 数学语义、难复现 Bug、最终验收。必须亲自审查并集成所有次级贡献。
- **子 Agent：Codex Sol，中等推理档**。优先承接边界清晰、可独立验收的工作：Markdown Lexer/Parser、AST/SourceMap、静态参数求值、语法 fixtures、文档与测试脚手架、NPZ/事件日志格式、跨平台构建冒烟测试。主 Agent 可安排其中任意工作，但**不得把首次根数学、换模状态、同刻事务正确性无监督地下放**。
- **资源限制：**仅申请**一个**中等推理子 Agent；不自动招募更多 Agent。是否支持子 Agent、是否支持单独指定 Medium，由当前 Codex 会话真实能力决定；不支持时主 Agent 自行执行并在报告中注明，绝不伪造委派记录。
- **文件所有权：**主 Agent 默认拥有 `compiler/continuous`、`runtime/`、`time/`、`tests/acceptance/`；子 Agent 在主 Agent 分配的独立目录内工作（例如 `netlist/`、`tests/parser/`、`output/`），不能并行改同一源文件。合并由主 Agent 统一运行集成测试。

阶段工作应当“主 Agent 处理数学难点，Medium 并行完成明确的工程边界”，但**不可让两个 Agent 对同一合同分别做互不知晓的实现**。

## 2. 技术栈、项目结构和代码复用

**必须保留**：C++20、Eigen、CMake/Ninja、CLI、C ABI、可选 Python ctypes 测试壳、原生 NPZ 写入；macOS ARM64 / Linux x64 / Windows x64 目标；正式运行不依赖 Python/NumPy/SciPy。单平台发布包预定目标 `<100MB`，若实测超出如实报告。

建议结构（先审核，必要时微调）：

```text
pulse-solver-v1.1/
├── README.md
├── CMakeLists.txt
├── cmake/
├── include/pulse/
│   ├── api/                   # C ABI / C++ facade
│   ├── netlist/               # reader, lexer, parser, ast, sourcemap
│   ├── semantics/             # parameters, subckt, types, dependency
│   ├── model/                 # 13 primitive IR, physical state, topology
│   ├── compiler/              # descriptor, modes, guards, discrete IR
│   ├── time/                  # exact-ish internal time, intervals, ordering
│   ├── runtime/               # agenda, root adapter, txn, stabilization
│   └── output/                # channels, npz, event log, report
├── src/                       # 与 include 对应
├── apps/pulse_cli/
├── tests/
│   ├── parser/               # Markdown/parameter/SUBCKT
│   ├── compiler/             # e+n matrices, primitive semantics
│   ├── events/               # REG/TRIG/EVENT and mode acceptance
│   ├── fixtures/             # *.md golden + invalid models
│   ├── regression/           # migrated legacy circuits
│   └── acceptance/           # A01...Axx and N01...N12
├── docs/
│   ├── 01_PULSE_V1.1_System_Architecture.md
│   ├── 02_PULSE_V1.1_Construction_and_Acceptance.md
│   ├── Architecture_Decisions.md
│   ├── Migration_Map.md
│   └── Agent_Execution_Log.md
├── scripts/
├── build/
├── dist/
└── reports/
    ├── V1.1_Implementation_Report.md
    ├── test_ledger.json
    ├── perf_baseline.json
    └── release_manifest.json
```

源码/测试可以据审计后实际组织，**不要在既有 C++ 中保留秘密的 D/MOS/NR/NC/NL 运行时 Kind**：必须迁移或通过真实原语展开。旧电路和相关源码只读；每次拷贝已验证算法应在 `docs/Migration_Map.md` 写明原路径、旧提交/哈希、修改内容、适用证据及新测试。

## 3. 阶段门槛与交付工件

| Gate | 施工内容 | 必交工件 | 必须通过的门槛 |
|---|---|---|---|
| G0 | 工程审计、合同落地、测试 oracle | `Architecture_Decisions.md`、历史清单、风险对照 | 旧目录只读；审计结论真实；C01/02/03 有可执行判据 |
| G1 | Markdown Reader/Parser/.PARAM/.SUBCKT/Layout | AST/IR、SourceMap、语法 fixtures | Golden E2E 解析；异常定位；不依赖元件文本顺序 |
| G2 | 13 Primitive 与数域类型、依赖/SCC | Typed Primitive IR、类型错误诊断 | 所有 13 原语正/负样例；无驱动/多驱动/非线性连续运算拒绝 |
| G3 | 电域+INT+MATH+SENSOR Descriptor/MNA | 连续模态编译器和守卫 IR | N01–N04/N11 相关用例；物理状态映射；解析解一致 |
| G4 | Event Time、Root 接口、C01 接受层 | TimePoint/Interval、certificate bridge、policy | A01 通过；非 dyadic、亚 tick、deadline 冲突安全停止 |
| G5 | REG/MATH/CMP/SEL/EVENT 超密时间内核 | agenda、delta closure、snapshot/rollback | N05/N06/N08、A04/A05；无 dirty commit |
| G6 | 电数联合 Runtime 与 C02/C03 | mode transition、forward-check、full txn | N07/N09/N10/N12、A02/A03；无错误向前模态 |
| G7 | 输出/接口/候选跨平台构建 | NPZ、event_log、JSON/MD report、CLI/C ABI | 默认全输出、时间日志无损、三平台 build smoke |
| G8 | 历史回归、正确性/性能基线、发布决定 | 最终报告、test ledger、发布候选/明确限制 | **完成 G8 之前不得宣告正式 release**；未决能力清楚标注 |

**允许 G1/G2 的语言层工作与 G3 数学原型并行**，但不能在未冻结 G0 接口时大量覆写 Runtime。任何 Gate 测试 FAIL 必须及时定位并记录，不可以通过删除测试继续发布。对于历史已经明确未完成的 LLC/N04，必须记录其为独立已知未决项，不能擅自把它们从报告删除或写 PASS。

## 4. G0：必须先审计的源、接口和工程目标

1. `pulse-solver-v1`：项目真实目录树、CMake、`model.hpp`、`runtime.cpp`、MNA、PWA 模态、事件定位、现有错误码、CLI/API、NPZ writer，保留原文件哈希与构建指纹。
2. `pulse_architecture/v1_stack_validation/`：C++ 已验证对象可否复制。
3. `pulse_architecture/numerical_domain_validation/`：N01–N12 的原始判据和 `PROPOSED_SEMANTICS.json`；不把研究 Python 直接放入 C++ 正式核心。
4. 首次根/事件分辨率研究，尤其 `event_resolution_research`、`first_root_isolation_research`，实际目录可能不同，使用只读检查确定。
5. `v1_1_event_acceptance_prototype`、`v1_1_engineering_atom_architecture_review`（若存在）：检查 C01 桥接能力与不支持范围，不能把只覆盖常向量场的成功直接推广到一般仿射/LLC。
6. 本次评审 C01–C07：逐条落实合约与最小验收，不仅在文档中复述。

输出 `Architecture_Decisions.md` 的一张表：编号、最终行为、允许工程近似条件、禁止的行为、顶层错误与子码、自动测试名称。**只有查实后才声称某旧算法可复用**。

## 5. G1：Markdown 网表与编译期参数

实施步骤：

1. 解析严格标题 `PULSE Netlist v1.1` 与唯一 Parameters/Network/Simulation/Layout 节；映射每个 `pulse` 代码块行列。
2. 词法分析数字/后缀/括号/矩阵/PWA 表/有方向端口组/续行/注释。不得执行 Markdown 中普通 prose 当数学模型。
3. `.PARAM` 仅文件开头顺序声明；表达式为四则及括号；单独设置 Runtime 参数不可在模拟期间改变。对超范围、未声明、重名、零除、非有限值给出 SourceMap。
4. `.SUBCKT` 和 `X` 展开支持多层、层级独立局部命名与稳定物理支路参考；递归调用和重名端口拒绝。**没有隐藏专用 MOS/Diode/Transformer 模型**。
5. Layout 是显示数据，与 Network 的电气连接分离；仅更换坐标不能改变 IR hash、模式矩阵和结果。
6. .TRAN/.SAVE 解析，缺省 `.SAVE` 全输出，真正为空的显式 Channels 与缺省不混淆；运行配置覆盖计算在 ParameterTable 固定之后进行。

必须留存的 fixtures：最小 RC+REG PWM、PWA R/C/L、多端口 L、V/I 受控源、SENSOR I/V、含两级 SUBCKT 的霍尔/低通、无 `.SAVE`、`.SAVE` 多通道、空 Layout、错误参数、重复标题、错类型、递归 X。

**功能禁区**：实现新语言不代表需要绘制 GUI；不允许把 `.md` 的 Layout 当权威连通性而绕开 Network。

## 6. G2：类型/组合依赖与 13 原语

- 校验每种原语有向端口数量、参数互斥、数值范围、PWA 连续性及正斜率。多端口 L 对称正定（允许数值 SPD 判定容差，必须记录），端口符号/IC 方向固定。
- 电气节点不可与 REAL/BOOL/TRIG 混接；泛型 SEL、REG 只在多种类型同样可能时要求 `REAL::/BOOL::` 标注；REG 的 TRIG 只是时钟/SET/RESET，不能作为数据值保存。
- 唯一信号驱动源；无消费者的源合法、可用于输出；无源且被消费的非外部端口拒绝。
- 连接分析采用 SCC：连续 affine/MNA 联立；REG 断开组合反馈；离散有向无环拓扑执行；不支持的组合环报错。测试将网表实例排列完全倒序、多次随机打乱，结果不变。
- MATH 文法转换为标准 AST，确认 `{K}*X` 合法而 `X*Y` 的连续使用非法，`MUL` 两保持输入合法；运行时离散函数输入不满足定义域则错误回滚。
- `SENSOR I` 有且只有确定支路/端口参考才能编译；例如 `SENSOR1 IP I LCOUP PORT=1`，禁止凭任意导线名称猜电流。

## 7. G3：Descriptor/MNA、模式与状态表示

### 7.1 连续装配

- `R`/PWA R 是局部仿射导电段；`C` 按 Q(V) 建立电荷状态；`L` 按 Φ(I) 建立磁链状态，多端口 L 采用 SPD 互感矩阵；V/I 受控源与 SENSOR 直接作为代数方程/观测。
- MATH 连续仿射和 INT 与电域共同装配为一个矩阵，不按元件文本先后逐条执行。
- 构建固定模式的 `Descriptor + output_map + guards + physical_state_map`。合法的约束子空间可以降阶；不能从原始代数块奇异直接推出“不可解”。对不在支持约束类内的 DAE 报 UNSUPPORTED_MODEL/MODEL_SINGULAR，不靠无声正则化。
- 模式可按需编译/缓存；缓存键绑定模型、有效逻辑/模式、保持参数化签名，更新数值部分/守卫证书时精确失效。

### 7.2 C03 状态转换必须作为显式接口

```text
PhysicalState old = reconstruct(old_mode, z_old)
PhysicalState same = preserve(q, phi, eta)
if !satisfies_new_constraints(same, new_mode):
    reject INCONSISTENT_MODE_TRANSITION
z_new = reduce(new_mode, same)
if !equivalent(reconstruct(new_mode,z_new), same): reject
```

合法正例：两套局部坐标一套 `q=z_old`、另一套 `q=2*z_new`，`q=1` 时新坐标必须为 `0.5` 而非 `1`。非法正例：理想受控电压源并联带初始电荷的 C，源阶跃强迫不连续电荷，不支持冲激时拒绝，事件和状态不能半提交。

## 8. G4：事件接受时刻桥接（C01，最高风险施工点）

### 8.1 函数职责

建议接口：

```cpp
struct RootCandidate { /* mode_id; guard_id; interval; direction; first_certificate; scope */ };
struct TimeOrder { /* BEFORE, EQUAL, AFTER, UNRESOLVED */ };
struct AcceptResult { /* accepted_time, state_kind, state, next_mode, error_scope, policy */ };
AcceptResult accept_next_event(const RunState&, const RootCandidate&, const AgendaView&, const AcceptancePolicy&);
```

先正确比较根证书、定时 deadline、结束时刻；再计算**实际接受时刻 Ta**、对应状态和近似范围。**证书给出顺序 ≠ 给出事件根点的物理状态**。不允许 `float64(l+u)/2` 偷换根、不允许先把两不同时刻转为 float64 后比较。根证书要绑定编译模式/入口/队列版本。

### 8.2 策略与拒绝条件

优先在支持范围内从真实根处重建后继模式并桥接至检查点；无法认证时可以采用公开标记的 `ENGINEERING_DELAYED_SWITCH`（受控延迟换模的**近似模型**）。必须：

- `Ta >= upper_bound(root_interval)` 且 `Ta - lower_bound <= T_atom`；窗口一次锚定、不能连锁扩大。
- FIRST/DIRECTION/所有可能更早事件与数字 deadline 顺序具有相应证据。
- 近似局部越界和状态误差预算明确计算或保守界定；不能把 `T_atom` 本身冒充状态误差上界。
- 固定物理储能状态、后继约束相容、右侧有效性必须通过；不知道是否有桥接区间内独立事件/短控制脉冲会受影响，拒绝或未决。
- 输出 EventAcceptance 证据字段：根区间、Ta、旧/新模型版本、候选集合、工程近似类型、最大时间延迟、守卫残差、已知局部误差范围、是否未决。

**禁止“为了提高完成率”无条件补大容差、删除守卫、吞掉窄脉冲。** 如果一般 A≠0 模型的根状态/后继桥接没有足够实现能力，局部返回未决；不得拿简化原型的 A=0 性质冒充通用结果。

### 8.3 时间和独立事件日志

- 继续使用 `Q_repr=2^-64 s`、全局+局部高精度 Time API，并保留源十进制期限及其实际有效表示。
- 若两个事件在内部实际上时刻不同，即使 `float64 seconds` 一样，事件日志也必须可无损重建其先后；否则拒绝不能证明的操作。
- 测 `t1=1s`、`t2=1+2^-60s`：内部与 event_log 往返有序且不同；此差异不能靠仅增加 `δ` 实现。
- 改变 `SAVE_DT` API override 后必须用最终有效值重新计算 `T_atom`、时间表/调度版本、缓存失效和输出元数据；不能保留 `.md` 旧 T_atom。

## 9. G5：离散 EVENT、REG、超密事务

### 9.1 必须支持的语义

1. 当前物理时刻候选事务统一持有 old committed state；每个 δ 从已稳定快照读取。
2. 同 δ REG（包括不同 EVENT 触发）全部读旧值、一起更新。
3. 同 δ EVENT 锁存动态 TON；零延时送 δ+1；同端口同 δ 重复 TRIG 合并，跨端口保持区分。
4. EDGE 基于稳定前/稳定后的 BOOL **净变化**生成下一 δ 的 TRIG，不对组合中间毛刺输出。
5. `transport` 保留 pending；`replace` 作世代替换；同 δ cancel 优先于新安排，到期已经进入本批的 TRIG 不撤回。
6. 本地负延时、DIV/LOG/SQRT 等运算域错误，必须使整个当前物理事务失败并回滚。
7. 完整逻辑/agenda 配置重复时可证明循环；微步骤预算耗尽但不重复只报告预算停止，不误称数学无解。
8. REG/BOOL/Agenda 变化必须使依赖的代数 SENSOR/CMP/SEL、事件证书及模式映射重新求值或失效。

### 9.2 回滚测试与持久化前缀

事务开始前须有 `S_committed`（时间、共同物理状态、降阶坐标、代数量、REG、BOOL、有效 agenda、版本/证书与输出前缀）。计算永远在 `S_candidate`，从传播起就如此；失败时直接丢弃。容许保留最后**已提交的有效前缀**供诊断，但必须伴随 `STOPPED_*` 状态和前缀终点，不能当完整结果。

故障注入点至少：传播到候选时刻后、REG 全部写入后、EVENT 取消/入队后、模式编译/换模后、NPZ 输出准备前；一一检查 no dirty commit。

## 10. G6：电数域 Runtime 的完整主循环

```text
validate_input_and_initial_physical_state()
compile_mode_and_initial_guards()
initialize_agenda_and_initial_delta_batch()
stabilize_initial_state_or_stop()
commit_initial_state_if_accepted()

while committed_time < effective_T_END:
    root = certified_first_root(current_mode, entry, guards)
    digital = agenda.earliest_pending()
    next = certified_compare(root, digital, end)
    if next cannot be ordered: STOPPED_UNRESOLVED

    candidate = copy_on_write(committed_state)
    candidate = propagate_or_bridge_candidate(candidate, next)
    if !C01_accepted_time_and_state: STOPPED_UNRESOLVED
    candidate.physical = reconstruct_and_preserve(candidate)
    if !C03_new_constraints_compatible: STOPPED_ERROR

    for δ in superdense_steps_at_candidate_time:
        snap = stabilized_delta_snapshot(candidate)
        batch = collect_triggers(snap, next, agenda)
        next_regs = evaluate_all_regs_from_one_snapshot(batch, snap)
        next_delays = latch_all_delays_from_one_snapshot(batch, snap)
        apply_updates_atomically(candidate, next_regs, next_delays)
        recompute_algebraic_and_discrete_combinational(candidate)
        if !mode_consistent: STOPPED_ERROR_OR_UNRESOLVED
        if !C02_forward_admissible: STOPPED_ERROR_OR_UNRESOLVED
        emit_net_bool_edges_for_next_delta()
        if cycle_detected: STOPPED_ERROR
        if microstep_budget: STOPPED_UNRESOLVED

    invalidate_root_and_numeric_caches_by_dependency()
    atomic_commit(candidate, event_records, output_prefix)

emit_final_outputs_and_status()
```

重要：**序列化时间、传播到候选状态、mode stable、right-side admissibility 与 state mapping 是五个不同检查**，不能合并成一个 Boolean 且不记录失败原因。对保存网格上的观测，事件时刻选已提交的 `t+`，REG 的采样仍按它自己的 δ 快照。

## 11. G7：输出、公开接口与发布候选

### 11.1 旧输出合同

`out.pewave.npz`（`time float64`、`analog float32`、`digital uint8`、`metadata_json`）；`simulation_report.json`；`simulation_report.md`。事件日志 `event_log.jsonl` 使用内部无损时间序列化字段及展示用 float64，包含 `(t,δ)`、事件源与 ID、守卫根区间、Ta、模式版本、接受 policy、证据等级、事务 ID。运行时绝不由导出 analog float32 回填内部高精度物理状态。

`Channels` 未指定就遍历有效展开实例的全部节点电压、可唯一求的有向支路电流、REAL/BOOL/REG/INT 及 TRIG 记录；显式选择则过滤已定义通道。过大输出需预先估算并警告/拒绝，不能静默丢失。别名相同通道按稳定路径映射，报告完整 registry。

### 11.2 公开错误与状态

保留旧规划顶层错误码集合，不可任意重排 C ABI 数值：

```text
INVALID_NETLIST / UNSUPPORTED_MODEL / INCONSISTENT_INITIAL_STATE /
INVALID_PWA_CURVE / PWA_OUT_OF_RANGE / MODEL_SINGULAR /
NUMERICAL_ERROR / EVENT_ROOT_FAILURE / MODE_STABILIZATION_FAILURE /
PHYSICAL_CONSTRAINT_VIOLATION / OUTPUT_ERROR / INTERNAL_ERROR
```

新增子码示例 `TIME_RESOLUTION_UNRESOLVED`、`NO_FORWARD_ADMISSIBLE_MODE`、`INCONSISTENT_MODE_TRANSITION`、`MULTIPLE_STABLE_MODES`、`MICROSTEP_BUDGET`、`ZERO_TIME_CYCLE`、`CONTINUOUS_NONAFFINE`、`COMBINATIONAL_CYCLE`、`INITIAL_CMP_BOUNDARY_UNRESOLVED`。运行结果状态应明确区分 `COMPLETED`、`STOPPED_ERROR`、`STOPPED_UNRESOLVED`；证据级别独立：`LOCAL_CERTIFIED/NUMERICAL/ENGINEERING_APPROXIMATION/NOT_CERTIFIED`，不能“安全未决也算完成”。

### 11.3 发行

三平台构建：macOS ARM64、Linux x64、Windows x64，CLI 独立运行；C ABI 与 ctypes 绑定检验；CMake/Ninja clean build；原生 NPZ。**G7 仅产生 release candidate**，正式发布必须等 G8 结论；未在当前机器可执行的其他平台必须明确标为 NOT_TESTED，而不是声称已通过。

### 11.4 API 边界与稳定版本

必须导出清晰版本号与句柄生命周期：

```text
pulse_abi_version() -> version
pulse_compile_markdown(bytes, len, options) -> model_handle | error
pulse_simulate(model_handle, run_options, result_destination) -> run_status
pulse_get_last_error(handle) -> structured diagnostic
pulse_release_model(model_handle)
```

以上只是**函数语义签名**，不强制具体 C symbol/ABI 结构体字段；实际命名和版本布局应先检查 V1.0 已公开的 C ABI，再通过独立头文件冻结。C ABI 不直接暴露 Eigen/C++ STL 对象或引用已释放内存。编译结果可复用，但每次 Runtime 创建独立状态、agenda、输出和证书版本。`effective_T_END/effective_SAVE_DT/Channels` 属于 run options，修改保存密度后重新实例化 Time/Agenda，不能让先前 compile cache 的 T_atom 继续生效。

## 12. G8：必须运行的回归和独立验收

### 12.1 数域 N01–N12 产品化

| ID | 目标 | 正确 oracle / 必须观察 |
|---|---|---|
| N01 | INT 单状态 | 闭式解、IC、长时传播 |
| N02 | 2+ INT/连续 MATH/电域联合 | 闭式解，证明确实联合模态编译；乱序不变 |
| N03 | CMP 有向首次根 | 独立首次时刻，正确 guard/方向/SEL 结果 |
| N04 | 多根/切触 | 正常上/下穿 PASS；切触不能认证则 INCONCLUSIVE+STOP，不能虚报 PASS |
| N05 | 周期 REG | 采样值、保持、初态、TRIG 类型非法拒绝 |
| N06 | 双 REG 原子更新 | Q2 读取 Q1 旧值，全排列相同 |
| N07 | 离散 MUL→SW | 样值 P 只在事件更新，电域分段闭式一致 |
| N08 | 动态 EVENT | 锁存/replace/transport/cancel/零/负延时/异常回滚 |
| N09 | 连续根和 CLK 同刻 | 正确先后/快照/δ1 边沿 |
| N10 | SW 跳变代数 SENSOR→CMP | 不靠旧模态连续根捕获边沿，δ 链正确 |
| N11 | 独立混合反馈 | 唯一/无/多模态分类，合法奇异 Descriptor 案例 |
| N12 | 即时链/循环/极近因果 | 不无限循环、不盲并、不 dirty commit、不能排序则未决 |

### 12.2 新增 C01–C07 强制回归

| ID | 场景 | 预期 |
|---|---|---|
| A01a | `x'=3` 阈值 1 后改 `x'=1`，根=1/3，Ta=ceil tick | root_interval/Ta/accepted_state/误差语义分离；对工程后备按明示模型 oracle，而非假装精确 |
| A01b | 根恰在整数 Q tick | 无多余漂移；事件记录精确一致 |
| A01c | 根早于、晚于、恰等于 deadline/T_END，区间重叠 | 证明排序才执行，不确定则安全未决 |
| A01d | 固定锚定窗口内多根/短数字脉冲 | 不链式吞并；不可交换因果绝不直接合并 |
| A02a | `x'=+1(x≤0), -1(x>0)` | 到边界安全拒绝/未决；绝不宣称成功向前 |
| A02b | 正常一次穿越、纯切触、零值平台、可证明高阶穿越 | 按 CMP 表明确处理；能力不足不冒充认证 |
| A03a | `q=z_old=2*z_new`，q=1 | 得 z_new=0.5，重建 q 不变 |
| A03b | C 初值 0 并联理想受控 V 源强制跳到 1V | 不允许电荷跳变；相容性失败、事务零提交 |
| A03c | PWA C/L 折点前后换段 | 检查 Q/Φ 的**截距与斜率**，物理状态连续 |
| A04 | 传播后/REG 后/queue 后/重编译后故障注入 | 回滚后时间/物理状态/队列/证据与此前一致 |
| A05 | `1s` 与 `1+2^-60s`，显示 float64 相同 | event_log 往返仍不同且有序；不得以 δ 替代时间精度 |
| A06 | md、CLI、API 配置相同；改变 SAVE_DT 覆盖 | 一致有效值/T_atom/元数据与实际行为；缓存正确失效 |
| A07 | REG 尝试存 TRIG；保持量变化缓存检查 | 类型拒绝；数值映射/守卫/根证书按依赖失效 |

### 12.3 Parser/Compiler/旧电域回归

| 组 | 用例 |
|---|---|
| Pxx | 四区块/缺失/重复、参数四则、后缀、未知名、表达式函数非法、SourceMap |
| Pxx | SUBCKT 递归拒绝/作用域隔离/两实例同内部名、布局改变不影响数学 |
| Pxx | 所有 13 原语至少一正一负、PWA 斜率/连续性、SPD、IC 默认/矛盾 |
| Pxx | SENSOR 电流方向/层级引用、REAL/BOOL/TRIG 推断、SEL/REG 歧义 |
| Pxx | 没有 SAVE 全输出、指定部分输出、TRIG 日志、事件同刻 t+ 输出 |
| Legacy | Buck/Boost、两类 DCM、BuckLong、CE01/CE02、自建 LLC，按实际模型等价逐项迁移；缺失能力和旧异常必须列出 |
| Legacy LLC | 100 周期目前历史未过，重测并明确 PASS/FAIL/INCONCLUSIVE/STOPPED_UNRESOLVED；不把不崩溃当 PASS |

测试基准以解析解、独立有理数/高精度 oracle、精确真值表、守卫约束为主；研究/正确性验收不借助 PLECS、ngspice 等作为必需的数学 oracle。允许辅助数值对照，但不能替代数学判据。证据分类固定 `PASS / FAIL / INCONCLUSIVE / UNSUPPORTED`；失败保留最小反例、环境和复现命令。

### 12.4 性能回归（正确后才计时）

至少记录：Parser/Compiler 耗时、模态编译缓存、矩阵指数次数、Guard 根查询/认证失败、δ 微步骤、队列规模、事务回滚、模拟物理时长、输出大小、各平台二进制体积。与 V1.0 比较必须同模型/同初值/同输出/同正确性边界；不同模型的时间比较注明不公平，不能宣称“比 PLECS 快多少”。

## 13. 错误处置、用户提示及“允许工程近似”的界限

| 问题 | Solver 动作 | 面向用户的建议 |
|---|---|---|
| C01 无法证明首次根/接受状态/因果次序 | `STOPPED_UNRESOLVED`，定位守卫/根区间/时间版本 | 缩小工程窗口、调整精度；不能修改模型宣称精确 |
| C02 无合法后继或边界抖动 | 拒绝/未决，不加入私有滑模 | 添加迟滞、比较器延时或有限带宽 |
| C03 新源约束与电荷/磁链冲突 | 明确 `INCONSISTENT_MODE_TRANSITION`，不投影 | 加入合理 Ron/ESR/ESL/有限电阻等 |
| 多模态 0/2 解或不唯一 | `NO_STABLE_MODE/MULTIPLE_STABLE_MODES` | 修正逻辑环、加入物理动态或迟滞 |
| EVENT 无限同刻递归 | 循环或预算子码；回滚 | 修改控制器的零延时反馈 |
| PWA 曲线越界 | 按 RANGE=ERROR/EXTEND | 提供足够表范围或显式外推 |
| 非法连续 MATH | 编译拒绝 | 通过 REG 采样后离散计算或以 PWA 组合表达 |
| 输出太大 | 预警或 OUTPUT_ERROR，不静默丢失 | 指定 `.SAVE` 通道 |

“工程近似完成”在报告中必须明确标注 `ENGINEERING_APPROXIMATION` 和有效预算、工作模型版本、Ta；不能伪装成“整个原模型轨迹经数学认证”。

## 14. 正式验收定义与最终交付

**可发布候选 Gate**：代码能真实 clean build；13 原语和合法网表有执行路径；P0 的 A01/A02/A03/A04/A05/A06/A07 在受支持场景通过；N01–N12 可重跑；所有失败及未决均未被抹除；三平台实际测试状态透明；性能和输出合同不缺失；无正式运行 Python 依赖。

**发布仍有限制**：若历史 LLC 100 周期与 N04 切触未完成，应以“不支持/可安全停止的明确范围”呈现，不能宣称普遍认证。若关键常见电路因新拒绝策略大面积无法完成，应作为发布阻挡的产品可用性问题报告，不得仅依靠测试“安全停止”掩饰。

主 Agent 最终交付：

1. `README.md`：完整构建/运行/示例与平台限定；
2. `docs/Architecture_Decisions.md`：每条合同裁决、错误路径和验收；
3. 正式 C++20 源码、测试、合法/非法 Markdown fixtures、构建系统、CLI 和 ABI；
4. `reports/V1.1_Implementation_Report.md`：阶段 G0–G8 完成情况、测试总表、主要设计取舍、未决项、复现命令、性能；
5. `reports/test_ledger.json`：每项用例的运行时实测状态、oracle、容差与证据；
6. `reports/release_manifest.json`：已构建/未测试平台、体积、运行依赖、二进制哈希；
7. `docs/Agent_Execution_Log.md`：主/中等 Agent 的分工、文件所有权、合并与检验事实，子 Agent 不可用必须如实记录。

**重要限制：**阶段性失败不应导致主 Agent 为了“交付完整”谎称已经完成整个 V1.1。工程未能完工时必须保留可运行的最小闭环与准确 Gate 状态，给出下一个阻挡项和最小复现，而不是提交只有规划的仓库。
