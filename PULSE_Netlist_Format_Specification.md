# PULSE 网表文件格式标准

规范版本：1.0。适用产品：PULSE Solver V1.15。网表语言版本：v1.1。发布日期：2026-10-22。

## 1. 范围与规范用语

本标准定义 PULSE 单文件 Markdown 网表的结构、词法、类型、十三种原语、子电路、仿真配置、输出选择及布局数据。本文是格式规范，不是可直接运行的电路输入。第 14 节给出完整 LLC 网表，并提供同内容的独立文件 `PULSE_Netlist_Example_LLC.md`。

“必须”“不得”表示强制要求；“应”表示推荐写法；“可以”表示允许的可选形式。代码中的尖括号占位符仅用于语法说明，实际网表不得保留占位符或省略号。

V1.15 继续使用 `# PULSE Netlist v1.1`，不得因产品版本变更而写成 `# PULSE Netlist v1.15`。

## 2. 文件结构

### 2.1 文档骨架

网表为不带 BOM 的 UTF-8 文本，文件扩展名为 `.md`，必须包含以下标题，且四个二级标题按所列顺序各出现一次：

1. `# PULSE Netlist v1.1`
2. `## Parameters`
3. `## Network`
4. `## Simulation`
5. `## Layout`

前三节的语义内容放在 `pulse` 围栏代码块中，Layout 使用 `json` 围栏代码块。应每节使用一个代码块。Parameters 可以为空，但不得省略该节。

正文说明不参与求解。标题、注释、元件坐标或图形颜色不得建立电气连通。未知章节中的 `pulse` 代码块不属于合法网表内容。

### 2.2 最小完整示例

以下外层四反引号只用于展示完整 Markdown 文件；实际文件从 `# PULSE Netlist v1.1` 开始，不包含外层围栏。

````markdown
# PULSE Netlist v1.1

## Parameters
```pulse
.PARAM RLOAD=1k
.PARAM COUT=1u
```

## Network
```pulse
I_IN 0 OUT DC=1m
R_LOAD OUT 0 R={RLOAD}
C_OUT OUT 0 C={COUT} IC_V=0
SENSOR_V VOUT V OUT 0
```

## Simulation
```pulse
.TRAN T_END=5m SAVE_DT=1u
.SAVE V(OUT) I(C_OUT) VOUT
```

## Layout
```json
{"version":"1.1","components":{},"wires":[]}
```
````

## 3. 词法、命名与数值

### 3.1 大小写与标识符

- 原语关键字、选项名和枚举值不区分大小写；规范生成应使用大写。
- 用户定义的实例名、节点名、信号名、参数名、子电路名区分大小写。
- 本地标识符为 `[A-Za-z_][A-Za-z0-9_]*`，不得含空格、连字符或中文。
- 电气地使用唯一特殊节点 `0`。其他电气节点不得使用裸数字；使用 `N1`、`N2` 等合法名称。
- 同一作用域的实例名必须唯一。一个数域信号必须有唯一驱动，不得同时作为电气节点。
- 层级展开名称由 `/` 分隔，例如 `X_D1/SW_PATH`。`/` 不用于本地实例名的声明。

### 3.2 实例类型由名称前缀确定

一行元件声明的第一个词就是完整实例名，不存在分开的“原语类型＋实例名”两个词。

```pulse
R_LOAD OUT 0 R=10
SENSOR_OUT VOUT V OUT 0
EVENT_CLK CLK MODE=PERIODIC PERIOD=10u START=0
```

不得写成 `R R_LOAD OUT 0 R=10`。

识别顺序使用已知最长前缀：`SENSOR`、`EVENT`、`MATH`、`CMP`、`SEL`、`INT`、`REG`、`SW`、`R`、`C`、`L`、`V`、`I`，以及子电路实例前缀 `X`。例如 `REG_GATE` 为 REG，不是 R；`CMP_HIGH` 为 CMP，不是 C。

建议实例名使用 `R_LOAD`、`C_OUT`、`L_TANK`、`SW_HIGH`、`MATH_ERROR`、`X_RECT` 形式。

### 3.3 行、注释与选项

- 一个逻辑语句可以占多行；续行必须以 `+` 开头。
- 去除行首空白后，以 `*` 开头的整行是注释。没有行尾注释语法；不得依赖 `;`、`//` 或 `#` 注释代码块中的内容。
- 位置参数之间用空白分隔。选项采用 `KEY=value`，等号两侧不得插入把它拆成多个词的空白。
- 数组、端口对及 `{...}` 内的空白不拆开该参数。
- 同一语句不得重复同名选项；不得使用本标准未列出的选项。

```pulse
* 一个含续行的耦合电感
L_COUP (P 0) (S 0) L_MATRIX=[[64u,31.99968u],[31.99968u,16u]]
+ IC_I=[0,0]
```

### 3.4 数值与单位

基础单位为 SI：秒、伏、安、欧姆、法拉、亨利、电荷库仑、磁链伏秒。数值不带单位文字。

支持十进制、科学计数法及下列倍率后缀：

| 后缀 | 倍率 | 例子 |
|---|---:|---|
| `T` | 1e12 | `1T` |
| `G` | 1e9 | `1G` |
| `Meg`、`meg`、`MEG` | 1e6 | `1Meg` |
| `k`、`K` | 1e3 | `10k` |
| `m` | 1e-3 | `20m` |
| `u` | 1e-6 | `10u` |
| `n` | 1e-9 | `15n` |
| `p` | 1e-12 | `1p` |
| `f` | 1e-15 | `10f` |

后缀大小写按表解释。单独 `M` 不合法；微单位必须写 ASCII `u`，不得写 `µ`。`10uF`、`300kHz`、`20mOhm` 均不合法。应写 `10u`、`300k`、`20m`。所有数值必须有限，不允许 NaN、Inf 或十六进制数值。

## 4. Parameters 与固定表达式

Parameters 中仅允许 `.PARAM`：

```pulse
.PARAM VIN=400
.PARAM FS=300k
.PARAM TS={1/FS}
.PARAM TON={0.48*TS}
.PARAM PI=3.141592653589793
```

每行定义一个参数。参数名不得重复；只能引用前文已经定义的参数，不允许引用尚未定义的参数。

固定表达式支持数值、已定义参数、括号、一元正负号和 `+ - * /`。不得使用函数、幂运算符、动态信号或内置常量。`PI` 必须自行定义；`sqrt()`、`sin()`、`^` 不是固定表达式语法。

除零、未定义参数以及非有限结果不合法。

元件参数、矩阵元素和表点可以使用 `{固定表达式}`：

```pulse
R_LOAD OUT 0 R={VIN/10}
EVENT_CLK CLK MODE=PERIODIC PERIOD={TS} START=0
```

参数在解析时冻结。引用全局参数应使用 `{PARAM_NAME}`；复合固定运算应放在 `{...}` 中。`MATH` 中的运行时信号与 `.PARAM` 是不同对象。

极小时间偏移不得通过让非零项在浮点加法中被吞掉来表达。需要独立延时时应使用 EVENT 的 DELAY 语义，而不是假定 `{大时间+极小偏移}` 总能保留全部信息。

## 5. 电域、数域与方向

### 5.1 电域

R、C、L、V、I、SW 的电端口连接节点。普通两端元件的参考电压为首节点电压减末节点电压，参考支路电流从首节点流向末节点。

```pulse
R_LOAD A B R=10
```

这里参考电压为 `V(A)-V(B)`，参考电流为 A→B。V 源的电流也采用此参考方向；供电状态下它可以为负。

### 5.2 数域类型

| 类型 | 含义 | 典型来源 |
|---|---|---|
| REAL | 连续或事件间保持的实数值 | SENSOR、MATH、INT、REAL REG |
| BOOL | 持续存在的 0/1 逻辑值 | CMP、BOOL REG、BOOL SEL |
| TRIG | 某时刻/微步的一次触发 | EVENT |

BOOL 与 TRIG 不可互换。SW 的控制端需要 BOOL，REG 的触发端需要 TRIG。TRIG 不是可以持续保存的数据，不能直接作为 REG 数据或 SW 控制。

类型通常自动推断。有歧义时可以在数域端口写 `REAL::NAME`、`BOOL::NAME`、`TRIG::NAME`。该前缀是类型约束，不会创建新信号，也不会进行类型转换。输出通道使用去掉类型前缀后的名称。

REAL 输入可以使用数值字面量，BOOL 输入的字面量仅允许 `0`、`1`；TRIG 必须由 EVENT 驱动，不能用常数代替。

### 5.3 保持值

REG 输出、固定常量，以及仅由保持输入构成的组合运算结果，属于事件间保持值。SENSOR 读取的连续电压电流、INT 状态通常不是保持值。

没有驱动、多驱动、电数域同名、类型冲突或不能消除的类型歧义不合法。连续仿射关系可以联合求解；无状态离散组合反馈环不合法，REG 可以提供离散存储。

## 6. 十三种原语总表

下表中的名称均为完整实例名；`N+ N-` 表示有序电端口，OUT/IN 等表示数域端口。

| 原语 | 规范语法 | 语义与类型 |
|---|---|---|
| R | `R_ID N+ N- R=value` 或 `IV_TABLE=table` | 电阻/单调 PWA I-V |
| C | `C_ID N+ N- C=value IC_V=value` 或 `QV_TABLE=table` | 电容；保存电荷 |
| L | `L_ID N+ N- L=value IC_I=value`；另有 PHII_TABLE、L_MATRIX | 电感；保存磁链 |
| V | `V_ID N+ N- DC=value` 或 `V_ID N+ N- REAL_IN` | 独立或实数控制电压源 |
| I | `I_ID N+ N- DC=value` 或 `I_ID N+ N- REAL_IN` | 独立或实数控制电流源 |
| SW | `SW_ID N+ N- BOOL_GATE RON=value ROFF=value` | 有限导通/阻断电阻 |
| SENSOR | `SENSOR_ID OUT V N+ N-` 或 `SENSOR_ID OUT I BRANCH [PORT=n]` | 电域观测输出 REAL |
| MATH | `MATH_ID OUT = affine_expr`，或按第 8 节 OP 形式 | REAL 运算 |
| CMP | `CMP_ID OUT IN OP=GE THRESHOLD=value` | REAL→BOOL 比较器 |
| SEL | `SEL_ID OUT SELECT FALSE_VALUE TRUE_VALUE` | BOOL 选择；数据为 REAL 或 BOOL |
| INT | `INT_ID OUT DERIVATIVE IC=value` | REAL 连续积分器 |
| REG | `REG_ID OUT DATA TRIGGER IC=value`，或 MODE=SR | REAL/BOOL 采样保持或 BOOL SR 存储 |
| EVENT | `EVENT_ID OUT MODE=...` | 输出 TRIG；四种模式见第 9 节 |

只有这十三种求解原语。`X` 是子电路实例前缀，不是第十四种原语。二极管、MOS、整流桥、驱动器、变压器等组合元件使用原语和 SUBCKT 表示，不得自行添加 `D`、`MOS`、`K`、`PWM`、`TRIG` 等原语。

## 7. 电域原语的完整规则

### 7.1 R

```pulse
R_LOAD A B R=10
R_PWA A B IV_TABLE=[(-2,-2m),(0,0),(2,20m)] RANGE=ERROR
```

`R` 必须严格正且有限。R 与 IV_TABLE 二选一。R 无初始状态。

IV_TABLE 点为 `(电压,电流)`。参考方向按第 5 节。

### 7.2 C

```pulse
C_OUT A B C=10u IC_V=0
C_PWA A B QV_TABLE=[(-1,-2u),(0,0),(1,3u)] IC_Q=0 RANGE=ERROR
```

C 与 QV_TABLE 二选一；线性 C 必须严格正且有限。表点为 `(电压,电荷)`。

`IC_V` 与 `IC_Q` 最多选择一个，不允许同时给出，即使两者数值看起来相容。IC_V 按本构曲线换算成电荷；未给初值时保存状态默认是 **零电荷**，不是对任意偏置曲线都默认零电压。

### 7.3 单支路 L

```pulse
L_TANK A B L=20u IC_I=0
L_PWA A B PHII_TABLE=[(-1,-2u),(0,0),(1,3u)] IC_PHI=0 RANGE=ERROR
```

L 与 PHII_TABLE 二选一；线性 L 必须严格正且有限。表点为 `(电流,磁链)`。

`IC_I` 与 `IC_PHI` 最多选择一个。IC_I 通过本构曲线换算为磁链；未给初值时默认为零磁链。

### 7.4 多绕组 L_MATRIX

```pulse
L_COUP (P1 P2) (S1 S2)
+ L_MATRIX=[[64u,31.99968u],[31.99968u,16u]]
+ IC_I=[0,0]
SENSOR_IP IP I L_COUP PORT=1
SENSOR_IS IS I L_COUP PORT=2
```

- 每组 `(首节点 末节点)` 是一个绕组，顺序确定端口号，从 1 开始。
- 矩阵必须为与绕组数相同维数的对称正定矩阵，元素使用亨利。
- 主对角为自感，非对角为带符号互感；互感符号必须与绕组端序及点标记一致。
- 本语法直接填写互感矩阵，不使用独立耦合系数元件。
- `IC_I=[...]` 或 `IC_PHI=[...]` 的长度必须等于绕组数，二者互斥；默认全零磁链。
- L_MATRIX 不得与 L 或 PHII_TABLE 同时使用。
- L_MATRIX 只定义线性耦合，未定义多绕组非线性磁芯模型。

### 7.5 PWA 表的共同规则

IV_TABLE、QV_TABLE、PHII_TABLE 至少有两个点。横坐标和纵坐标必须分别严格递增，故每段斜率严格为正。点间使用连续线性插值；不得用重复横坐标、平坦段、负斜率或跳跃点表达其他模型。

`RANGE=ERROR` 为默认值，超出表范围报告错误。`RANGE=EXTEND` 使用端部线段外推。RANGE 只能用于具有 PWA 表的 R/C/L，不能用于普通线性参数或 L_MATRIX。

### 7.6 V、I

```pulse
V_BUS VIN 0 DC=400
I_BIAS 0 OUT DC=2m
V_CTRL DRV 0 VDRIVE
I_CTRL A B ICMD
```

DC 固定值与第三个 REAL 控制端二选一，不得同时提供。受控输入为电压值或电流值本身，不隐含增益。ESR、内阻等使用单独 R 元件，没有 `ESR=` 源选项。

### 7.7 SW

```pulse
SW_HIGH VIN SW GATE RON=20m ROFF=1Meg
```

RON、ROFF 均必须显式提供、严格正且有限。GATE 为 BOOL：1 选择 RON，0 选择 ROFF。语法不强制 ROFF 大于 RON，也没有无穷电阻或零电阻特殊值。

SW 本身只定义该电阻关系，不包含体二极管、Coss、栅电荷、死区、开关延时或电流斜坡。所需结构应通过其他原语及 SUBCKT 明确定义，不能使用不存在的 SW 选项暗示这些特性。

### 7.8 SENSOR

```pulse
SENSOR_V VAB V A B
SENSOR_I IL I L_TANK
SENSOR_IP IP I L_COUP PORT=1
```

输出均为 REAL。V 模式得到 `V(A)-V(B)`；I 模式读取已命名物理支路的参考电流，不新增测量支路。

单支路的 PORT 默认 1；多绕组 L 必须显式指定合法整数 PORT。V 模式不允许 PORT。

电流目标必须是可识别的物理支路，例如 `L_TANK` 或 `X_D1/SW_PATH`；节点名、任意导线、整个 `X_D1` 组合元件名不是默认可用的支路电流引用。

## 8. 数域原语

### 8.1 连续仿射 MATH

```pulse
MATH_ERROR ERROR = {VREF} - VFB
MATH_SUM SUM = 2*X - Y/4 + 0.5
MATH_CONST ONE = 1
```

表达式支持 REAL 信号、数值、冻结参数、括号及 `+ - * /`；化简后必须是固定系数乘各信号再加常数。乘法至少一侧为固定常量，除法分母必须是非零固定常量。

以下不是合法仿射表达式：`X*Y`、`X/Y`、`SIN(X)`、`X^2`。即使 X、Y 来自 REG，在此表达式语法中也不能把两个运行时信号的乘法当成固定参数运算。

表达式读取数域 REAL；不得把电气节点名或输出选择器 `V(A)`、`I(L1)` 当作表达式信号。应先通过 SENSOR 输出数域信号。

### 8.2 保持输入 MATH 操作码

| OP | 语法 | 语义 |
|---|---|---|
| MUL | `MATH_P P A B OP=MUL` | A×B |
| DIV | `MATH_Q Q A B OP=DIV` | A/B，B 不得为零 |
| SIN | `MATH_S S A OP=SIN` | 正弦，输入弧度 |
| COS | `MATH_C CVAL A OP=COS` | 余弦，输入弧度 |
| SQRT | `MATH_R ROOT A OP=SQRT` | 平方根，A≥0 |
| POW | `MATH_W W A OP=POW EXPONENT=2` | 固定指数幂 |
| EXP | `MATH_E E A OP=EXP` | 自然指数 |
| LOG | `MATH_L LOGVAL A OP=LOG` | 自然对数，A>0 |
| ATAN2 | `MATH_A ANGLE Y X OP=ATAN2` | atan2(Y,X)，两输入不得同时为零 |

这些操作的全部动态输入必须为 **事件间保持的 REAL**。POW 只带一个数据输入，指数由固定 EXPONENT 提供。结果必须有限且满足实数定义域。不得用这些操作码对连续 SENSOR/INT 信号直接实现连续非线性方程。

合法采样功率片段：

```pulse
REG_V VSAMPLE VFB CLK IC=0
REG_I ISAMPLE IL CLK IC=0
MATH_POWER POWER VSAMPLE ISAMPLE OP=MUL
```

片段中的 VFB、IL、CLK 由所在完整网表定义。

### 8.3 CMP

```pulse
CMP_HIGH HIGH VFB OP=GE THRESHOLD=80
```

输入为 REAL，输出为 BOOL。OP 必须为 GT、GE、LT、LE；THRESHOLD 为固定值，必须给出。没有 EQ、NE、动态阈值输入或隐含滞回选项。

动态两信号比较可先建立仿射差值，再与固定零阈值比较。连续信号位于边界时需要事件方向及初始化语义，不能把 OP=GE 理解为任意数值不确定情况下都强行导通。

### 8.4 SEL

```pulse
SEL_CMD VDRIVE GATE 0 10
SEL_NOT BOOL::NOT_GATE GATE 1 0
```

位置参数顺序固定为 **OUT、SELECT、FALSE_VALUE、TRUE_VALUE**。SELECT 为 BOOL；OUT 与两个数据输入必须同为 REAL 或同为 BOOL。SEL 不接受 TRIG 数据，不使用 OP 选项。

### 8.5 INT

```pulse
MATH_D DX = 1000*(VIN_SENSE-X)
INT_FILTER X DX IC=0
```

含义为 `dX/dt=DX`，X、DX 为 REAL，IC 默认 0。INT 不含 RESET、LIMIT 等选项，不能通过 REG 改写其连续状态。常量输入允许写作 `INT_CLOCK CLOCK 1 IC=0`。

## 9. REG、EVENT 与触发语义

### 9.1 REG 采样保持

```pulse
REG_SAMPLE REAL::VSAMPLE VFB CLK IC=0
REG_BOOL BOOL::QSAMPLE GATE CLK IC=0
```

语法为 `REG_ID OUT DATA TRIGGER [IC=value]`。OUT 与 DATA 同为 REAL 或 BOOL，TRIGGER 为 TRIG。没有触发时保持旧值；触发时读取本微步更新前的 DATA 快照。IC 默认 0，BOOL 初值只能为 0 或 1。

普通采样 REG 不填写 MODE、SET、RESET、PRIORITY。

### 9.2 REG SR 模式

```pulse
REG_GATE GATE MODE=SR SET=ON RESET=OFF PRIORITY=RESET IC=0
```

OUT 为 BOOL，SET 与 RESET 必须为 TRIG，二者及 PRIORITY 必须显式给出。PRIORITY 只能为 SET 或 RESET，同微步二者同时到达时按该值决定。没有事件时保持；IC 默认 0。

### 9.3 EVENT 模式与允许选项

| MODE | 规范语法 | 允许选项及默认 |
|---|---|---|
| AT | `EVENT_ON ON MODE=AT AT=0` | MODE、AT；AT 必须给出且≥0 |
| PERIODIC | `EVENT_CLK CLK MODE=PERIODIC PERIOD=10u START=0` | MODE、PERIOD、START；PERIOD>0，START 默认 0 且≥0 |
| EDGE | `EVENT_RISE RISE MODE=EDGE SOURCE=HIGH EDGE=RISE` | MODE、SOURCE、EDGE；SOURCE 为 BOOL；EDGE 为 RISE/FALL/BOTH |
| DELAY | `EVENT_OFF OFF MODE=DELAY SOURCE=CLK DELAY=4u POLICY=TRANSPORT` | MODE、SOURCE、DELAY 或 DELAY_INPUT、POLICY、CANCEL |

所有 EVENT 输出为 TRIG。各模式只接受所在行列出的选项，例如 AT 不接受 PERIOD，PERIODIC 不接受 CANCEL。

PERIODIC 在 `START+n*PERIOD`、n=0,1,2… 时触发。EDGE 观察 BOOL 的改变，不是在信号保持高电平时反复触发；单独给出初始高电平不等于发生了一次上升沿。

### 9.4 DELAY

SOURCE 为 TRIG。固定 `DELAY=value` 与动态 `DELAY_INPUT=REAL_SIGNAL` 必须二选一。

```pulse
EVENT_OFF OFF MODE=DELAY SOURCE=CLK DELAY_INPUT=TON POLICY=REPLACE CANCEL=CANCEL_OFF
```

- 延时必须非负且有限；动态输入必须是事件间保持的 REAL。
- SOURCE 到达时读取并锁存本微步快照中的延时。后来 TON 改变，不修改已经排入队列的截止时刻。
- POLICY 默认 TRANSPORT：每次 SOURCE 均保留其新安排。
- REPLACE：新安排使该 EVENT 先前仍 pending 的安排失效。
- CANCEL 必须为 TRIG，使该 EVENT 仍 pending 的安排失效。它不撤销已到期并进入当前触发批次的事件。
- 同微步 CANCEL 与 SOURCE 同到达时，先取消旧 pending，再依据 SOURCE 安排新的事件。
- 零延时合法，产生同一物理时刻的下一微步触发，不把物理时间增加一个 dt。

### 9.5 同刻读写

一个微步中的 REG、DELAY 输入使用同一更新前快照；语句在 Network 中的排列顺序不决定先后。

若 CLK 同时更新 TON 寄存器并触发 `DELAY_INPUT=TON`，当前次延时读取更新前 TON。新提交状态造成的边沿可以在同一物理时刻的后续微步继续传播。未完成事务出现错误时不能把部分寄存器、部分队列更新当成成功提交。

## 10. SUBCKT 与层级

```pulse
.SUBCKT LOWPASS IN OUT
MATH_D DX = 1000*(IN-OUT)
INT_STATE OUT DX IC=0
.ENDS LOWPASS

X_FILTER VIN_SENSE VFILTER LOWPASS
```

定义语法为 `.SUBCKT NAME FORMAL_PORT...`，至少一个形式端口；结束必须为匹配名称的 `.ENDS NAME`。定义不能直接嵌套，但可以在定义体中实例化其他子电路。前后定义顺序不决定能否引用；直接或间接递归均禁止，即使该定义没有被顶层使用。

实例语法为 `X_ID ACTUAL_PORT... SUBCKT_NAME`，最后一个词为定义名，实际端口数量和顺序必须与形式端口一致。不得写 `X X_ID ...`，不得省略定义。

子电路端口可连接电气节点或数域信号，类型由展开后的用法确定。

展开规则：

1. 形式端口逐位置映射到实际名称。
2. `0` 始终是全局电气地。
3. 内部节点、信号和实例加实例路径前缀；不同实例的内部名称隔离。
4. 内部支路引用、MATH 本地名称及 SOURCE/SET/RESET/CANCEL/DELAY_INPUT 等信号引用随作用域展开。
5. 全局 `.PARAM` 使用同一个冻结参数表。没有局部 `.PARAM`、实例 `PARAMS:` 或参数覆盖语法。

例如内部 `SW_PATH` 在 `X_D1` 实例中成为 `X_D1/SW_PATH`，内部 ON 信号成为 `X_D1/ON`。在子电路内部应通过本地名及形式端口建立表达式，不应手工拼接外部绝对层级名称。

组合元件的器件方程由其 SUBCKT 内容定义，名称本身不添加任何隐含物理特性。

## 11. Simulation 与输出通道

### 11.1 TRAN

```pulse
.TRAN T_END=5m SAVE_DT=100n
```

只接受 T_END、SAVE_DT，二者为正且有限的固定值；同一文件最多一条 TRAN。仿真起点为 0，没有 T_START、MAX_STEP、RTOL、ATOL 或 T_ATOM 选项。

一个自包含网表应明确提供一条含两项的 TRAN。省略其中配置的文件必须由外部运行配置补足，不能独立确定一次运行。外部运行配置可以覆盖这两项。

SAVE_DT 是输出采样间隔，不是器件开关时间，也不是事件定位步长。V1.15 默认原子时间为 10 fs，独立于 SAVE_DT，原子时间由运行配置提供而非本节语法。

### 11.2 SAVE

同一文件最多一条 SAVE，选择器之间用空白分隔：

```pulse
.SAVE V(N8) I(L3) I(LCOUP_K1,1) G1 G2 X_D1/ON
```

| 形式 | 含义 |
|---|---|
| 省略 SAVE | 输出全部已注册通道，并保留全部事件日志 |
| `.SAVE *` | 与全输出一致，星号必须单独使用 |
| `.SAVE` | 不选择模拟/BOOL 通道及 TRIG；仍有时间数据、报告及必要的根事件记录 |
| `.SAVE name...` | 只选择列出的通道；TRIG 选择还影响日志中的 TRIG 条目 |

合法通道名称：

- `V(NODE)`：非地节点对地电压。
- `I(BRANCH)`：单支路参考电流。
- `I(MULTIPORT_L,n)`：第 n 绕组参考电流。
- REAL/BOOL 信号的展开名称，如 `LEGACY_L1_CURRENT`、`G1`、`X_D1/ON`。
- EVENT 的 TRIG 名称，如 `CLK`，用于选择相应事件记录，不形成持续数值波形。

选择器必须准确匹配已存在的注册名称，不使用类型前缀。不得假定 `V(A,B)`、`V(0)`、`I(X_D1)` 或任意通配模式有效。差分电压应由 SENSOR 输出一个 REAL 信号，再选择该信号。

TRIG 与 ROOT 事件记录不是同一种记录；SAVE 对 TRIG 的筛选不表示删除所有内部根事件。

## 12. Layout

Layout 必须为合法 JSON 对象。最小值为 `{}`；建议使用：

```json
{"version":"1.1","components":{},"wires":[]}
```

布局字段仅供展示，不参与电气连通、器件参数、方程及事件语义。空布局合法。修改图形不能代替修改 Network；Network 中不存在的连接不能由 wires 隐式补出。

## 13. 结构文法摘要与封闭选项表

### 13.1 文法摘要

以下 `RID`、`CID` 等代表符合第 3.2 节前缀规则的完整实例标识符，而不是独立的关键字。

```ebnf
file         = header, parameters, network, simulation, layout ;
parameter    = ".PARAM", IDENT, "=", fixed_expression ;
network_stmt = primitive | subckt | x_instance ;
primitive    = r_stmt | c_stmt | l_stmt | v_stmt | i_stmt | sw_stmt
             | sensor_stmt | math_stmt | cmp_stmt | sel_stmt | int_stmt
             | reg_stmt | event_stmt ;
subckt       = ".SUBCKT", IDENT, IDENT+, subckt_body*, ".ENDS", IDENT ;
subckt_body  = primitive | x_instance ;
x_instance   = XID, actual_port+, subckt_name ;
r_stmt       = RID, node, node, option+ ;
c_stmt       = CID, node, node, option+ ;
l_stmt       = LID, (node, node | winding+), option+ ;
winding      = "(", node, node, ")" ;
v_stmt       = VID, node, node, ("DC=", fixed_value | real_input) ;
i_stmt       = IID, node, node, ("DC=", fixed_value | real_input) ;
sw_stmt      = SWID, node, node, bool_input, "RON=", fixed_value,
              "ROFF=", fixed_value ;
sensor_stmt  = SENSORID, output, ("V", node, node | "I", branch, ["PORT=", integer]) ;
math_stmt    = MATHID, output, "=", affine_expression
             | MATHID, output, real_input+, "OP=", function, option* ;
cmp_stmt     = CMPID, output, real_input, "OP=", compare, "THRESHOLD=", fixed_value ;
sel_stmt     = SELID, output, bool_input, data_input, data_input ;
int_stmt     = INTID, output, real_input, ["IC=", fixed_value] ;
reg_stmt     = REGID, output, data_input, trig_input, ["IC=", fixed_value]
             | REGID, output, "MODE=SR", "SET=", trig_input,
               "RESET=", trig_input, "PRIORITY=", priority, ["IC=", fixed_value] ;
event_stmt   = EVENTID, output, "MODE=", event_mode, option* ;
option       = KEY, "=", value ;
node         = IDENT | hierarchical_name | "0" ;
compare      = "GT" | "GE" | "LT" | "LE" ;
priority     = "SET" | "RESET" ;
event_mode   = "AT" | "PERIODIC" | "EDGE" | "DELAY" ;
```

该摘要不覆盖全部类型和互斥条件；第 6—11 节的详细规则优先。SUBCKT 定义体允许原语和 X 实例，不允许再次声明 SUBCKT。位置参数必须保持规定顺序；同语句的命名选项相互顺序不影响语义，应将它们写在位置参数之后。

### 13.2 允许选项全集

| 原语 | 允许的选项名 |
|---|---|
| R | R、IV_TABLE、RANGE |
| C | C、QV_TABLE、RANGE、IC_V、IC_Q |
| L | L、PHII_TABLE、L_MATRIX、RANGE、IC_I、IC_PHI |
| V / I | DC |
| SW | RON、ROFF |
| SENSOR | PORT，仅 I 模式 |
| MATH | OP、EXPONENT，仅 POW 可有 EXPONENT |
| CMP | OP、THRESHOLD |
| SEL | 无 |
| INT | IC |
| REG | MODE、SET、RESET、PRIORITY、IC，按第 9 节区分两种形式 |
| EVENT | MODE、PERIOD、START、AT、SOURCE、EDGE、DELAY、DELAY_INPUT、POLICY、CANCEL，按模式限制 |

本标准没有 `.MODEL`、`.INCLUDE`、`.IC`、`.OPTIONS`、SPICE `PULSE(...)` 源或独立的二极管、MOS、耦合系数语句。不得把其他语言的关键字直接写入 PULSE 代码块。

## 14. 完整 LLC 示范文件

独立可运行文件：[PULSE_Netlist_Example_LLC.md](PULSE_Netlist_Example_LLC.md)。本节与该文件内容一致。

示例展示约 300 kHz 的半桥 LLC：400 V 输入、20 μH 串联谐振电感、15 nF 谐振电容、64/16 μH 耦合绕组、3.199968e-5 H 互感、10 μF 输出电容、1.6 Ω 负载；两路脉冲各导通 1.6 μs，相移约半周期。仿真终点 5 ms，输出间隔 100 ns。

二极管由 SUBCKT 中的 SENSOR/CMP/SW/SEL/受控电流源明确定义。其电流关系是 OFF 时 `v/Roff`，ON 时 `(v−Von)/Ron`。示例未给漏电斜率连续拼接追加修正，不得把这份模型解读为其他本构曲线。

示例的主开关使用 SW 及外接寄生电容；它表达这些语句规定的电阻与电容关系，不隐含完整栅电荷或指定通道关断斜坡。保留的参数名只是标识符；例如 `CR002_COSS` 在本文件中虽已定义，实际寄生电容语句使用的是 `CR002_CJ`，应以语句引用为准。

<!-- LLC_COMPLETE_EXAMPLE_BEGIN -->
````markdown
# PULSE Netlist v1.1

半桥 LLC 完整网表示例。

## Parameters
```pulse
.PARAM CR002_CJ=1p
.PARAM CR002_COSS=1p
.PARAM LEGACY_D1_VON=0.5
.PARAM LEGACY_D1_RON=100m
.PARAM LEGACY_D1_ROFF=1Meg
.PARAM LEGACY_D2_VON=0.5
.PARAM LEGACY_D2_RON=100m
.PARAM LEGACY_D2_ROFF=1Meg
.PARAM LEGACY_D3_VON=0.5
.PARAM LEGACY_D3_RON=100m
.PARAM LEGACY_D3_ROFF=1Meg
.PARAM LEGACY_D4_VON=0.5
.PARAM LEGACY_D4_RON=100m
.PARAM LEGACY_D4_ROFF=1Meg
.PARAM LEGACY_D5_VON=0.5
.PARAM LEGACY_D5_RON=10m
.PARAM LEGACY_D5_ROFF=1Meg
.PARAM LEGACY_D6_VON=0.5
.PARAM LEGACY_D6_RON=10m
.PARAM LEGACY_D6_ROFF=1Meg
.PARAM LEGACY_GATE1_PERIOD=3.3333333333333333e-06
.PARAM LEGACY_GATE1_START=0
.PARAM LEGACY_GATE1_TON=1.6e-06
.PARAM LEGACY_GATE2_PERIOD=3.3333333333333333e-06
.PARAM LEGACY_GATE2_START=1.6666666666666667e-06
.PARAM LEGACY_GATE2_TON=1.6e-06
```

## Network
```pulse
.SUBCKT LEGACY_DIODE_D1 A K
SENSOR_V VD V A K
CMP_ON ON VD OP=GE THRESHOLD={LEGACY_D1_VON}
SW_PATH A K ON RON={LEGACY_D1_RON} ROFF={LEGACY_D1_ROFF}
MATH_ZERO ZERO = 0
MATH_BIAS BIAS = {-LEGACY_D1_VON/LEGACY_D1_RON}
SEL_OFFSET OFFSET ON ZERO BIAS
I_OFFSET A K OFFSET
.ENDS LEGACY_DIODE_D1
.SUBCKT LEGACY_DIODE_D2 A K
SENSOR_V VD V A K
CMP_ON ON VD OP=GE THRESHOLD={LEGACY_D2_VON}
SW_PATH A K ON RON={LEGACY_D2_RON} ROFF={LEGACY_D2_ROFF}
MATH_ZERO ZERO = 0
MATH_BIAS BIAS = {-LEGACY_D2_VON/LEGACY_D2_RON}
SEL_OFFSET OFFSET ON ZERO BIAS
I_OFFSET A K OFFSET
.ENDS LEGACY_DIODE_D2
.SUBCKT LEGACY_DIODE_D3 A K
SENSOR_V VD V A K
CMP_ON ON VD OP=GE THRESHOLD={LEGACY_D3_VON}
SW_PATH A K ON RON={LEGACY_D3_RON} ROFF={LEGACY_D3_ROFF}
MATH_ZERO ZERO = 0
MATH_BIAS BIAS = {-LEGACY_D3_VON/LEGACY_D3_RON}
SEL_OFFSET OFFSET ON ZERO BIAS
I_OFFSET A K OFFSET
.ENDS LEGACY_DIODE_D3
.SUBCKT LEGACY_DIODE_D4 A K
SENSOR_V VD V A K
CMP_ON ON VD OP=GE THRESHOLD={LEGACY_D4_VON}
SW_PATH A K ON RON={LEGACY_D4_RON} ROFF={LEGACY_D4_ROFF}
MATH_ZERO ZERO = 0
MATH_BIAS BIAS = {-LEGACY_D4_VON/LEGACY_D4_RON}
SEL_OFFSET OFFSET ON ZERO BIAS
I_OFFSET A K OFFSET
.ENDS LEGACY_DIODE_D4
.SUBCKT LEGACY_DIODE_D5 A K
SENSOR_V VD V A K
CMP_ON ON VD OP=GE THRESHOLD={LEGACY_D5_VON}
SW_PATH A K ON RON={LEGACY_D5_RON} ROFF={LEGACY_D5_ROFF}
MATH_ZERO ZERO = 0
MATH_BIAS BIAS = {-LEGACY_D5_VON/LEGACY_D5_RON}
SEL_OFFSET OFFSET ON ZERO BIAS
I_OFFSET A K OFFSET
.ENDS LEGACY_DIODE_D5
.SUBCKT LEGACY_DIODE_D6 A K
SENSOR_V VD V A K
CMP_ON ON VD OP=GE THRESHOLD={LEGACY_D6_VON}
SW_PATH A K ON RON={LEGACY_D6_RON} ROFF={LEGACY_D6_ROFF}
MATH_ZERO ZERO = 0
MATH_BIAS BIAS = {-LEGACY_D6_VON/LEGACY_D6_RON}
SEL_OFFSET OFFSET ON ZERO BIAS
I_OFFSET A K OFFSET
.ENDS LEGACY_DIODE_D6
SW_S1 N5 N6 G1 RON=20m ROFF=1Meg
SW_S2 N6 0 G2 RON=20m ROFF=1Meg
R_ESR_VDC1 N5 LEGACY_VDC1_P R=1m
VDC1 LEGACY_VDC1_P 0 DC=400
R_ESR_C1 N7 LEGACY_C1_P R=100m
C1 LEGACY_C1_P N6 C=15n IC_V=0
R_ESR_L3 N7 LEGACY_L3_P R=20m
L3 LEGACY_L3_P N2 L=20u IC_I=0
X_D1 N3 N8 LEGACY_DIODE_D1
X_D2 N4 N8 LEGACY_DIODE_D2
X_D3 0 N3 LEGACY_DIODE_D3
X_D4 0 N4 LEGACY_DIODE_D4
R_ESR_C2 N8 LEGACY_C2_P R=30m
C2 LEGACY_C2_P 0 C=10u IC_V=0
R1 N8 0 R=1.6
X_D5 N6 N5 LEGACY_DIODE_D5
X_D6 0 N6 LEGACY_DIODE_D6
R_ESR_L1 N2 LEGACY_L1_P R=20m
R_ESR_L2 N3 LEGACY_L2_P R=20m
LCOUP_K1 (LEGACY_L1_P 0) (LEGACY_L2_P N4) L_MATRIX=[[6.3999999999999997e-05,3.1999680000000003e-05],[3.1999680000000003e-05,1.5999999999999999e-05]] IC_I=[0,0]
EVENT_GATE1_ON LEGACY_GATE1_ON MODE=PERIODIC PERIOD={LEGACY_GATE1_PERIOD} START={LEGACY_GATE1_START}
EVENT_GATE1_OFF LEGACY_GATE1_OFF MODE=DELAY SOURCE=LEGACY_GATE1_ON DELAY={LEGACY_GATE1_TON} POLICY=TRANSPORT
REG_GATE1 G1 MODE=SR SET=LEGACY_GATE1_ON RESET=LEGACY_GATE1_OFF PRIORITY=RESET IC=1
EVENT_GATE2_ON LEGACY_GATE2_ON MODE=PERIODIC PERIOD={LEGACY_GATE2_PERIOD} START={LEGACY_GATE2_START}
EVENT_GATE2_OFF LEGACY_GATE2_OFF MODE=DELAY SOURCE=LEGACY_GATE2_ON DELAY={LEGACY_GATE2_TON} POLICY=TRANSPORT
REG_GATE2 G2 MODE=SR SET=LEGACY_GATE2_ON RESET=LEGACY_GATE2_OFF PRIORITY=RESET IC=0
SENSOR_L1_I LEGACY_L1_CURRENT I LCOUP_K1 PORT=1
SENSOR_L2_I LEGACY_L2_CURRENT I LCOUP_K1 PORT=2
* 开关支路与二极管支路的显式寄生电容
C_SW_S1_PF N5 N6 C={CR002_CJ}
C_SW_S2_PF N6 0 C={CR002_CJ}
C_X_D1_PF N3 N8 C={CR002_CJ}
C_X_D2_PF N4 N8 C={CR002_CJ}
C_X_D3_PF 0 N3 C={CR002_CJ}
C_X_D4_PF 0 N4 C={CR002_CJ}
C_X_D5_PF N6 N5 C={CR002_CJ}
C_X_D6_PF 0 N6 C={CR002_CJ}
```

## Simulation
```pulse
.TRAN T_END=0.005 SAVE_DT=9.9999999999999995e-08
```

## Layout
```json
{"version":"1.1","components":{},"wires":[]}
```
````
<!-- LLC_COMPLETE_EXAMPLE_END -->
