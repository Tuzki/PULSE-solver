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

当前 Linux C002 状态：**NOT_RUN**。实际终止时间、事务数、墙钟均暂无数据。
Ubuntu 单元测试中的 C 控制器执行成功不代表本案例已完成。
不得将 CI 中按设计未触发的手动 C002 job 标为仿真通过。

## D. 精度比较方法

`scripts/compare_c002.py` 校验案例库原 PLECS CSV 的 SHA256、时间单调性、
0–0.3 s 覆盖与有限值，读取 PULSE 原 NPZ。无时间平移或参考波形修改。
报告七通道完整参考采样网格上的 mean/rms/max（原通道 atol + 1%），
及逐点 RMSE/max_abs。这是明确的完整网格统计，区别于历史窗口验收；
1 us 参考输出无法解析所有开关边沿，不声称逐点误差即求解内核误差。
尚未执行 Linux C002 精度比较，未声明精度 PASS。

## E. 环境安装

初始 Windows 未安装 WSL/Ubuntu；未发现 Docker/Podman 或已有远程 Linux 配置。
用户已明确授权启用 WSL2 所需系统功能和安装 Ubuntu，但禁止自动重启。
Ubuntu 目标磁盘位置为 `D:\WSL\Ubuntu`。WSL 系统组件由 Windows 管理。
安装日志保存在工作区 `wsl-setup/`，不上传系统安装程序和二进制产物。
本机 Linux 验证需在 WSL2 实际可用后继续。

## F. 未解决问题

1. 本机 WSL2 Ubuntu 安装尚未完成；可能需要用户手动重启。
2. 本机 Linux 编译、CTest 和实际精度探针尚未运行。
3. 原始 C002 Linux 0.3 s、COMPLETED、事务数及本地墙钟仍待验证。
4. C002 Linux 精度比较尚未运行；不得以历史案例结果替代。
5. MSVC 构建未验证；Windows 本次验证采用原有 GCC 工具链。
6. 额外 `run_validation.py --suite all` 回归正在运行，结果待收集。
