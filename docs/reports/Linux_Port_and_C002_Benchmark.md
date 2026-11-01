# Linux 平台移植与 C002 验证

日期：2026-11-01（Asia/Shanghai）。本报告记录实际证据，尚未完成最终验收。

## A. 平台移植

迁移前提交：`d4113718aa8186c64bb4894d5c3358124861819b`。
GitHub 全新检出，起始工作区干净；开发分支 `feature/linux-support`。
未修改原工作目录内的历史实验，也未修改 main。

| 文件 | 原因与范围 |
|---|---|
| src/software.cpp | Windows 保留 BCrypt/LoadLibraryExW/GetProcAddress/FreeLibrary；Linux 增加 OpenSSL EVP SHA256 和 dlopen/dlsym/dlclose；共享 manifest、ABI、调用、状态和调度代码 |
| src/pre_netlist.cpp | 按编译平台选择 .dll/.so，不修改网表语法 |
| scripts/build_software.py | 编译器目标选择扩展名；Linux PIC、未解析符号检查；保留 ABI 2、源码/头文件/二进制哈希及浮点参数 |
| CMakeLists.txt | Linux 链接 libcrypto、dl 和 C 测试需要的 libm；两平台注册相同软件域测试；测试开启时要求 Python |
| tests/software_domain.py | 保留全部原有断言，增加二进制篡改和 manifest ABI 检查 |
| tests/platform_probe.cpp | 记录实际 long double 精度，验证 SHA256 已知向量 |
| build_linux.sh | Linux 独立 Release/Ninja 构建及全部 CTest，输出 JUnit |
| scripts/run_validation.py | 可指定构建目录，Linux 默认 build-linux；去除旧机器 CTest 路径 |
| scripts/run_c002_linux.py | 原始案例校验、ELF64 检查、完整 0.3 s 执行、独立证据和墙钟记录 |
| scripts/compare_c002.py | 不改参考数据，核对参考哈希并比较完整区间 |
| .github/workflows/linux.yml | Ubuntu push/PR 单元测试，手动完整 C002 回归 |
| .gitignore、docs/Linux_Build.md | 排除 Linux 构建产物、记录依赖和使用方式 |

`include/pulse/software.h` 已有 POSIX 可见性声明，`software.hpp` 和
`apps/cli.cpp` 无需修改。没有改动事件发现/根定位、联合事件、原子时间、
NR/NC/NL、传播、矩阵指数、LU/QR、容差、状态坐标或物理参数。

## B. 编译验证

| 环境 | 构建 | CTest 总数 | 通过 | 失败 | 跳过 |
|---|---|---:|---:|---:|---:|
| 本机 Windows 11 x64，GCC 16.2.0，CMake/Ninja Release | 成功 | 24 | 24 | 0 | 0 |
| GitHub Actions Ubuntu 24.04 x64，Release | 成功 | 24 | 24 | 0 | 0 |
| 本机 WSL2 Ubuntu | 安装处理中，未运行 | — | — | — | — |

Ubuntu CI 验证提交：`111296f154741c588cc1db23490ca006d190ba05`。
[工作流及日志](https://github.com/Tuzki/PULSE-solver/actions/runs/41265253495)，
[JUnit、平台探针和软件域证据](https://github.com/Tuzki/PULSE-solver/actions/runs/41265253495/artifacts/13066744091)。
Windows CTest 墙钟 23.07 s；CI CTest 12.17 s。此处只是各自测试执行记录，
不能据此比较本地与 CI 性能。两端均实际执行了软件域 C 控制器测试。

测试包括 parser、compiler_diagnostics、time_origin、electrical_references、
C_ABI_compatibility、NPZ_compatibility、engineering_events、engineering_additional、
mode_cache、pre_kernel、software_domain、transaction_budget、a011_boundary、
a011_closure、event_retry_merge、a021_control_d、a021_control_dot、general_strategies、
a021_sampling、trajectory、strategy_transaction、phi_affine、group_latest 和新增 platform_probe。
未关闭或跳过任何现有 CTest。无失败原因可列；新增探针使总数从 23 增至 24。

Windows GCC 和 Ubuntu CI 探针均实测：指针 64 位，double 有效尾数 53 位，
long double 存储 16 字节、有效尾数 64 位、max_exponent=16384、epsilon≈1.0842e-19，
小端。没有假定 MSVC 具有同样精度；本次未验证 MSVC。

## C. C002 仿真

案例库固定提交：`13660577132de41c37c1c47576c02941d21c532a`。
原网表 SHA256：`83e90dbfd3b3d8b11532f7b2c4122b8dfa5cbb19eccdd28e56a3639318567894`。
原 controller.c SHA256：`778a443cbff27d997fb7fcaf91cd9776e5ccef0ab1f458142bfe914fa8b7da28`。
保留 T_END=0.3 s、SAVE_DT=0.2 us、控制器和初态。

实际 Linux C002 状态：**COMPLETED**。终止时间 **0.3 s**；有效 SAVE_DT **2e-7 s**；
事务数 **30,003**；C 控制任务调用 **30,000** 次；T_atom **1e-14 s**。
退出码 0，诊断为空，输入字节校验保持不变。
CI 墙钟 **31.291694855 s**，包含进程启动和结果写出，不含控制器编译。
这是 GitHub Actions Ubuntu 的结果，**不是本机 Linux 性能基线**。

[完整运行与比较工作流](https://github.com/Tuzki/PULSE-solver/actions/runs/41265610784)，
[运行报告、NPZ、事件记录及比较证据](https://github.com/Tuzki/PULSE-solver/actions/runs/41265610784/artifacts/13067009047)。
验证提交仍为 `111296f154741c588cc1db23490ca006d190ba05`；后续提交仅文档及回归路径。
Linux ELF 求解器 SHA256：`02c2c15055cf81c3ebe2bac6896bf39c9fa70aa44836e2fb4794dcc71d436bb5`；
Linux CTRL.so SHA256：`5cf597bb5c1043c953ad4855e3add8e5e5d281900c89120b6f22c90ab5730782`。
本次执行 Linux ELF 和 .so，没有 Wine 或 Windows 后端。

## D. 精度比较方法

`scripts/compare_c002.py` 校验案例库原 PLECS CSV 的 SHA256、时间单调性、
0–0.3 s 覆盖与有限值，读取 PULSE 原 NPZ。无时间平移或参考波形修改。
报告七通道完整参考采样网格上的 mean/rms/max（原通道 atol + 1%），
及逐点 RMSE/max_abs。这是明确的完整网格统计，区别于历史窗口验收；
1 us 参考输出无法解析所有开关边沿，不声称逐点误差即求解内核误差。
实际执行 21 项完整网格统计，**20 通过、1 失败**，未跳过。
失败项：CH003（Diode current）max，PLECS **15.364982074776727 A**，
PULSE **15.03870964050293 A**；允许差 **0.15374982074776725 A**，
实际差约 **0.326272434273797 A**。因此比较返回 1，工作流整体显示 failure；
求解完成与精度比较结果分开记录，不将工作流标为全通过。
逐点 RMSE：CH005 约 1.6222e-6 A、CH006 约 0.011716 V；
开关电压 CH002 约 111.425 V，原始比较 JSON 保留全部通道误差。
已用未修改的 d411371 Windows 基线重新运行相同原始 C002：COMPLETED，
0.3 s、30,003 事务，并使用同一比较脚本得到完全相同的 CH003 max 失败数值，
同为 20/21 通过。这项失败并非 Linux 平台新引入，不能据此放宽阈值。
Windows 基线运行证据在本机 `reports/c002-windows-baseline/`；其墙钟记录
43.9543425 s 仅用于记录该次复现，不能与 CI 31.291694855 s 作为速度比。
Windows 基线二进制 SHA256：`11588f926e180ee6f640642443307ce6cb774b6d6629606e1d7bebfb65554669`。
未改变算法、参考数据或阈值。

保存数据中的一个具体边沿诊断：PLECS CH003 最大值发生在 t=0.00219 s。
Windows 基线在同一时间保存 CH003≈-7.947e-7 A，而 CH005=15.3649845 A；
下一保存点 t=0.0021902 s，CH003=15.2987795 A。
PULSE 自身完整 0.2 us 保存网格的 CH003 最大值为 15.3042869568 A，
但将其按比较脚本原方法采样到 PLECS 的 1 us 网格，最大值变为上述 15.0387096405 A。
这些记录表明比较对开关边沿和保存网格敏感；仅作为差异诊断，
没有改用另一统计方法替换已失败的 21 项比较，也没有更改事件左右值语义。

## E. 环境安装

初始 Windows 未安装 WSL/Ubuntu；未发现 Docker/Podman 或已有远程 Linux 配置。
用户已明确授权启用 WSL2 所需系统功能和安装 Ubuntu，但禁止自动重启。
Ubuntu 目标磁盘位置为 `D:\WSL\Ubuntu`。WSL 系统组件由 Windows 管理。
安装日志保存在工作区 `wsl-setup/`，不上传系统安装程序和二进制产物。
本机 Linux 验证需在 WSL2 实际可用后继续。

## F. 未解决问题

1. 本机 WSL2 Ubuntu 安装尚未完成；WSL/VirtualMachinePlatform 功能已启用，
   DISM 返回 3010，明确需要用户手动重启，未自动重启。
2. 本机 Linux 编译、CTest 和实际精度探针尚未运行。
3. 原始 C002 已在 Linux CI 完成 0.3 s，仍缺本机 Linux 墙钟。
4. C002 完整网格精度比较有 CH003 max 一项失败，仍待归因；没有宣称精度全部通过。
5. MSVC 构建未验证；Windows 本次验证采用原有 GCC 工具链。
6. Windows 额外历史/PF 回归执行 20 例，17 完成、3 失败、0 跳过。
   `rectifier_pf`、`llc_pf`、`llc_100cycles_pf` 均在 t=0 报
   `MODEL_SINGULAR`，诊断为 descriptor has nonunique or unsupported higher-index dynamics。
   已从迁移前 d411371 原始源码重新编译 Windows 求解器，原样复现这三项失败。
   属于基线已有问题，本次不调整数值策略或模型来绕过。

### 既有失败的复现

在未修改的基线 d411371 上构建，使用相同 GCC 16.2.0：

```bash
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF
cmake --build build --target pulse-solver
build/pulse-solver.exe tests/cr002/fixtures/rectifier_pf.md --out reports/repro-rectifier
build/pulse-solver.exe tests/cr002/fixtures/llc_pf.md --out reports/repro-llc
build/pulse-solver.exe tests/cr002/fixtures/llc_100cycles_pf.md --out reports/repro-llc100
```

原始 fixture SHA256：

| fixture | SHA256 |
|---|---|
| rectifier_pf.md | e4f93e99534aea9465d7e6c8420f8121cceb35db40cb5dda8524835870567437 |
| llc_pf.md | 5020b77af8a8142202eef840939fa6ee077548981125d945ce8c8b3f9a6d5a9b |
| llc_100cycles_pf.md | 92c7909483346248c946f4c16e112f56dd595007999bed2b51583aab3d87bbe6 |

本机详细 ledger：`reports/linux-port-windows-validation/all_ledger.json`；
基线失败复现：`reports/baseline-failure-reproduction/`。这些是生成证据，不提交二进制或输出产物。
