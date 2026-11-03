# C/D 运行时重复计算审计工具

只用于 Linux x86-64、glibc、单线程 Release 审计。只累计调用、字节、完整输入重复数；不读时钟、不采样调用栈、不输出 CPU 或墙钟统计。若观测到多个线程、计数表溢出、原有计数不符或严格 PEVT 对照不符，拒绝验收。

正式 Git 求解器文件保持不变。prepare.py 将已冻结 C/D 原始源码复制到独立目录，再按唯一锚点安装计数语句；保留 Release 的优化和严格浮点选项。cow_value.hpp 仅将默认复制的同一共享指针操作展开以累计复制数；不改变对象布局、COW 条件或物理数据。Eigen Memory 的包装仅记录实际进入分配函数的上下文。

本机冻结目录为 /root/pulse-stage-c-20261103 与 /root/pulse-stage-d-20261104，源码 SHA 与报告中的两个提交核对。复现应使用新的空工作目录，并调整脚本中的冻结源码/模型路径：

    python3 prepare.py --work /root/cd-repeat-audit-20261104 --version C
    python3 prepare.py --work /root/cd-repeat-audit-20261104 --version D
    python3 calibrate.py
    python3 run.py --work /root/cd-repeat-audit-20261104 --model /root/stage-a-regression-20261103/model/netlist.md
    python3 verify_allocations.py --work /root/cd-repeat-audit-20261104 --model /root/stage-a-regression-20261103/model/netlist.md
    python3 analyze.py --work /root/cd-repeat-audit-20261104 --out REPORT_DIR --pins PINNED_SOURCES.json

PINNED_SOURCES.json 是从固定 Git 提交导出的 src、include、apps、CMakeLists 的逐文件 SHA256。原模型 .pulse_modules 必须已通过当前模块构建器生成；求解器原有 ABI 和 manifest 检查仍执行。

D1 使用相同计数方法，增加坐标绑定缓存命中/物化以及 A 行范数填充、复用、回退计数：

    python3 prepare.py --work /root/stage-d1-count-20261104 --version D1
    python3 calibrate.py --work /root/stage-d1-count-20261104 --versions D1
    python3 ../../stage_d1_validate.py --out /root/stage-d1-regression-20261104/validation

准备程序的 D1 源码默认取自 /root/pulse-stage-d1-20261104。最终正常 ELF 的分配总数与源码计数构建分开记录，D1 的通用比较函数不物化 Matrix，比较本身仍计数。

refine_paths.py 由准备程序调用，记录额外坐标转换、公开状态发布、批量信号读取及 Flow 的矩阵比较上下文；其单独执行入口只用于保留初次计数后的诊断扩展。最终安装的所有计数点均包含在 prepare/refine 两步中。

counters.cpp 使用固定数组归因调用路径，完整输入查重用带完整字节相等比较的表。查重工具本身的分配/释放、哈希及输出分配排除；不改变求解器缓存结果。Basis 身份键仅用于本例中由原有不淘汰值缓存固定生命周期的不可变对象，并和完整原始锚点/row 位组合。

API 次数的权威值来自 verify_allocations.py 对**未修改 Release ELF**的分配拦截。源码插桩会影响编译器合并分配/清零为 calloc、消除 free(NULL) 的机会，因此只用其 malloc/calloc 合计进行逻辑路径归因，并输出总量校核，不能拿插桩后的单独 malloc/calloc/free(NULL) 分布冒充原始 Release。

统计口径是计数库初始化后到退出输出前的公开 malloc/calloc/realloc/free 请求，包含初始化、计算、归档与清理；未覆盖 glibc 内部私有分配和直接 mmap。字节是累计申请量，realloc 计完整新请求大小，不是存活内存或 RSS。归因路径是安装计数的逻辑作用域，不是完整物理调用栈；构造函数初始化列表及按值参数的分配可能归到调用者。完整输入键只说明相同操作数，不能将不同新状态的合法检查当成重复。
