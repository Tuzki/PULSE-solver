# PULSE Solver V1.1 — 系统架构与接口规范

> 版本：Implementation Contract 1.0 / 2026-10-19  
> 用途：供 Codex 实际重构及审查；不是“已开发或已验证”的声明。  
> 新项目：`/Users/tuzki/Documents/Codex/pulse-solver-v1.1/`  
> 依据：旧施工草案、`PULSE_V1_1_Construction_Spec_Review_Feedback.md`、`Numerical_Domain_Validation_Report.md`，以及用户对 C01–C03 的工程化裁决。  
> 状态：**实施基线**；本文明确的保守拒绝属于预期行为，不得声称覆盖任意病态系统。实际工程实现仍需通过验收。

## 0. 设计约束与证据边界

**产品目标：**以可审计的 Markdown 单文件网表，构建电域 + 数域联合 PWA 事件驱动仿真器。运行时代数、连续状态和离散事件由同一协调器驱动，连续部分沿用 Descriptor/MNA → 模态编译 → 矩阵指数传播 → 首次事件定位。**不新增第 14 种数学原语，不增加通用连续非线性 ODE 求解器。**

**本轮工程变更只有两条主线：**

1. 输入/编译重构：旧 `*.pe.net` / 旧 S/D/NR/NC/NL 类型 → `*.md`、13 个原语、`.SUBCKT`、固定参数、类型/依赖推断和可重现 IR。
2. Runtime 重构：旧电域换模主循环 → 联合连续传播 + 定时队列 + `(t,δ)` 同刻事务 + REG 原子更新 + 代数跳变重算 + 物理状态映射 + 可回滚接受。

历史数域研究 N01–N12：**11 PASS、0 FAIL、1 INCONCLUSIVE**（N04 切触窗口只能安全未决）；这是研究原型证据，不是正式 Solver 结果。历史 LLC 100 周期仍未通过。本版本承诺的是“能证明/能按工程合同接受则执行，否则有诊断地停止”，而非任意模型全部仿真完成。

### 0.1 已冻结与本文件作出的工程裁决

| 编号 | 施工决定 |
|---|---|
| D01 | 新标准网表扩展名 `.md`；文件包含 Parameters、Network、Simulation、Layout 四区块。 |
| D02 | 13 个红色原语：电域 `R C L V I SW SENSOR`；数域 `MATH CMP SEL INT REG EVENT`。 |
| D03 | `SENSOR` 只检测电压和电流；不作为串联的零欧理想仪表。 |
| D04 | `REAL BOOL TRIG` 三类数域信号，类型可唯一推导则省略前缀，歧义才显式标注。 |
| D05 | 黑色官方/蓝色用户组件都是 `.SUBCKT`；Solver 只认识展开后的红色原语。 |
| D06 | 参数在文件开头冻结；表达式只允许字面量、先前定义的固定参数、`+ - * / ( )`；无函数、内置常量引用或运行时信号。 |
| D07 | MATH 连续仿射采用 `Y = 2*X1 - 3*X2 + 10`；离散非线性采用 `OP=MUL` 等操作码，仅用保持量。 |
| D08 | `V/I` 允许 `DC=`；`REG` 允许 `MODE=SR`；`EVENT` 允许动态 REAL 延时输入。 |
| D09 | 无 `.SAVE` = 全部可观测通道及 TRIG 事件；有 `.SAVE` = 所选通道；缺省与显式空选择区分。 |
| D10 | C01：受限工程近似时间接受；不允许猜测首次根或无条件合并有因果影响的近事件。 |
| D11 | C02：新模态必须有向前有效性；不能证实时可安全停止，不自动引入滑模/迟滞。 |
| D12 | C03：跨模态保持物理电荷/磁链/INT 状态，重建降阶坐标；新约束不相容则报错。 |
| D13 | 失败的候选传播、REG/agenda/缓存/输出不污染已提交历史；只有物理时刻事务整体成功才提交。 |
| D14 | `T_atom=effective_SAVE_DT*10^(-N)`；N 缺省为 9，最终运行配置确定后计算并记录，改变 SAVE_DT 可改变工程事件行为。 |
| D15 | 正式发布需要产品回归；研究原型 PASS 不自动转为产品 PASS。 |

本文其余明确的默认语义属于**本次实施选择**，不是宣称用户已逐条口头裁决。若实现发现与模型数学矛盾：保守拒绝、保留最小反例并报告，不静默改变用户冻结的项目边界。

## 1. 架构总览

```text
NetlistGen / CLI / C ABI
         │
         ▼
*.md ─ Markdown Sections ─ Lexer/AST ─ Frozen Parameters
         │                                  │
         └──── SUBCKT expansion ─ Typed Primitive IR
                                     │
                      Dependency/SCC + topology/SourceMap
                                     │
             ┌───────────────────────┼─────────────────────────┐
             ▼                       ▼                         ▼
    Electrical + INT + MATH     Guard/PWA Compiler       REG/EVENT Kernel
    Descriptor / MNA            first-root inputs        agenda + microsteps
             │                       │                         │
             └───────────────────────┼─────────────────────────┘
                                     ▼
                  Runtime Event Acceptance Coordinator
                    candidate state / commit / rollback
                ┌────────────────────┼───────────────────┐
                ▼                    ▼                   ▼
           Mode matrix exp       First Root       (t,δ) transactions
                └────────────────────┼───────────────────┘
                                     ▼
                 stable observations / NPZ / event log / report
```

主要依赖方向：Parser 不调用 Solver；Compiler 不产生时间推进；矩阵传播不修改 EVENT；Root Finder 返回证据而不提交换模；Runtime 唯一负责提交；Recorder 只能观察已提交状态。

## 2. 数据合同和数学边界

### 2.1 仿真最小四项输入

`Netlist`、`T_END`、`SAVE_DT`、`Channels`。IC 从网表得出，未设储能/REG 初态默认 0。优先级：**API 显式值 > CLI 显式值 > Markdown Simulation > 缺省配置**；缺省必须要求有效的 `T_END`/`SAVE_DT`，不能猜测仿真时长。用户显式选择 `Channels=[]` 与未设置 Channels 区分：前者明确不导出波形通道（仍保留必要元数据与诊断），后者全输出。`.SAVE` 指定后的运行时显式 Channels 覆盖 `.SAVE`。相同最终配置不论来自何处，行为与 `T_atom` 一致。

### 2.2 统一连续数学

固定 PWA 模态 `σ`、保持输入 `r`，以物理储能及 INT 状态 `s=[q_C; φ_L; η_INT]`、电气代数量 `a` 装配：

```math
E_\sigma\dot s = A_\sigma s + B_\sigma a + D_\sigma r + b_\sigma,\qquad
0 = K_\sigma a + F_\sigma s + H_\sigma r + k_\sigma.
```

在支持的正则/约束子空间上消元，得到 `s'=Mσ s+hσ(r)`；模式内 `r` 为常量，传播可通过增广矩阵指数。所有 Sensor、连续 MATH、INT 进入同一个 Descriptor；不得“电路积分一次，数域再积分一次”。**合法的原始奇异代数块不必然等于奇异物理模型**；可验证约束相容性与切向一致后消元，不支持的高指数/不唯一动态明确拒绝。

### 2.3 电数域作用范围

- 电域：电阻、电容、电感/互感、有限 Ron/Roff 开关、独立与受控 V/I；PWA R/C/L 采用**连续**本构表；非理想模型以数学原语组合。
- 连续数域：常量与仿射 MATH、INT、CMP 守卫、BOOL 驱动 SEL 分段；不能执行任意连续 `SIN(v)` 或 `v*i`。
- 离散数域：REG 保持 REAL/BOOL；TRIG 是瞬时通知；离散 MATH 允许 `MUL/DIV/SIN/COS/SQRT/POW/EXP/LOG/ATAN2`（必须定义函数域）。
- 不支持：任意连续非线性半导体/IQQ、任意高指数 DAE、任意动态可变 RLC、磁/热/力域、通用冲激/滑模、隐式通用非线性方程解算、DLL/FMU、GUI/器件库铺量。

## 3. Markdown 网表语言规范

### 3.1 文档区块、词法与连通性

```markdown
# PULSE Netlist v1.1

## Parameters
\`\`\`pulse
.PARAM VIN=48
.PARAM N=2
.PARAM LP=50u
.PARAM LS={LP/(N*N)}
\`\`\`

## Network
\`\`\`pulse
...仅原语、SUBCKT/ENDS、X 实例和连通定义...
\`\`\`

## Simulation
\`\`\`pulse
.TRAN T_END=1m SAVE_DT=1u
* .SAVE 缺失即全输出
\`\`\`

## Layout
\`\`\`json
{"version":"1.1","components":{},"wires":[]}
\`\`\`
```

上例用反斜杠转义三反引号仅为展示。真正文件应使用标准 Markdown fenced code block。首部 `# PULSE Netlist v1.1` 必需；四个 `##` 标题各恰好一次；Network 与 Simulation 中认可的 `pulse` 代码块被解释，Layout 中 `json` 代码块只用于布局；不允许 Markdown 段落变成求解语义。其他无关正文可忽略但未识别的 `pulse` 代码块必须报错，不能静默吞掉电路。Layout 只可改变图形不改变 Network 的真实连通；GUI 修改连线必须同步提交 Network。

词法：关键字大小写不敏感、用户标识符大小写敏感；标识符 `[A-Za-z_][A-Za-z0-9_]*`；电气地是独占标记 `0`；同作用域实例/网络名称不可二义；连续行首 `+` 表示上一行续行，`*` 行首注释；统一数值后缀 `T,G,Meg,k,m,u,n,p,f`，`M` 单独不作为兆单位（需要兆用 `Meg`）；不支持隐式单位转换或内置数学常量。`.PARAM` 允许顺序向前引用，未知/循环/除零/非有限数报错；全局参数表冻结，`.SUBCKT` 暂无实例参数覆盖；可通过文件头不同常量 + 局部明确展开取得不同设备参数。`{...}` 可在元件数值位中使用冻结表达式。原语参数与端口的结构校验先于仿真。

`Network` 语句顺序不改变语义；SourceMap 保存 `(file,block,line,column,hierarchical_instance)`；SUBCKT 不允许递归实例化。官方黑色与用户蓝色区别仅存 GUI 库 provenance，导出均为 X + SUBCKT。

### 3.2 完整原语输入表（最低实施合同）

| 原语 | 推荐规范写法 | 状态、约束和错误 |
|---|---|---|
| `R` | `R1 A B R=100` 或 `R1 A B IV_TABLE=[(-2,-2m),(0,0),(2,20m)]` | R>0；表按 V 严格递增且正增量导纳、连续插值 |
| `C` | `C1 A B C=10u IC_V=0` 或 `C1 A B QV_TABLE=[(-1,-2u),(0,0),(1,3u)] IC_Q=0` | C>0；dQ/dV>0；初值 `IC_V` 或 `IC_Q`，不可矛盾并给 |
| `L` | `L1 A B L=10u IC_I=0`，`L1 A B PHII_TABLE=[(-1,-2u),(0,0),(1,3u)]` | L>0；dΦ/dI>0；`IC_I`/`IC_PHI` 二选一 |
| `L` 多端口 | `LCOUP (P1 P2) (S1 S2) L_MATRIX=[[50u,23.75u],[23.75u,12.5u]] IC_I=[0,0]` | SPD 对称矩阵、端口有序、绕组方向确定；支持向量 `IC_PHI` |
| `V` | `V1 A B DC=48` 或 `V1 A B VCTRL` | 直流常量/REAL 控制互斥；电压定义 `V(A)-V(B)` |
| `I` | `I1 A B DC=1` 或 `I1 A B ICTRL` | 电流正方向 A→B；受控 REAL 输入 |
| `SW` | `SW1 A B ON RON=10m ROFF=1Meg` | ON BOOL，高=Ron；两者均有限正值；不假定 ROFF 无穷 |
| `SENSOR` | `SENSOR_V VC V A B` / `SENSOR_I IL I L1 [PORT=1]` | V=V(A)-V(B)，I 读有向支路，不创建物理测流支路 |
| `MATH` 连续 | `MATH_ERR E = {VREF} - FB` | 仅可化为仿射；常量乘 REAL 合法，动态 REAL×REAL 不合法 |
| `MATH` 离散 | `MATH_P P VSAMP ISAMP OP=MUL` | 输入必须在事件间保持；定义域错误终止该事务 |
| `CMP` | `CMP1 G X OP=GE THRESHOLD=1` | 输出 BOOL；守卫与等号/穿越详见 §6 |
| `SEL` | `SEL1 Y G LOW HIGH` | G BOOL；Y/LOW/HIGH 同为 REAL 或 BOOL；FALSE→LOW |
| `INT` | `INT1 X DX IC=0` | 连续 `dX/dt=DX`；初态默认为零 |
| `REG` | `REG1 Q X CLK IC=0` 或 `REG2 G MODE=SR SET=ON RESET=OFF PRIORITY=RESET IC=0` | Q 只能 REAL/BOOL，触发输入 TRIG；SR 冲突优先级显式 |
| `EVENT` | `EVENT_CLK CLK MODE=PERIODIC PERIOD=10u START=0`；`EVENT_OFF OFF MODE=DELAY SOURCE=CLK DELAY_INPUT=TON POLICY=REPLACE` | 还支持 AT/EDGE；动态 TON 是保持 REAL；见 §5 |

同类参数别名不得暗中改变物理意义。R/C/L 的 PWA 表默认 **RANGE=ERROR**，可显式 `RANGE=EXTEND` 做端部线性外推；界外时按选择报错或外推。不支持闭区间表点之后的零、负斜率。多端口 L 仅线性矩阵，不假装实现多绕组饱和的非线性磁芯。

`SENSOR I` 最小合同：引用已命名且方向已知的单支路或 `L_MATRIX PORT=n`；若引用复合子电路端口电流，Compiler 必须可唯一重建端口电流及其正方向，否则拒绝 `AMBIGUOUS_CURRENT_REFERENCE`。线束任意位置的电流不能凭节点名猜测。

`MATH OP=POW` 的指数建议采用固定 `EXPONENT=...`；`ATAN2` 两个保持输入；所有高级函数仅离散执行，参数/输入不合法拒绝并回滚。可在这些已支持函数以内添加内部计算优化，但不应借机扩展到一个外部脚本语言。

### 3.3 类型与驱动

每个电气节点连接电域电端口；数域信号只能 `REAL/BOOL/TRIG`；同作用域一个数域信号最多一个驱动；`REG` 数据/输出仅 REAL 或 BOOL，SEL 数据为 REAL/BOOL，TRIG 不得被 REG 持续保存。类型可推导时不加 `REAL::`；歧义用 `REAL::NET` 或 `BOOL::NET` 等消除，**TRIG:: 只可标触发端口**，不能把 TRIG 变成保持数据。无驱动、冲突驱动、强制跨类型联接报错。

连续仿射反馈 SCC 联合进入 Descriptor；离散组合 DAG 用拓扑顺序；REG 切断离散反馈；无状态离散非线性环拒绝 `COMBINATIONAL_CYCLE`；CMP/SEL/SW 代数反馈需要独立唯一性/向前检查，绝不能拿“找到第一个固定点”冒充唯一。

### 3.4 示例：可用作 Parser Golden 的完整 Netlist

> 本例是**非理想开关控制 RC**，不是声称已验证的 Buck 物理回路。布局线条仅用于显示。

````markdown
# PULSE Netlist v1.1

## Parameters
```pulse
.PARAM VIN=10
.PARAM VREF=3
.PARAM T_END=5m
.PARAM SAVE_DT=1u
.PARAM TS=100u
.PARAM TON={TS*0.4}
.PARAM RLOAD=10
.PARAM COUT=100u
```

## Network
```pulse
.SUBCKT LP1 IN OUT
MATH_D DX = 1000*(IN-OUT)
INT_F OUT DX IC=0
.ENDS LP1

V_IN VIN 0 DC={VIN}
SW_MAIN VIN VOUT GATE RON=10m ROFF=1Meg
R_LOAD VOUT 0 R={RLOAD}
C_OUT VOUT 0 C={COUT} IC_V=0
SENSOR_V VS V VOUT 0
SENSOR_I IL I R_LOAD
X_FILT VS VF LP1
MATH_ERROR E = {VREF}-VF
CMP_HI HI VF OP=GE THRESHOLD={VREF}
EVENT_EDGE RISE MODE=EDGE SOURCE=HI EDGE=RISE
EVENT_CLK CLK MODE=PERIODIC START=0 PERIOD={TS}
EVENT_OFF OFF MODE=DELAY SOURCE=CLK DELAY={TON} POLICY=TRANSPORT
REG_GATE GATE MODE=SR SET=CLK RESET=OFF PRIORITY=RESET IC=0
REG_V VSAMP VS CLK IC=0
REG_I ISAMP IL CLK IC=0
MATH_POWER POWER VSAMP ISAMP OP=MUL
```

## Simulation
```pulse
.TRAN T_END={T_END} SAVE_DT={SAVE_DT}
* 不写 .SAVE，即输出全部可观测通道及 TRIG 日志。
```

## Layout
```json
{"version":"1.1","components":{"V_IN":{"x":80,"y":80},"SW_MAIN":{"x":200,"y":80}},"wires":[]}
```
````

### 3.5 高级 MATH 与动态延时例

```pulse
* DUTY_HELD 必须由 REG 等保持源提供
MATH_ON TON = {TS}*DUTY_HELD
EVENT_OFF OFF MODE=DELAY SOURCE=CLK DELAY_INPUT=TON POLICY=REPLACE
```

同一 δ 如果 DUTY_HELD 由 CLK 所触发的 REG 更新，则 EVENT 锁存的是该 δ 的**旧快照**；若控制设计希望本周期使用新 DUTY，必须在明确的后续 δ 事件中触发延时，不能因网表书写顺序发生隐式相位改变。

### 3.6 Parser 最小无歧义文法及优先级

以下是**实现文法约束**，不是要求用户手写 JSON IR：

```ebnf
file          := header parameters_section network_section simulation_section layout_section ;
parameters    := ('.PARAM' IDENT '=' const_expr EOL)* ;
network_stmt  := primitive | subckt_begin | subckt_end | x_instance | comment ;
subckt_begin  := '.SUBCKT' IDENT port_name+ ;
subckt_end    := '.ENDS' IDENT ;
x_instance    := 'X' IDENT port_name+ subckt_name ;
primitive     := primitive_kind IDENT port_and_option_list ;
fixed_param   := '{' const_expr '}' ;
const_expr    := add ;
add           := mul (('+'|'-') mul)* ;
mul           := unary (('*'|'/') unary)* ;
unary         := ('+'|'-') unary | atom ;
atom          := NUMBER_WITH_SPICE_SUFFIX | IDENT_PREDECLARED | '(' const_expr ')' ;
affine_math   := 'MATH' IDENT IDENT '=' affine_expr ;
discrete_math := 'MATH' IDENT IDENT IDENT* 'OP=' FUNCTION_NAME option* ;
```

词法必须区分 `MATH1` 这种**完整实例标识符**和头部的 `MATH` 原语 Kind：通过已知最长原语前缀识别 `SENSOR_X`、`EVENT_CLK`、`SW_MAIN` 等，不凭首字母推断（`SW` 与 `SENSOR` 不能混淆）。`X_FILT` 必须识别为子电路实例；真正的 `.SUBCKT` 定义名在引用前可已经定义或经过两遍解析后解析，但禁止递归。

`affine_expr` 解析为一棵包含字面量、冻结 `{PARAM}`、REAL 网络名、加减乘除和括号的语法树；常数折叠和符号分析之后必须能化为 `Σa_i x_i+b`，否则报 `CONTINUOUS_NONAFFINE`。例如 `2*VOUT` 合法，`VOUT*I_L` 不合法。`discrete_math` 按操作码分别限定输入个数和函数域，且所有动态输入须已被证明为离散保持。

PWA 表、L_MATRIX 使用由括号/逗号分隔的专用数组解析器，不在它们的方括号内部把续行符误判为算术 `+`。单位后缀属于数值字面量，不能靠 MATH 来转换。

### 3.7 合法模型的最小参数默认与拒绝规则

- 线性 `R/C/L`、所有 Ron/Roff 必须严格正且有限；PWA 表至少两个严格递增横坐标点，相邻每段斜率严格正；表内电荷/磁链截距也属于物理本构，不得在分段切换时丢失。
- 单一 C/L 的初值可以分别用电压/电荷、电流/磁链之一提供；没有初值默认为零对应的**物理储能状态**；对应本构关系若未覆盖 0 且 RANGE=ERROR 应明确初始不相容，而不是隐式外推。
- `REG` REAL IC 必须有限，BOOL IC 必须是 0/1；`EVENT PERIODIC PERIOD>0`，`AT≥simulation_start`（允许 `AT=0`），延时锁存值≥0。
- 连续比较器 `CMP` 支持 `GT/GE/LT/LE`，不在 V1.1 加浮点精确 `EQ/NE` 连续守卫；离散保持输入上的点谓词仍按指定比较算子。每个信号只能有一个有向驱动，未被消费的合法观测可输出。
- 分支方向：所有 `R/C/L/V/SW` 的参考电压是首节点减末节点；`I` 的正方向从首节点到末节点；`SENSOR I` 的符号采用目标元件已声明的参考电流方向，`L_MATRIX PORT=n` 采用第 n 绕组正方向。
- 受控电源、复合端口、电流测量无法建立唯一代数映射时拒绝，不能增加用户看不见的物理支路来让编译“看起来能跑”。

## 4. Compiler 的内部对象和算法合同

| IR | 字段/不变量 | 消费者 |
|---|---|---|
| `SourceMap` | block、行列、SUBCKT 实例路径、名称 | 诊断/GUI |
| `FrozenParameterTable` | 值、文本来源、表达式依赖、单位比例 | 原语实例化 |
| `PrimitiveIR` | 13 Kind、参数、IC、有向端口、稳定 ID | Compiler |
| `TypedNetIR` | 物理域或 REAL/BOOL/TRIG、驱动、连续/保持/事件属性 | 数域编译 |
| `PhysicalStateIR` | 电荷 q、电感磁链 φ、INT η；每态对象 ID | Runtime/模式映射 |
| `ModeIR` | 段号/BOOL/SW、Descriptor、合法约束、降阶映射、模式指纹 | 传播和右侧检查 |
| `GuardIR` | g=cᵀs+d、侧规则、方向、源 ID、活动模式绑定 | 首次根搜索 |
| `DiscreteKernelIR` | REG old→new、拓扑顺序、TRIG 因果、函数域 | δ 内核 |
| `EventCertificate` | 根区间、首次证明、方向、模式/入口版本、认证范围 | 接受协调器 |
| `AgendaItem` | deadline、来源、端口、策略、generation、token | EVENT 队列 |
| `RunState` | 时间、共同物理状态、局部模式坐标、REG/BOOL、agenda 与版本 | 唯一提交对象 |
| `OutputRegistry` | 节点、支路、REAL、BOOL、INT/REG、TRIG 元数据 | Writer |

模式数组顺序由稳定路径 ID 规范化，不取决于哈希表或 Markdown 实例顺序。只允许在 `CompiledModel` 内部保存优化后的模态矩阵；用户层不必写线性代数矩阵。

**缓存：**符号分析/拓扑可复用；保持值或模式改变时，数值矩阵、仿射项、观测映射、守卫及旧证书必须按依赖失效。支持 `Mσ(r)` 时必须确实将保持数据作用到矩阵；V1.1 初版可以**拒绝保持 REAL × 连续 REAL 的系数调制**，只支持已可化为固定模式系数或 `hσ(r)` 的情形，避免假缓存正确。恒定参数乘动态信号是合法仿射，不受此限制。

## 5. 时间、首次根与工程接受（C01）

### 5.1 三个分离的时刻

- **数学根** `τ∈[l,u]`：局部模型的有向首次事件证书，不等于精确物理根点。
- **接受时刻** `Ta`：Runtime 真正提交换模/检查点的可表示 TimePoint。
- **导出时间** `time_f64`：波形显示/兼容表达；**不是**权威事件时间。

内部 `TimePoint` 必须有可靠可比较的全局+局部高精度坐标和可无损序列化的表现。`Q_repr=2^-64 s` 保留历史设计；非网格事件/根的亚 tick 严格次序如无法可靠表达或比较，返回 `TIME_RESOLUTION_UNRESOLVED`，不得先化 float64 再排序。`T_atom=effective_SAVE_DT×10^-N`（N 默认 9），在有效配置确定后计算；若小于可用时间网格间隔，不准悄悄上调。

### 5.2 C01 单次接受规则（工程近似）

1. 绑定可信入口版本与固定工作模型；得到所有活动连续守卫的首次有效根及事件组信息，检查预定 agenda 和 T_END 的时间先后。**根区间未能证明首次/方向/先后时不接受。**
2. 在首个有效事件的根区间上锚定至多 `T_atom` 的单次工程候选窗口；不得“相邻差小于 T_atom 就链式扩容”；不能把独立数字事件强制当作同时。
3. **优先桥接模式：**在能力范围内从根状态的可信点/区间切到后继模式，按后继流传播至共同可表示检查点 `Ta`，对整个桥接段做后继有效性及第二事件检查；该段检验通过才能按 `LOCAL_CERTIFIED`（仅局部）描述。
4. **受控工程近似后备：**如无法执行完整根状态桥接，但已独立证明首次事件及可接受的事件组与调度顺序，可选 `ENGINEERING_DELAYED_SWITCH`：用旧工作模式传播至 `Ta` 后换模。其语义是**有意将切换推迟到 Ta 的近似混合模型**，不能称为原始系统在 Ta 的严格状态。必须验证 `Ta≥u`、`Ta-l≤T_atom`、无被吞并的不可交换数字事件，记录守卫越界幅度、相位差、局部误差估计及近似模型版本；误差估计/越界界无法构造、候选后继不确定或其他事件可能改变因果时，停止为 `UNRESOLVED`。该方法**不得**绕过物理状态连续性及新约束相容检查。
5. 严格同时的事件只有在共享根/约束关系证据下才能合并；极近但不同的事件只是候选，必须检查后继、因果与覆盖区间。不采用“秒数很小所以相同”的判据。
6. 返回 `EventAcceptance`：`root_interval`、`accepted_time`、`accepted_state_kind`(point/bounded/approx)、`before/after model IDs`、`chosen_policy`、`error_scope`、`certificate_scope`、`members`、`causal_order`、`status`。只要证据不足就返回未决而不写入已提交轨迹。

> 工程近似**不是**普遍正确性证明。禁止将局部近似误差和 `T_atom` 自身宣传为全轨迹误差界。对于实际支持的窄类（如受限标量或可证明单模态桥接），可以做更精确的流程；一般高 Q/LLC 无条件完成不属于 V1.1 声明。

### 5.3 事件位置误差的一个参考预算

在可验证局部有界性 `‖f_old−f_new‖≤B`、Lipschitz 上界 `L` 且无额外真实切换的前提下，延迟 `h` 的连续状态差可用 `B·(exp(Lh)−1)/L`（L=0 时为 Bh）作条件性局部界。不满足条件就不要输出看似严谨的误差界；必须保留已知近似时间窗口与守卫残差，并视产品验收限额决定拒绝。用户可以通过调整有效 SAVE_DT/N 提高精度，但**它们改变近似行为，并非仅改变波形保存密度**。

## 6. 模态一致性、右侧有效性与换模（C02/C03）

### 6.1 三项独立的接受义务

`algebraic_consistent`（代数方程成立） ≠ `mode_consistent`（模态谓词匹配） ≠ `forward_admissible`（存在已支持的合法右侧延续）。任意一项为 false 必须拒绝；证明不了则 `STOPPED_UNRESOLVED`。不通过有限微步骤预算冒充没有解的数学证明；不因旧模式根方向就直接批准新模式的右侧有效性。

边界例：`dx/dt=+1 if x≤0; -1 if x>0` 到达 x=0 时没有普通经典向前解。V1.1 不做 Filippov 滑动、无限切换正则化或自动迟滞；报告 `NO_FORWARD_ADMISSIBLE_MODE` 或未决，提示用户加入迟滞/延时/合理物理环节。

CMP 连续守卫（布尔历史侧）与离散点谓词（GT/GE/LT/LE）需分开实现：

| 输入情形 | 本版规则 |
|---|---|
| REAL 非零距阈值 | 依 GT/GE/LT/LE 点值；侧状态一致 |
| 连续有向穿越 | 取已证明右侧值，净 BOOL 变化可引出 EVENT EDGE |
| 连续切触、无换侧 | 不生成 EDGE；无法排除进一步有效根则未决 |
| 落在等号并在区间内始终恒等 | 依运算符点谓词赋值且验证其模态向前有效；无净边沿则不发 EDGE |
| t=0 等号、右侧无法证明 | `INITIAL_CMP_BOUNDARY_UNRESOLVED` |
| 代数跳变正好到阈值 | 重新计算点谓词与新约束；无右侧有效性证据则未决 |

高阶穿越不可一律因第一导数为零就拒绝：证明能力不足时以未决结束。不存在无需验证的绝对“在任何等号都保留历史侧”规则。

### 6.2 共同物理状态与模态局部坐标

- 权威连续状态：电容 **q**（PWA Q-V 的真实曲线及截距）、电感 **φ**（含互感矩阵方向）、INT **η**。线性储能允许等价稳定坐标，但必须提供可逆映射。
- 每模态局部状态 `zσ` 只作为加速计算坐标：`s_phys = Rσ(zσ, parameters)`；换模必须 `reconstruct_old → preserve physical → validate new constraints → reduce_new`。
- `SW`、CMP/SEL、REG 等普通离散更新**不允许隐式重置物理储能**；若新模态需要电容电荷或磁链跳跃才能相容，应报告 `INCONSISTENT_MODE_TRANSITION`。不静默投影、不自动加冲激电流、不靠传播一小步掩饰跳变。
- 模式内合法 Descriptor 子空间必须有一致初态和唯一导数；遇到无法证明动态唯一的高指数等复杂案例，明确拒绝/未决。无解/多解/瞬时 SCC 必须区分。

### 6.3 后继选择与混合 SCC

在固定物理状态及本 δ 的保持/逻辑信号下，枚举或认证混合 CMP/SEL/SW 候选配置；至少需检查：完整谓词一致性、代数相容性、唯一允许后继、右侧有效性。**不能只查到第一个固定点就接受。** 为防模式指数爆炸，允许对大型 SCC 设置明确预算/能力上限，超出返回 `MODE_UNRESOLVED`；避免用指数穷举作为所有电力电子电路的唯一实现策略。无模式报 `NO_STABLE_MODE`，多个模式报 `MULTIPLE_STABLE_MODES`，状态冲突报 `INCONSISTENT_MODE_TRANSITION`。

## 7. 离散数域与超密时间 Runtime

### 7.1 `(t,δ)` 协议

`δ` 只表示**同一个物理 t 的逻辑微步骤**，增加 δ 不增加任何物理时间；两个不同时刻不能靠 δ 伪装成同刻。一个同刻物理事务具有只读已提交入口和可变候选态。

每个 δ：

1. 收集此 δ 已到期有效 TRIG、认证根引发的侧变化及计划输入；同端口同 δ 重复合并，不同端口保留。
2. 读取该 δ 的稳定快照（物理储能、REG 旧值、BOOL、代数观测）；REG 同一 δ 批次读取同一快照。
3. EVENT 的动态 `DELAY_INPUT` 在同一快照**锁存**；同时计算全部触发 REG 的新值。
4. 原子写回 REG / 控制源、应用认证模式侧变化；固定物理储能，重建代数量和离散组合依赖。
5. 对 CMP/SEL/SW 求可接受稳定配置并检查向前有效性；只比较本 δ 入口稳定 BOOL 与本 δ 结束稳定 BOOL，净边沿在 `δ+1` 生成 TRIG，组合中间毛刺不可见。
6. 有新同刻 TRIG 继续 δ；全部合法稳定才提交本物理时刻事务。同步错误、数据域错误、模式未决均回滚。

不同 δ 采样可看前一 δ 已提交的新 REG；同一 δ 不可看其他 REG 的新写回。物理 `t` 处 output 选择最终稳定右侧 `t+`；事件前采样按对应 δ 快照独立决定。

### 7.2 EVENT 与 REG 参数

| 模式 | 具体动作/限制 |
|---|---|
| `EVENT PERIODIC` | `START`、`PERIOD>0`，按 `t0+kP` 精确描述目标；不反复浮点加 P 累漂移 |
| `EVENT AT` | 只发送一次绝对时刻 TRIG |
| `EVENT EDGE` | 稳定 BOOL 的净 RISE/FALL/BOTH → 下一 δ TRIG |
| `EVENT DELAY` | 对源 TRIG 锁存固定 `DELAY` 或保持 `DELAY_INPUT`，0 延时下一 δ，负延时拒绝 |
| `POLICY=TRANSPORT` | 保留多个 pending，正常到期分别触发 |
| `POLICY=REPLACE` | 新触发使旧 pending 无效（generation token），已到期并归入本批的事件不能取消 |
| `CANCEL=TRIG_NAME` | 收到取消 TRIG 时使仍 pending 的项失效；同 δ 取消先于新安排 |
| `REG` | 数据端 REAL/BOOL，触发 TRIG；`MODE=SR` 的 SET/RESET 为 TRIG；同时触发由 `PRIORITY=RESET/SET` 决定 |

异常函数（除零、非实开方、log 非正数等）终止整事务并回滚，绝不向连续矩阵或导出通道传播 NaN 作为普通合法值。

### 7.3 原子候选与回滚起点（C04）

**先建立候选，再传播**，永不先修改已提交连续状态才记录事务：

```text
S_committed = last consistent checkpoint
next = plan_next_event(S_committed)           # 只读证据
S_candidate = deep_snapshot_or_COW(S_committed)
propagate_into(S_candidate, next)            # 含时间、物理状态、局部状态与误差账本
accept_event_on_candidate(S_candidate)       # C01/C02/C03
run_all_deltas_on_candidate(S_candidate)
if all checks pass:
    atomic_commit(S_candidate, event_log, samples, versions)
else:
    discard(S_candidate)                      # 包含 agenda、缓存、输出暂存
    emit STOPPED_ERROR / STOPPED_UNRESOLVED with diagnostic
```

若无事件、只是普通保存时刻，应在当前固定模态上计算观察值，不把 SAVE_DT 人为插入为物理换模事件。输出可以按提交的已知轨迹分段重建；不可从事务失败后的脏候选写成功波形。

### 7.4 循环与预算

重复配置检测应包含有效 REG/BOOL、当前模式、未消费 TRIG、有效待办 agenda 等语义状态；`δ` 绝对编号/世代编号不应单独阻止重复判定。真正重复可报告 `ZERO_TIME_CYCLE`；不重复却持续增长到预算则 `MICROSTEP_BUDGET`，不谎称证明循环不存在或已存在。两个错误都无脏提交。

## 8. 首次根/事件时间与历史日志（C05/C06）

### 8.1 Time API

统一返回：`TimePoint`（含权威可比较高精度时间）、`TimeInterval`（证书闭区间）、`TimeOrder`（BEFORE/EQUAL/AFTER/UNRESOLVED）、`TimePolicy`（精确桥接/延迟工程近似）。不能把 `[l,u]` 中点作为真实事件。

**定时调度的精度边界：**外部十进制 `PERIOD/AT/DELAY` 先转换为可追溯的输入值和向内存储的目标时间；如果转换误差会导致与根/其他时钟不可区分或错误交换因果顺序，返回未决。正式核心 C++ 使用检查过的 可移植的带符号 128-bit 或任意精度整数 tick（例如 Boost.Multiprecision，不依赖仅在部分编译器存在的 `__int128`）+ 局部高精度/区间比较或经实测等价的精确后端；可复用现有 MPFR/GMP 代码，不引入 Python 运行依赖。不能凭此次报告宣称已实现所有非 dyadic 期限的精确表示。

### 8.2 输出合同

- `out.pewave.npz`：`time=float64 seconds`、`analog=float32`、`digital=uint8`、`metadata_json`；内部状态不由 float32 回填。
- **权威事件日志** `event_log.jsonl`：包含 `time_canonical`（可无损恢复最终内部接受时刻，按 TimePoint 实际表示编码）、`time_seconds_display`、`delta`、TRIG/来源、守卫/根区间、前后模态、接受策略、误差/证据级别、事务 ID。仅保留 `float64+δ` 不够：两个不同物理时刻可能显示为同一个 float64。
- `simulation_report.json/.md`：结构化错误/警告、运行完成状态、局部证书等级、数值近似等级、事件/事务次数、未决原因、模型/源码版本、有效 `SAVE_DT/T_atom`。
- `.SAVE` 省略意味着所有有效层级电节点、可唯一求的支路电流、REAL、BOOL、INT/REG、TRIG 事件日志；重复别名按稳定 registry 规则映射，不静默丢弃。输出量过大明确警告或 OUTPUT_ERROR，不允许不告知地截断。
- 数域 TRIG 瞬时信号不能仅通过采样 digital:uint8 代替事件日志。`.SAVE` 指定时应决定 TRIG 过滤与电节点/支路通道筛选，但基础错误事件诊断始终记录。

### 8.3 完成与证据是不同维度

运行状态 `COMPLETED / STOPPED_ERROR / STOPPED_UNRESOLVED`；证据等级 `LOCAL_CERTIFIED / NUMERICAL / ENGINEERING_APPROXIMATION / NOT_CERTIFIED`（也可以兼容旧 ABI 的映射名）。不得把“某个窗口找不到根而主动停止”报告成 COMPLETED；任何局部认证不等于完整轨迹或 Compiler 模型误差认证。

## 9. 模式生成、初始化和诊断

初值：未定义的 C/L/INT/REG 默认为零；C `IC_V` 经 Q-V 计算为电荷；L `IC_I` 经 Φ-I/L_MATRIX 计算为磁链；全状态一致性检查后求初始代数和模式。`EVENT AT=0`、`PERIODIC START=0` 在确定的初始稳定态后作为同刻 δ0 批次；初值在 CMP 门槛时，只有获得初始化右侧有效性证据才可选择侧，否则 `INITIAL_CMP_BOUNDARY_UNRESOLVED`。

错误顶层优先保持旧规划：`INVALID_NETLIST / UNSUPPORTED_MODEL / INCONSISTENT_INITIAL_STATE / INVALID_PWA_CURVE / PWA_OUT_OF_RANGE / MODEL_SINGULAR / NUMERICAL_ERROR / EVENT_ROOT_FAILURE / MODE_STABILIZATION_FAILURE / PHYSICAL_CONSTRAINT_VIOLATION / OUTPUT_ERROR / INTERNAL_ERROR`。诊断子码另增 `CONTINUOUS_NONAFFINE / COMBINATIONAL_CYCLE / AMBIGUOUS_CURRENT_REFERENCE / NO_STABLE_MODE / MULTIPLE_STABLE_MODES / NO_FORWARD_ADMISSIBLE_MODE / INCONSISTENT_MODE_TRANSITION / ZERO_TIME_CYCLE / MICROSTEP_BUDGET / TIME_RESOLUTION_UNRESOLVED / INITIAL_CMP_BOUNDARY_UNRESOLVED`。发现完成性不足时报告 `STOPPED_UNRESOLVED` 并给定位信息，不能滥用 INVALID_NETLIST。

缓存和证书绑定最少包括 `model_version、mode_version、entry_state_version、schedule_version、time_policy_version`；数域保持量或拓扑/模式变化需要使依赖的观察/守卫/数值映射失效，旧首次根证书失效。

## 10. 成功及能力边界

PULSE V1.1 必须能够正确模拟典型非理想电力电子网表 + 连续线性反馈 + 数字采样与 PWM。在事件因果不能排序、无合法右侧延续、储能状态与新约束不相容、非认证高阶切触或大规模未证明的代数 SCC 上，可以安全停止并建议用户增加迟滞、有限寄生、延时或减小工程窗口；**禁止 Solver 静默修正网表。**

需要在正式实现中对历史 LLC 100 周期单独标记仍未决，不允许将 N01–N12 的通过替代长周期验收。详细施工步骤、测试和 Agent 协作见第二份文档。
