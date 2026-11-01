# PULSE Solver V1.2pre

独立预览工程，基线为 Windows V1.15。目标是最小可验证的连续分段线性事件内核与 C 软件域；原 V1.15 工程和已验收证据保持只读。

## 已实现的范围

- 连续 PWA 本构转折点具有器件、分段、端点和方向身份。只有达到端点的候选才推进分段；窗口内尚未达到的端点保留实际先后并重新预测。
- 真正同时或在现有数值求值误差内不可分辨的转折点联合处理。检查使用根定位误差和原有守卫求值尺度，不增加固定电压或电流容差。
- 控制动作或另一转折点引起的代数 IV 区间失效，在同一有界联合求解中处理。q/phi/INT 物理状态保持。
- 五区网表：参数、仿真配置、电气连接、虚拟 MCU 配置、代码。兼容原 v1.1 四区网表和十三原语。
- C 模块支持同目录多个 `.c` 文件或内嵌 C；支持独立实例状态、输入快照、REAL/BOOL 保持输出、周期触发、自预约执行、提交和回滚。
- 默认累计事务数不设上限；`--max-transactions N` 显式限制，`0` 表示不限。保留同刻微步、根搜索、联合求解及输出容量等独立保护。

## 构建与使用

Linux x86-64（原生 Ubuntu 或 WSL2 Ubuntu）：

```bash
sudo apt-get install -y build-essential cmake ninja-build python3 libssl-dev
./build_linux.sh
python3 scripts/build_software.py examples/software_rc/input.md --cc gcc
./build-linux/pulse-solver examples/software_rc/input.md --out reports/linux-software-rc
```

Linux 使用独立 `build-linux/`、ELF 求解器和 `.so` C 控制模块。
依赖、完整 C002 命令及平台边界见 [Linux 构建说明](docs/Linux_Build.md)；
实际 Windows/Linux 测试与未解决项见 [Linux 与 C002 报告](docs/reports/Linux_Port_and_C002_Benchmark.md)。

在本目录 PowerShell 中：

```powershell
.\build_windows.ps1
```

工具复用 `D:\codex\tool\pulse-win`。软件模块编译器与主程序使用同一套本机工具。

外部 C 文件的闭环示例：

```powershell
& 'C:\Users\49605\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' .\scripts\build_software.py .\examples\software_rc\input.md
.\build\pulse-solver.exe .\examples\software_rc\input.md --out .\out-software-rc
```

内嵌 C、自预约变载频和死区示例：

```powershell
& 'C:\Users\49605\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' .\scripts\build_software.py .\examples\software_gate\input.md
.\build\pulse-solver.exe .\examples\software_gate\input.md --out .\out-software-gate
```

C 接口见 [include/pulse/software.h](include/pulse/software.h)。程序源文件修改后需要重新编译模块；加载时校验 DLL/.so、源文件和实际依赖头文件的 SHA-256，拒绝使用过期模块。

## 网表结构

主标题为 `# PULSE Netlist v1.2pre`。五个必需区域按下列顺序出现，均使用 `pulse` 代码块；内嵌代码另外使用 `c` 代码块：

1. `## 参数域` / `## Parameters`
2. `## 仿真参数配置` / `## Simulation`
3. `## 电气域连接网表` / `## Electrical`
4. `## 虚拟MCU配置域` / `## MCU`
5. `## 代码域` / `## Code`

`MCU` 绑定 `PROGRAM`；`TASK` 绑定 MCU、C 入口、输入、输出、参数和触发源；`TIMER` 生成周期事件。软件声明编译为既有事件与保持输出绑定，C 算法通过软件运行层执行，不进入连续电路矩阵。

未标注类型的软件输出默认为 REAL，也可以显式使用 `BOOL::`。每个输出均须提供 `INIT_OUTPUTS`。输入在每次执行开始时取同一快照；同一微步中的任务先读取，再统一提交输出。程序需要相互依赖时，通过后续事件表达顺序。

文件名相对网表所在目录解析。`PROGRAM CTRL SOURCES=["controller.c","filter.c"]` 仅接受同目录 `.c` 文件名；头文件通过 `#include` 引用。

## 当前限制

- 每个虚拟 MCU 支持一个任务；可以创建多个 MCU 实例，共享同一份代码但保持独立状态。
- 原生模块 ABI 为 2，与宿主 C ABI 2 分别管理。持久状态最多 64 KiB/实例，使用可复制的无持久指针数据。持久可变全局变量不属于支持的状态契约。
- 当前 C 模块在宿主进程中运行，必须遵循接口并有界返回；未实现执行进程隔离、指令仿真或 MCU 指令周期计时。
- 任务可返回正的 `next_delay` 预约私有唤醒；外部定时器的周期时间不受影响。`trigger_flags` 区分外部触发和私有唤醒。当前尚未实现通用中断抢占和任意预约取消接口。
- 通用 ADC、DAC、PWM 外设原语尚未实现；示例中的互补门极、变载频和死区由 C 状态机及自预约事件生成。直接信号快照与量化 ADC 不是同一模型。
- 数域 CMP 继续使用已有控制阈值规则；本预览重点重构 PWA 转折点接受与联合本构处理。

## 验收

`ctest --test-dir build --output-on-failure` 包含转折点、软件域及超过 100,000 次正常事务的检查。

`scripts/validate_pre_cases.py` 保留第一阶段六个案例的数域控制基线。随后六个案例的控制算法均已迁移到真实 C 软件模块，网表与源码位于 [benchmarks/control_c_vs_plecs_20261027/cases](benchmarks/control_c_vs_plecs_20261027/cases)：每例 `input.md` 为五区网表，`controller.c` 为同目录引用源码，`v115.md` 为对照用的原控制域网表。

完整案例结果、保存的 PLECS 参考对比、基线不变性以及阶段结论见 [reports/STAGE_REPORT.md](reports/STAGE_REPORT.md)。旧版已知失败案例保留有效前缀，不能以运行完成代替准确性验收。


本轮采用新运行的 PLECS、冻结 V1.15 与 C 版 V1.2pre，按用户要求仅采用首轮单次完整测量。六例统计精度共通过 225/225 项，原始逐点误差另行保留；开关边沿的逐点差异不等于统计验收失败。完整时间表、精度图、计时范围与限制见 [六案例单次对比报告](benchmarks/control_c_vs_plecs_20261027/REPORT.md)。


A011 的 C 控制版现已完成原定 0.5 s，并通过原始 PLECS 三个窗口共 63/63 项统计检查。此次修复了近转折点求值一致性与候选分段闭合的验收顺序，同时修正 C 模板时钟同步。结果、单次用时及范围见 [A011 修复与验收报告](benchmarks/a011_fix_20261028/REPORT.md)；最终网表为 `benchmarks/a011_fix_20261028/case_clocked/input.md`。本轮仅复核 A011，其他案例未在新内核上回归。
