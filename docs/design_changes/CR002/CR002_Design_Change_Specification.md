# PULSE Solver V1.1 — CR-002 通用事件求解流程局部重构任务书

> **版本**：Design Change Specification Draft 1.1 / 2026-10-20  
> **状态**：待用户审批的设计变更草案；不是已完成的实现或数学认证  
> **工程对象**：`/Users/tuzki/Documents/Codex/pulse-solver-v1.1/`  
> **施工基线**：CR-001 回退完成后的 **Stage 1 Production Bug Fix + Runtime Root-Coordinate Scaling Fix**  
> **变更焦点**：面向**任意受支持电路**的 First Event → Candidate Cluster → Joint Mode Reclassification → Event Acceptance  
> **特别补充**：功率二极管/MOS 的测试模型必须包含**显式 pF 级寄生电容**；不得通过 Solver 隐式插入元件。

## 0. 范围、授权与验收底线

本次是**通用求解流程的部分算法重构**，**不是 LLC 专项修复**、不是新建 Solver、不是重新定义整个器件库。LLC 只属于系统级回归/压力测试，不允许作为通用实现的名称依赖、硬编码或先决条件。

设计依据：

1. `PULSE_Solver_V1.1_Architecture_Review_2026-10-18.md`：工程原子时间、阈值轮询、右侧导数引导联合模态重判、严格事件类与工程近邻簇的区分；该文件是设计评审稿，并非所有数学条件均已验收。
2. `PULSE_V1_1_Engineering_Atom_Architecture_Review_Feedback.md`：指出近阈值提前选段的本构语义、器件模型、事件因果和误差预算尚待闭合，并提供反例。
3. 2026-10-19 正式三文件 `01_PULSE_V1.1_System_Architecture.md`、`02_PULSE_V1.1_Construction_and_Acceptance.md`、`03_Codex_Sol_ExtraHigh_With_Medium_Agent_Prompt.md`：沿用已实现的数学内核、物理状态、数域、时间与事务机制；纠正其过早终止候选事件路径的实施偏差。
4. CR-001 Phase A–D：仅作为**已保存的研究经验和反例**，不是本次允许直接并入生产代码的实现基线。

**前置关卡**：Agent 必须先核实 CR-001 回退报告、源码 SHA256、clean build、原有 124 项验收与 8/8 CTest、五个恢复电路和 CE01/CE02 的实际结果。若无法确认基线，停止修改正式源码；不以文件名猜测版本。

**正确性底线**：不能漏检必须保留的更早独立事件，不能误认后根为首根；不能按时间接近直接宣称严格同时；不能隐式改变 PWM/REG/EVENT 的因果；不能通过放宽容差、删除守卫、改变错误码语义或脏提交来制造完成状态。允许在经批准、明示范围内对**自主分段事件**采用工程近似，并诚实标注近似模型及误差。

## 1. 当前问题与目标行为

### 1.1 需要纠正的接口缺口

目前首次根排序未决可能在 `ROOT_ORDER_UNRESOLVED_NOT_PROVEN_SIMULTANEOUS` 直接停止，候选集合没有机会完成联合模态重判。`UNRESOLVED` 作为安全后备依旧有效，但不能**仅因簇内根区间重叠**就禁止所有有条件的工程候选路径。

### 1.2 目标流程

```text
Compiled Mode (Descriptor/MNA, physical-state map)
             ↓
Matrix-exponential propagation & first-event isolation
             ↓
Single event / proved ExactEventClass / engineering-near candidates
             ↓
Proof of earliest relevant cluster and compatible agenda/deadline
             ↓
Bounded Candidate Discovery (all autonomous PWA guards)
             ↓
Joint Mode Reclassification (one full network model per candidate)
             ↓
Algebraic + constitutive + right-side + q/φ/η + causality checks
             ↓
Exact or approved engineering acceptance at Ta
             ↓
Atomic commit; invalidate mode/root caches; continue first-root search
             └─ insufficient proof/budget → refine or STOPPED_UNRESOLVED
```

正常单事件路径应沿用已有快速实现，不能默认进入复杂的多模态组合搜索。

### 1.3 统一适用范围

- 自主分段：PWA R、C、L（含组合的二极管等）；比较器的连续守卫与有向穿越；未来其他经现有 Primitive IR 合法展开的 PWA 组合。
- 强制事件：PWM、开关控制、REG、EVENT、到期 deadline；**保持既有调度/超密时间协议**，不是可随意压缩为自主簇的成员。
- 无器件名、拓扑名、二极管数量、LLC 特征频率、已知网表 ID 的专用判断。

## 2. 功率器件寄生电容：强制网表建模要求（新增 P0）

### 2.1 建模原则

**在 PULSE 的工程电路仿真与相应测试网表里，二极管和 MOS 都应有明确的寄生电容。** 这一条是器件组合模型及**测试网表**的要求，不允许 Solver 在运行时看到 `SW` 或“二极管名称”就悄悄新增隐藏电容。现有 13 原语不变，按原子器件/`.SUBCKT` 显式展开。

| 器件 | 必须具备的最小寄生项 | 连接原则 | 可选扩展 |
|---|---|---|---|
| 二极管（PWA 导电支路组合件） | 正的结电容 `Cj` | **并联于阳极—阴极**，与导电支路共端口 | `Cj(V)` 若由受支持的连续 PWA NC 表达；真实模型按器件资料优化 |
| MOS/GaN 等功率受控开关组合件 | 正的输出/漏源电容 `Cds` 或等效 `Coss` 路径 | **并联于 D—S 功率端**，独立于门极控制的 ON/OFF | 如模型具有真实 G 节点，可显式建 `Cgs`/`Cgd`，但不可因只有 BOOL 门控而伪造模拟 G 节点 |

- 二极管的 `Cj` 与 MOS 的 `Cds/Coss` **均为物理电容元件**，对应连续电荷状态；不能靠纯数值时间延迟、守卫阈值调大、软开关标志取代。
- 如果用户器件组合件或网表已经包含相应等效寄生电容（包括等效电荷模型），**不得重复添加**；必须识别实际端口和等效关系，避免双重计数。`Coss` 可能包括 `Cds+Cgd` 在特定连接条件下的等效，不可无条件双算。
- MOS 的 Ron/Roff、有损元件与现有受控开关语义保留；寄生电容不能取代有限导通/关断电阻。二极管的导电支路分段与 `Cj` 是不同关系，守卫应根据适当的本构/导电变量定义，不能把总端口电流误用为纯导电电流。
- **不能把“增加 pF 电容”解释成强制切换的瞬态值总是连续**：必须遵守实际 q/φ 状态保存及 Descriptor 一致性；含其他理想约束的网表仍可能不相容。

### 2.2 无寄生项时的测试网表修订

审核本次 CR-002 使用的**所有电力电子拓扑测试网表**（含合成事件电路、Buck/Boost/DCM/多开关/谐振回归）。凡出现代表真实 MOS 或二极管的开关/导电支路，但没有对应寄生电容，**在该网表中显式增设一个 pF 量级电容**：

- 基准值可用 **`1 pF`**（即 `1e-12 F`），也可根据拓扑及期望尺度选择 `2.2 pF`、`5 pF`、`10 pF` 等；**具体取值必须作为网表参数公开，不能偷偷改变**。
- 多个器件实例各自具备对应电容；不得只在母线放一个大电容就视为各开关均有寄生电容。
- 对 MOS 模拟开关：在电气功率 D—S 端并联电容。对二极管：在 A—K 端并联结电容。确认子电路多次实例化时每实例电容正确生效。
- 已经具备正确并联 `Cj`/`Cds` 的模型不重复添加。电容在其他位置（例如输入滤波电容）不算该开关器件的寄生电容。
- 如果有**专门为了测试单一原子语义的非物理单元 fixture**，必须标注 `ATOMIC_SEMANTICS_ONLY`，单列而不得用于电力电子产品功能/性能/工程近邻接受的正向证明。对应物理电路回归仍必须提供含寄生项的版本，不能借此大面积豁免。

**示意（非新语法合同，按真实 `.md` Netlist 语法实现）：**

```text
* 某功率开关及其明确的输出寄生
SW_M1 D S CTRL ...
C_M1_DS D S 1p

* 某二极管的 PWA 导电组合支路及其结电容
X_D1 A K DIODE_PWA ...
C_D1_J A K 1p
```

> 以上仅示意端口关系，不能在未确认 parser 语法前原样当作可执行网表。若 `X_D1` 官方子电路已包含 `Cj`，**不要**再从外部加 `C_D1_J`。

### 2.3 变更影响与基线公平性

新增 pF 电容会增加储能状态、改变微秒/纳秒尺度响应、局部模态矩阵和刚性、根时刻甚至事件数量。**不能再把修改前后电路视为同一数学模型。**

1. 先只读审计测试网表并保留原始原文件、哈希、参考基线；
2. 生成修改清单：每个开关实例 `device_id / A-K or D-S / original_cap / new_cap / value / reason / model_hash`；
3. 按确认的 fixture 范围修改/复制网表，更新独立的解析/高精度 oracle；
4. 原来的 124 项验收和八个 CTest 作为**回退后代码**基线应原样跑通；如测试网表因寄生电容要求而实质改变，必须另列**新模型结果**，不能用物理模型不同造成的差异冒充算法回归，也不能删除原测试来掩盖变化；
5. 在新正向事件接受测试里，**禁止用完全没有二极管/MOS 寄生电容的理想化开关电路替代目标电力电子模型**。

### 2.4 接受条件

- `CAP-01`：二极管无 `Cj` 的拓扑测试网表能被审计发现，并明确补 `1pF` 或有据的 pF 数值；
- `CAP-02`：MOS 组合件无 `Cds/Coss` 的拓扑测试网表能被发现并显式补足；
- `CAP-03`：寄生项已有时不重复注入；
- `CAP-04`：子电路两个实例各具电容，不被错误共用状态；
- `CAP-05`：电荷初值及新模式切换前后连续性正确；
- `CAP-06`：求解结果随 1 pF / 10 pF 改变按同模型 reference 验证；
- `CAP-07`：对无寄生的纯原子/语法 fixture 的标注及测试适用范围真实完整；
- `CAP-08`：无 Solver 隐式添加 C 的行为、无双算 `Coss/Cj`。

## 3. First Event 与候选移交：通用数学接口

定义内部证据对象（建议名称，并非强制 ABI）：

```cpp
struct EventWitness {
    ModeId mode_id;
    Version entry_version, agenda_version;
    GuardId guard_id;
    TimeInterval first_root_bracket;
    Direction direction;
    ProofScope earliest_and_direction;
};
struct ExactEventClass {
    std::vector<GuardId> members;
    EquivalenceCertificate compiler_bound_certificate;
};
struct EngineeringCandidateCluster {
    TimeInterval earliest_anchor;
    TimePoint window_end;          // anchor + effective T_atom, no chaining
    std::vector<EventWitness> candidates;
    ExclusionEvidence excluded_guards;
    AgendaConflictEvidence agenda;
    ProofScope candidate_completeness;
};
```

`RootFinder` 负责按现有安全合同找到每个相关守卫的有向**首次**有效根，并提供足以排除候选簇之前独立事件的证据；簇内严格排序不是工程移交的前置条件。

任何 `UNKNOWN` 的守卫排除证据必须保留为需精化/候选，不能因一次一阶筛选为远离而认定 `PROVEN_EXCLUDED`。对于被证明严格共同的守卫，使用绑定实际工作模型和可达空间的 `ExactEventClass` 完整处理；**根接近不足以授予严格共同证书**。

可信事件状态须绑定同一工作模型、根括区和传播误差界。不能用 `float64` 根中点、旧提交状态或异常传播后的静默回退伪装为根状态。

## 4. Joint Mode Reclassification：正常路径不得全模式穷举

1. 固定当前真正发生的强制控制变化，未来 PWM/deadline 不得被提前执行；
2. 利用候选守卫/阈值邻域，对**全部自主 PWA 元件**做快速扫描与有界排除；
3. 候选**不等于**实际要切换的元件；
4. 生成完整候选赋值，**联合**按需编译 MNA/PWA 新模态；
5. 在相同可信物理 q/φ/η 状态上验证代数可解、模型本构、模式谓词、右侧导数/必要高阶或短区间条件、新约束一致、向前动态、数域因果；
6. 以约束传播/局部受影响子图和右侧重判为正常算法。仅有限歧义候选且预算允许时做局部组合；**不得默认用 `2^k` 枚举电路所有开关**；
7. 无/多后继及数值证据不足时，按原因分类重试、精化或保留 `STOPPED_UNRESOLVED`，不能任选首个收敛模式；
8. 必须明确 `CompileSuccess != ModeConsistent != ForwardAdmissible != PhysicalMapVerified != AcceptanceCertified`。

**物理状态**：电容电荷 `q`、电感磁链 `φ`（含互感）、INT 状态 `η` 在普通换模前后不允许冲量跳变；应验证 `old mode local → physical state → new mode local` 的双向映射和约束，不能把只传入相同 `Vector` 当作映射证明。

## 5. 事件接受：精确语义与工程近似语义分离

| 接受路径 | 先决条件 | 记录等级 |
|---|---|---|
| 严格单事件 / `ExactEventClass` | 首次根、模型身份、真实根状态/局部桥接、后继合法、事务完整性有证据 | 对实际完成的局部证明标 `LOCAL_CERTIFIED` |
| `EngineeringCandidateCluster` | 无簇外更早相关事件、固定 T_atom 预算、工程近似模型/时间规则已批准、联合合法后继、局部误差及因果检查 | `ENGINEERING_APPROXIMATION`，不声称严格同时 |
| 任一路径能力不足 | 证据不完整、不可交换控制事件、无法验证后继或超预算 | refine 或 `STOPPED_UNRESOLVED`，历史不脏提交 |

### 5.1 固定的工程时间合同

`T_atom = effective_SAVE_DT × 10^{-ATOM_ORDER}`，`ATOM_ORDER` 默认 9；独立于内部时间表示 `Q_repr`。工程簇一旦锚定，不滚动延长。所有时间加法用本地高精度坐标加全局 `TimePoint`，不能用导出 `float64 seconds` 比较近邻根。

### 5.2 工程切换模型：本次**必须在 Gate 1 冻结**

考虑优先方案 `CLUSTER_DELAYED_APPROX`：选择满足可表示和因果约束的尽可能早的共同检查点 `Ta`，将实际选中的自主分段在 `Ta` 接受；`Ta` 不早于相关根可信上界，且 `Ta - earliest_lower ≤ T_atom`。需要额外明示：延迟期间旧模式如何作为**近似工作模型**使用、分段越界如何限制、事件再次相遇如何处理、不可交换事件如何防止被吞并。

对照研究 `CLUSTER_EARLY_APPROX` 和根处桥接，但**不得由 Agent 自行选择产品默认策略**。若原合同无法成立，应提交最小数学反例、条件或替代方案供用户批准；未批准时允许开发只读接口/隔离原型，不得更改生产默认接受语义。

### 5.3 工程误差及证据范围

必须区分：求根/传播的数值不确定度、时间偏移、工程模型引起的 q/φ/η 与能量变化；在需要时给出可计算局部界或明示的局部启发式/实验界，不能把 `T_atom` 单独当作能量/状态误差认证。

数值/物理日志至少包括 `model_id`, `work_model_id`, `policy_id`, `root_brackets`, `anchor`, `Ta`, `T_atom_effective`, `exact_members`, `candidate_members`, `actual_switched`, `numeric_scope`, `physical_map`, `constitutive_relaxation`, `time_error`, `state_error_scope`, `energy_error_scope`, `agenda_conflicts`, `acceptance_status`。

### 5.4 数域因果约束

两段不同物理时间不能依靠 `(t,δ)` 伪装同时。PWM、REG、EVENT、CMP EDGE、transport/replace/cancel、短数字脉冲的顺序必须保留；默认工程近似**只考虑明确授权的自主分段**。若候选换模可能使脉冲、采样值或数字边沿改变，必须采用有证据的保留/桥接方案，否则未决。

## 6. 分阶段实施：每阶段要有客观 Gate

| Gate | 目标 | 必须交付与停止条件 |
|---|---|---|
| **G0 回退基线确认** | 只读审计 CR-001 回退后的 Stage1+Scaling Fix | 基线哈希、clean build、124 acceptance、8/8 CTest、五电路/CE；失败不得触碰生产源码 |
| **G1 通用算法与近似语义评审** | 定义所有守卫、事件、状态、近似/因果接口和 PWA 寄生模型审计 | `Generic_Event_Design.md`、`Pending_Decisions.md`、最小反例；用户批准后才允许启用默认工程接受 |
| **G2 通用独立原型** | 构造与 LLC 无关的多事件混合 PWA 电路；必须包含实际二极管/MOS 的 pF 寄生 | 至少一个**真实不同近根**正例可以接受到 T_END；拒绝用例准确；独立 oracle；原型可单独运行 |
| **G3 局部正式代码集成** | 增量接入首次根移交、候选发现、联合模态重判、经批准的接受路径 | 生产默认正常单事件不退化；若 G1 尚未批准仅实现非默认内部路径与测试 |
| **G4 通用产品验收** | 覆盖多器件/不同模式/因果/错漏事件；检查电容真实参与状态 | GEC+CAP 全部运行并如实记录 PASS/FAIL/INCONCLUSIVE；至少一个生产 Runtime 非 LLC 完整近根正例（经批准行为） |
| **G5 历史拓扑、LLC、性能** | 迁移含寄生的真实网表、比较正确性与性能 | Buck/Boost/DCM/多开关/LLC 分类回归；LLC100 单列，不作为通用算法唯一验收 |

没有用户批准的产品默认工程近似语义时，Agent 不能宣称 G3/G4/G5 的工程近似正式实施已完成；只读/实验工作仍可进行。

## 7. 通用验收清单

| 编号 | 用例 | 验收重点 |
|---|---|---|
| GEC-01 | 单一有向根 | 保持旧首次根与单事件快速路径 |
| GEC-02 | 可证明严格同根 | 严格组完整提交、编译模型证据绑定 |
| GEC-03 | **两个真实不同的极近自主根** | 已批准工程模型下真实接受且到 `T_END`（非 LLC） |
| GEC-04 | 三个近邻、两个相邻间距<T_atom但总跨度>T_atom | 固定窗口、无链式扩容 |
| GEC-05 | 候选中一部分仍保持原段 | `candidate ≠ switched` |
| GEC-06 | 窗外/更早独立事件 | 不能漏检/错排，失败则未决 |
| GEC-07 | 切触或守卫一阶导数为 0 | 二阶/短区间后备或正确未决 |
| GEC-08 | 无合法后继 / 不相容储能状态 | 拒绝、事务回滚 |
| GEC-09 | 多合法后继 | 不无证据任选其一 |
| GEC-10 | PWM/deadline 位于簇窗口内 | 不吞独立控制脉冲 |
| GEC-11 | 极小时间差但极大状态/能量效应 | 不因时间近就批准 |
| GEC-12 | 连续两次工程簇 | 证书失效、状态缓存、全局时刻正确 |
| GEC-13 | 非零绝对起点 | 局部根到全局时刻转换正确 |
| GEC-14 | PWA R/C/L 多段 | 不依赖二态二极管专用逻辑 |
| GEC-15 | SAVE_DT/ATOM_ORDER 改变 | 不隐式放宽/缩窄合同 |
| GEC-16 | 工程接受之后再次找根 | 后继新模型、非旧守卫、无遗漏 |
| GEC-17 | 大量但少数临界的开关 | 正常路径不做 `2^all-switches` 枚举 |
| GEC-18 | 数值证据不足与非法根状态 | 保留精度状态，不伪造根状态/证书 |
| GEC-19 | 不同网表元件顺序/无关重命名 | 数学行为不变 |
| GEC-20 | 注入错误、重编译失败 | 完整无脏提交 |

**CAP-01～CAP-08（§2.4）必须与上述 GEC 一起验收。** 所有涉及真实二极管或 MOS 的正向电路必须有显式 pF 级结电容或输出电容，不得仅在报告里口头声称。

### 基线保护与物理模型变化处理

- 在**回退基线原模型**上首先复跑 124 项：历史目标 **118 PASS / 6 INCONCLUSIVE / 0 FAIL**；历史 CTest **8/8**；五个已恢复电路 `COMPLETED`，CE01/CE02 通过。
- 之后若因显式增添 Cj/Cds 而变更网表，应记录新网表/模型哈希及独立 oracle；不能要求新模型所有波形逐点等于旧模型，也不能把它的差异计作 Solver 错误或掩饰真实错误。
- 变更后每次构建执行全部没有被合法调整适用范围的旧测试；新增 GEC/CAP 正向案例通过才说明 CR-002 的通用能力实现。
- LLC100 继续单列 `COMPLETED/STOPPED_UNRESOLVED/FAIL`；既不能因 LLC100 暂停否定已验证的通用子类，也不能以通用测试 PASS 伪称 LLC100 已完成。

## 8. 实施授权、版本控制与输出

1. 原始三份正式 V1.1 施工文件和 10 月 18 日架构评审稿**只读保留**。所有批准决定以 CR-002 独立变更记录承载，带原因、风险、测试及批准状态。
2. 先证据再动代码：记录目标树 SHA256、编译环境、对照实验和最小反例；形成必要的可恢复快照。禁止硬 reset/clean/覆盖未知文件。
3. 主 Agent 负责数学、接口、事件因果、接受；其他 Agent 可独立生成含寄生参数的 fixture、oracle、CI/日志，不得未经审查另起求解器。
4. 对任何改变数学模型（包括更改旧测试网表寄生电容）或生产默认近似策略的决定，必须先在变更清单记录并确认；不能借“数值更安全”擅自偏离批准设计。
5. 每一 Gate 都必须真实运行测试，不得仅提交图纸、说明或空接口。未完成不得谎报完成。

**建议交付目录：** `docs/design_changes/CR002/`，实验报告存 `reports/cr002/`，独立实验存 `research/cr002/`。输出文件至少包括：

- `CR002_Design_Change_Specification.md`（本文件批准版本，历史原稿只读）
- `CR002_Architecture_Diff.md`（2026-10-18 → 2026-10-19 → rollback → CR-002）
- `CR002_Generic_Event_Design.md`（可实现接口、伪代码、成本分析）
- `CR002_Pending_Decisions.md`（待用户批准的默认近似与误差合同）
- `CR002_Parasitic_Capacitor_Audit.md`（逐网表、逐器件、电容位置、参数/是否重复）
- `CR002_Math_Validation.md`（充分条件、反例、证据范围）
- `CR002_GEC_CAP_Test_Ledger.json`（GEC-01～20、CAP-01～08）
- `CR002_Implementation_Report.md`（真实代码/构建/阻挡）
- `CR002_Regression_Performance_Report.md`（对等模型的速度、分立旧/新物理模型验证）
- `CR002_Release_Assessment.md`（是否具备产品发布条件、LLC100 单列）

## 9. 核心完成判据

只有同时满足下列条件，才可写 `CR002_IMPLEMENTATION_COMPLETED = YES`：

- 实际交付通用 `First Event → EngineeringCandidateCluster → Joint Reclassification → Event Acceptance` **可运行闭环**；
- 至少一个**非 LLC、真实不同近根**的物理 PWA 电路（如含 `1 pF` 二极管结电容、含 `1 pF` MOS Cds 的合成电路）以正式产品实现、明确近似记录完成到 `T_END`；
- 同时通过包含独立早根、时间近但大能量差、短 PWM、没有后继、多后继的负向测试；
- 所有真实功率开关/二极管测试 fixture 均经过逐实例寄生项审计并在缺失时显式补齐（无双算）；
- 有可计算、可信的状态/时间/因果检查并声明证据范围；
- 旧基线不退化（区分物理电路修改后的新 oracle）；
- 一般单事件路径不开启指数穷举；
- 工程接受模型及误差政策获得用户批准，未将实验策略擅自变成正式默认；
- 报告包含可重建源码/测试/哈希、性能和所有已知限制。

如用户尚未确认近似默认策略或误差预算，则**只可交付并报告已完成的非默认原型和部分代码**；不能声称正式产品实现完成。

---

### CR-002 用户待批准的产品语义（不得自行决定）

| ID | 待裁决项目 | 本文建议 | 未批准前允许工作 |
|---|---|---|---|
| DEC-01 | 工程簇共同接受时刻与路径 | 优先验证 `CLUSTER_DELAYED_APPROX`，精确桥接作为已有可靠能力子类 | 隔离原型、证据接口、性能测试 |
| DEC-02 | 守卫越界/本构域的工程近似定义 | 明确声明暂时延迟的近似模型，限本簇有效 | 给出可复现反例及充分条件 |
| DEC-03 | q/φ/η、能量及时间误差预算 | 使用量纲合理、参数化、可核查的局部界；不可只凭 T_atom | 提议多套方案，注明未知 |
| DEC-04 | 对暂时不可验证后继/复杂中间事件的退避 | 保留精确路径或安全停止；不因完成率降低审查 | 失败诊断和负向测试 |
| DEC-05 | pF 基准如何选择 | 新通用 fixture 缺失寄生时以 1pF 为公开默认测试参数，真实器件参数以资料优先 | 审计现有网表、建议修改和 oracle 工作 |

**整个 CR-002 是通用算法设计变更，不得再演变为 LLC D1/D4 专题研究。**
