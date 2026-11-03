#!/usr/bin/env python3
"""Publish compact, evidence-backed artifacts; retain large raw data locally."""
import argparse
import csv
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET


def fingerprint(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return {'path':str(p),'bytes':p.stat().st_size,'sha256':h.hexdigest()}


def main():
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--repo',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
    raw=a.raw;analysis=read(raw/'analysis-final/analysis.json');sampling=read(raw/'cpu-sampling-500ms/measurement.json');count_run=read(raw/'full-500ms/measurement.json');counts=read(raw/'full-500ms/counts.json');manifest=read(raw/'full-500ms/probes.json');alloc=read(raw/'full-500ms/allocations.json')
    baseline=read(a.repo/'docs/reports/stage_b_cow_20261103/EVIDENCE.json')['performance']['full_new']
    accepted=read(a.repo/'docs/reports/stage_c_20261103/EVIDENCE.json')['performance']['stage_c_measurement']
    funcs={q['label']:q for q in counts['probes']};N=159037
    assert sum(v['bindings'] for v in counts['observer_binding_identities'])==funcs['bind_observations']['entries']==377391
    assert funcs['flow_ctor']['entries']==478908 and funcs['flow_ctor']['context_entries']==357471
    assert all(q['map_errors']==q['collisions']==q['unmatched_returns']==0 for q in counts['probes'])
    assert all(q['entries']==q['returns'] for q,m in zip(counts['probes'],manifest) if m['timing'])
    assert alloc['slot_overflow']==0 and all(t['size_overflows']==0 for t in alloc['threads'])
    for name in ['MODULE_EXCLUSIVE.csv','BIND_BREAKDOWN.csv','NESTED_GROUPS.csv','OBSERVE_BREAKDOWN.csv','REPEAT_COST_CONTEXTS.csv']:
        shutil.copyfile(raw/'analysis-final'/name,a.out/name)
    svg=(raw/'analysis-final/FLAMEGRAPH.svg').read_text();svg=svg.replace('width="1600" height=', 'preserveAspectRatio="none" width="1600" height=',1);ET.fromstring(svg);(a.out/'FLAMEGRAPH.svg').write_text(svg,encoding='utf-8')
    with (raw/'analysis-final/FUNCTION_HOTSPOTS.csv').open() as f:hot=list(csv.DictReader(f))
    fields=[k for k in hot[0] if k!='representative_stack_leaf_to_root']
    with (a.out/'FUNCTION_HOTSPOTS.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(hot)
    (a.out/'TOP20_CALLSTACKS.md').write_text('# TOP20 实际物理函数调用栈\n\n'+'\n\n'.join(f"## {r['rank']}. {r['function']}\n\n```text\n"+r['representative_stack_leaf_to_root'].replace(' <- ','\n <- ')+'\n```' for r in hot[:20]),encoding='utf-8')
    with (a.out/'FUNCTION_COUNTS.csv').open('w',newline='') as f:
        fields=['label','function','calls','calls_per_transaction','context','context_calls','instrumented_inclusive_wall_seconds','instrumented_mean_wall_ns','paired_returns','errors']
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for q,m in zip(counts['probes'],manifest):
            w.writerow({'label':q['label'],'function':m['function'],'calls':q['entries'],'calls_per_transaction':q['entries']/N,'context':m['parent'] or '',
                        'context_calls':q['context_entries'],'instrumented_inclusive_wall_seconds':q['wall_ns']/1e9 if m['timing'] else 'not timed',
                        'instrumented_mean_wall_ns':q['wall_ns']/q['entries'] if m['timing'] and q['entries'] else 'not timed',
                        'paired_returns':q['returns'] if m['timing'] else 'not collected','errors':q['map_errors']+q['collisions']+q['unmatched_returns']})
    api=[];bins=[];free=free_null=0
    for t in alloc['threads']:
        api+=t['apis'];bins+=t['size_bins'];free+=t['free_calls'];free_null+=t['free_null']
    requests=sum(r['calls'] for r in api);requested=sum(r['requested_bytes'] for r in api)
    assert requests==559617285 and requested==68881827693
    with (a.out/'ALLOCATIONS.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['name','calls','requested_bytes','failures']);w.writeheader();w.writerows(api)
    with (a.out/'ALLOCATION_SIZE_BINS.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(bins[0]));w.writeheader();w.writerows(bins)
    with (a.out/'RESOURCE_COMPARISON.csv').open('w',newline='') as f:
        fields=['run','completion_wall_seconds','cpu_seconds','peak_rss_kib','scope'];w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for name,r,scope in [('Stage B COW',baseline,'saved unprofiled baseline'),('Stage C accepted',accepted,'saved unprofiled acceptance'),('Stage C CPU sampling',sampling,'perf 999 Hz plus syscall trace, no return probes or allocation observer'),('Stage C exact counters',count_run,'heavy paired probes plus allocation observer; not a speed benchmark')]:
            w.writerow({'run':name,'completion_wall_seconds':r['completion_wall_seconds'],'cpu_seconds':r.get('cpu_total_seconds',r.get('cpu_seconds')),'peak_rss_kib':r['peak_rss_kib'],'scope':scope})
    out=a.out
    top='\n'.join(f"| {r['rank']} | `{r['function'][:100]}` | {float(r['self_cpu_percent']):.2f}% | {float(r['total_cpu_percent']):.2f}% | {r['actual_calls']} |" for r in hot[:20])
    modules='\n'.join(f"| {r['module']} | {r['exclusive_cpu_percent']:.2f}% | {r['exclusive_cpu_seconds_estimate']:.3f} |" for r in analysis['modules'])
    bind='\n'.join(f"| {r['component']} | {r['cpu_seconds_estimate']:.3f} | {r['percent_within_bind']:.2f}% |" for r in analysis['bind_breakdown'])
    def csvrows(name):
        with (out/name).open() as f:return list(csv.DictReader(f))
    observe='\n'.join(f"| {r['component']} | {float(r['cpu_seconds_estimate']):.3f} | {float(r['percent_of_process']):.2f}% |" for r in csvrows('OBSERVE_BREAKDOWN.csv'))
    report=f'''# Stage C A010 500 ms：执行次数与 CPU 瓶颈剖析

固定代码：`f8138727a45f7213898a87b0a10c94a57eb33c04`，分支 `performance/stage-c-20261103`。采集日期 2026-11-03。未修改 src/include/apps/CMakeLists.txt、模型、控制器、容差或算法；本次只提交分析工具和报告。

## 结论

优先处理反复创建绑定辅助数据、矩阵缓冲和小对象分配，其次处理 observe 投影准备与重复兼容/归档比较。临时 Flow 构造本体不是最大的热点：其在 observe 内约 **0.762 CPU s / 1.21%**；同一路径的局部多项式准备约 **2.365 s**、绑定 COW 复制约 **1.741 s**。直接优化构造次数，不能把整个 observe 的收益都算进去。

分配器独占约 **23.44% / 14.782 CPU s**；bind 连同所有子调用约 **28.15% / 17.750 CPU s**，两者重叠，不能相加。T128 与来源运算独占约 **1.84% / 1.163 s**。实际写系统调用仅约 **0.161 s**；PEVT 内存编码、查找、比较与分配和真正磁盘写出分开计量。

## 方法、精度与测量开销

Linux x86-64，WSL2 Ubuntu 24.04，Ryzen 5 6600H，GCC 13.3。Release 保留 `-O3 -DNDEBUG -ffp-contract=off -fno-fast-math` 和 EIGEN_DONT_PARALLELIZE；只为副本增加 `-g1`，其 .text 与验收版逐字节相同，SHA256 `d2e8a8803411b91ccbc5be1d788acbfbc2109b89c7424b9edc451eea046f3de9`。

采用两个互补的完整 500 ms 诊断通道，而不是混用受干扰的栈：

1. 精确计数：task-scoped eBPF 入口/返回聚合、observe 上下文和只读绑定身份统计、COW 真正分离分支计数、独立 LD_PRELOAD 分配观察器。全部配对探针零丢配、零重入冲突、零 map 错误。独立 100 次调用与嵌套调用校准通过。
2. 主要 CPU 归因：**不安装返回探针，不加载分配观察器**，perf cpu-clock 999 Hz、DWARF 32 KiB 栈，共 **61,912 样本**；另用 perf trace 统计 write/writev/fsync。返回探针会替换返回地址并截断 DWARF 外层栈，因此第一通道 1.8 GB 采样仅留作原始证据，不用于 Self/Total/火焰图。

函数 Self 只计栈顶；Total 每样本中同名物理函数去重后计一次，包含子调用。递归帧不重复叠加同一函数。各模块每个样本只分给一个类别，独占占比总和为 100%。绑定/observe 内部表是各自内部的分解，不能再与全局表相加。

调用次数是入口事件计数，样本数不是调用次数。优化后内联、未布点的函数明确标为未测；TOP20 中 libc/Eigen 等多数未独立布点，不能声称其调用次数已精确获取。函数平均 CPU 成本是独立 CPU 样本估计除以同输入完整运行的精确入口计数，不是精确逐次延迟。探针跨度包括调度与自身开销，另存 FUNCTION_COUNTS.csv，禁止当作纯 CPU 或与嵌套跨度相加。

早先提出的所有函数 CPU 时间相对统计误差 ≤1% **未达成，也不宣称达成**。CSV 附独立样本假设下的 95% Wilson 区间；它不覆盖采样相关性和系统偏差。按用户后续澄清，本轮以真实执行次数和重复比例为主要证据，时间用于排序；没有为追求小热点 1% 反复跑多轮。

## 资源与 61.60 s 基线

| 运行 | 完成墙钟 / s | CPU / s | 峰值 RSS / KiB |
|---|---:|---:|---:|
| Stage B COW，保存的未剖析基准 | 61.601002 | 62.19 | 1,162,312 |
| Stage C，保存的未剖析验收结果 | 57.716774 | 58.17 | 1,162,484 |
| 本轮独立 CPU 栈采样 | 62.099544 | 63.049700 | 1,162,484 |
| 本轮精确计数与分配统计 | 116.658169 | 117.978378 | 1,162,512 |

Stage C 的保存验收结果较 Stage B 快 6.31%；本轮带采样结果不能替代无剖析性能基准，更不能把计数通道的 116.66 s 解释成求解器退化。当前 CPU 样本给出较无剖析 Stage C 增加约 7.6% 的墙钟；计数通道的系统 CPU 达 42.694 s，开销很明显。

CPU 栈通道每 100 ms 读 /proc，共 618 个记录，观察到最大 **1 个目标线程**；分配观察器也仅记录 1 个分配线程。该内核缺少 /proc/PID/io，第一通道的监控因此未取得线程采样；已修正为可选 I/O 字段，使用第二通道完整线程记录和 perf trace 补足，未编造该字段。

## 精确执行次数与重复

完整运行 159,037 次事务、159,036 次根查询、26 次模态编译、477,111 次原方程检查。核心计数：

| 操作 | 完整执行次数 | 含义 |
|---|---:|---|
| observe | 472,296 | 每事务约 2.970 次 |
| Flow 两参数构造 | 478,908 | 含 observe 临时投影 |
| observe 内 Flow 构造 | **357,471** | 全部构造的 74.64%；observe 调用的 75.69% |
| bind_observations | **377,391** | 每事务约 2.373 次 |
| 只读 ObserverBinding 对象 | **26** | 精确地址聚合；总绑定次数校验一致 |
| 绑定路径 COW edit | 3,019,128 | 每次绑定正好 8 次编辑入口 |
| 绑定路径实际 COW 分离 | **377,391** | 每次绑定 1 次 |
| 全部已布点 COW 分离分支 | 734,886 | 其中非绑定 357,495 次；不是全部内联 COW 的泛化计数 |
| Mode 拷贝构造 | 969,125 | 不含未布点赋值或内联变体 |
| Flow compatible | 515,849 | 每事务约 3.244 次 |
| 二进制时间转十进制来源 | 285,107 | 每事务约 1.793 次 |
| PEVT equation 请求 / 比较 | 514,713 / 514,693 | 实际定义编码仅 20 次 |

26 个绑定对象只证明**静态绑定基础**反复使用，不代表它们的动态 held 输入完全相同。不能把 377,391 次矩阵更新都直接判为多余。

可明确定位的重复：`Assembler(...,false)` 每次绑定都会为同一个冻结 Model 的 **70 个 part** 重建 partidx。函数计数乘固定无提前退出的循环规模，推导为 **26,417,370 次索引插入迭代**；这是计数加源码固定循环推导，并非对每个循环回边单独布点。该路径不组装 A/F 等完整方程；避免误称其为 377,391 次重新因子分解。

observe 缓存未命中分支先复制 Mode，再经 COW 克隆包含所有映射的 ModeBinding，随后立即 clear maps、clear guards、替换为单个 OBSERVE row。完整运行 357,471 次进入构造分支，源码说明其整份映射复制随后被丢弃；这是值得重构的具体数据复制，不是仅因调用次数高而下结论。

## bind_observations 内部 CPU 分解

| 内部互斥类别 | 估计 CPU / s | 占 bind Total |
|---|---:|---:|
{bind}

依据真实物理调用栈、Eigen/COW/STL 函数和 DWARF 来源分类。矩阵类包含矩阵缓冲分配/复制；字符串类包含 map 节点生命周期，不能称为纯字符计算。COW 类包含其子调用。Assembler 构造在绑定上下文中约 **2.891 CPU s**；单纯模式 ID 格式化约 **1.273 s**，二者与内部表的其他类别存在包含关系，不可额外相加。

## observe 路径 CPU 分解

| 内部互斥类别 | 估计 CPU / s | 占全进程 |
|---|---:|---:|
{observe}

临时构造的精确入口/返回跨度合计 1.889809 s（重探针通道）；独立 CPU 栈估计 0.761745 s，约 **2.131 µs CPU/次**。两者测量口径和开销不同。更大的费用在前置 COW 和局部多项式准备；后者是否能共享必须保留 anchor、basis、行与误差界的完整语义。

## 模块独占 CPU

| 模块 | 独占 CPU | 估计 CPU / s |
|---|---:|---:|
{modules}

`mode_entry_and_compile_residual` 包含缓存路径后的状态坐标/矩阵进入工作，不能读作 26 次真正编译耗时。根搜索独占只含其自身，包含 Flow 求值时 Total 约 4.46%；closure Total 约 41.19%，扣除独立分类的子工作后自身约 4.90%。C 控制器包装 Data::call Total 约 14.22%，包含观测/兼容等，软件控制自身约 1.53%。

## TOP20 物理函数

| # | 函数（此处截短，完整名称及源码见 CSV） | Self | Total | 精确入口次数 |
|---:|---|---:|---:|---|
{top}

完整名称、实际源码、平均 CPU 成本、置信区间见 FUNCTION_HOTSPOTS.csv；真实栈见 TOP20_CALLSTACKS.md。Total 列不能相加。

## 内存与 I/O

公开分配 API 请求 **{requests:,} 次**、累计请求 **{requested:,} B（68.88 GB）**，失败 0；不是同时存活内存，也不是 RSS。malloc 497,793,125 次，calloc 61,824,119 次，realloc 41 次。free 共 {free:,} 次，其中 free(NULL) {free_null:,} 次；非空释放 559,617,242 次，与 malloc+calloc 请求量接近。请求量包含 realloc 的替换大小，不能直接当作新对象数。

观察器自检覆盖 9 个请求、787 字节。自检发现 reallocarray 会委托 realloc，已在工具中抑制嵌套重复计数；正式运行 reallocarray/memalign 等委托 API 次数均为 0，故此工具修正不影响已采集的 malloc/calloc/realloc 结果。保留了采集时动态库及其哈希，未偷偷替换原始证据。

分配器约占 14.782 CPU s；峰值约 1.11 GiB、分配失败为零，主要证据支持**分配/释放周转的 CPU 成本**，不支持“内存不足”。公开 API 之外的直接 mmap 等不计入请求统计。字节量没有按调用栈精确分配给每个模块，不能把采样百分比冒充各模块分配字节。

perf trace：writev 10 次、累计 160.667 ms；write 2 次、累计 0.153 ms，均零错误；未观察到 fsync/fdatasync。系统调用跨度不等于 CPU，也不等于数据已经持久化到物理盘。PEVT 数据文件约 162.84 MB，其编码和去重 Total 约 8.306 CPU s，明显不能全部归给磁盘。

## 优化排序、风险与验证

详见 OPTIMIZATION_PLAN.md。所有收益区间均为**估计**，未实现任何求解器优化；区间和模块占比存在重叠，不能直接相加。建议先做一项、核对精确次数和分配量下降，再核对完整 PEVT/数值行为，最后比较无剖析墙钟。

## 证据与限制

两条完整诊断运行均实际到 0.5 s / COMPLETED，保持全部 13 模拟/4 数字输出。PEVT 2–10 段记录数、长度、SHA256 及要求的全部数值统计，与 Stage C 验收版完全一致。本轮不重建波形、不重跑 PLECS。

原始文件留在 **/root/stage-c-cpu-profile-20261103/**：两个 perf.data、完整物理栈导出、计数、分配、I/O、线程记录、符号二进制与工具校准。EVIDENCE.json 列出实际命令、版本、机器及原始文件 SHA256。Git 仅保存工具、报告、CSV 和约 681 KiB 火焰图，不上传 GB 级采样、二进制或事件文件。

[交互火焰图](FLAMEGRAPH.svg) · [执行次数](FUNCTION_COUNTS.csv) · [资源比较](RESOURCE_COMPARISON.csv) · [绑定拆分](BIND_BREAKDOWN.csv) · [观测拆分](OBSERVE_BREAKDOWN.csv)
'''
    (out/'CPU_PROFILE.md').write_text(report,encoding='utf-8')
    plan='''# 实测驱动的优化顺序（仅建议，未修改求解器）

收益均为估计，不是实测优化结果。以约 58 s 未剖析 Stage C 为量级；各区间相互重叠，不能相加。

| 顺序 | 具体目标及实测证据 | 估计可省墙钟 | 风险 | 必须验证 |
|---:|---|---|---|---|
| 1 | 将 Assembler(false) 的 partidx 和固定驱动索引变为冻结 Model 的共享只读数据；377,391 次构造导致 26,417,370 次相同 part 插入，构造栈约 2.89 CPU s，并有 map/字符串/分配子成本。复用小型 scratch buffer，避免重复创建 map。 | 1–4 s | 低至中；实例生命周期、线程隔离、memo/visiting 不能误共享 | 循环次数降为每 Model 一次；请求数/字节降低；软件独立状态、六点回滚、来源取消故障、PEVT 2–10 完全一致 |
| 2 | observe 投影只持有需要的 row/basis/anchor 数据，避免完整 ModeBinding 克隆后清空 maps。357,471 次临时构造，投影前置 COW 约 1.74 CPU s；构造本体仅约 .76 s。研究共享同 anchor/basis 的 local_state 系数，相关路径另占约 2.36 s。 | 1–3 s | 中；continuation offset、guard/row、局部误差界、缓存失效语义 | observe miss/构造/分离次数实降；原浮点顺序、完整 17 路、事件流 SHA256、精确来源与故障回滚保持 |
| 3 | 基于不可变身份与完整版本证书复用 Flow 兼容、PEVT 定义等价结论；515,849 次 compatible，514,693 次归档比较却仅 20 次编码。memcmp Self 12.19%；在兼容路径的 memcmp 约 1.91 CPU s、归档路径约 2.38 s。 | 1–3 s | 中至高；动态 held 值、observer rows、guards、strategy 变化必须失效；不可按模式 ID 猜相同 | 人为改变每个相关字段均拒绝旧证书；缓存命中仍保留原残差检查；原接口失败语义、PEVT 哈希一致 |
| 4 | 缓存 ObserverBinding 真正静态的 A 绝对值、行范数、固定映射索引，复用矩阵临时存储。绑定矩阵类约 7.60 CPU s，但动态列确实会变化，不能整体删掉。 | .5–2 s | 中；Eigen 分块/归约顺序变化会破坏逐位结果 | 先测动态输入重复率；按旧表达式顺序产生相同字节；保留所有 residual/scale 检查，完整 case 回归 |
| 5 | 减少 Mode.id 和归档键的临时字符串；绑定格式化约 1.27 CPU s。评估内部结构键与延迟格式化，只在原输出需要时生成完全相同字符串。 | .3–1 s | 中；日志时序、模式 ID、异常和诊断可观察行为 | 输出逐字节一致；不要因延迟生成丢失中间事件状态；分配/格式化次数实降 |
| 6 | 精确 T128/十进制来源结果的有界缓存；独占约 1.16 CPU s，优先级较低。 | 0–.4 s | 中；精确来源、预算、取消后校验不能改变 | 原大整数 oracle、同时间不同来源负例、Stage C 取消漏检回归、溢出与预算行为一致 |

不建议先改根搜索或关闭原方程检查：根搜索 Total 约 2.81 CPU s，原方程检查 477,111 次是既定检查语义；本轮没有证据支持通过删除它们获得安全收益。真正写系统调用仅 .161 s，单纯更换写盘方式的上界也很小。

若只选三份求解器文件研究：`src/descriptor.cpp`（绑定/固定索引/矩阵 scratch）、`src/engineering_flow.cpp`（投影/COW/local coefficients/兼容）、`src/pevt.cpp`（等价证书/键与临时编码）。跨文件不可变结构设计可能需要相应头文件，不能以“三文件限制”牺牲类型或失效规则。

每项采用独立源码提交、先精确次数与分配证据、后完整正确性、最后无剖析性能；收益以真实测量替换上述估计，未通过不得缩短时长、删通道或放宽容差。
'''
    (out/'OPTIMIZATION_PLAN.md').write_text(plan,encoding='utf-8')
    commands=[['uname','-a'],['g++','--version'],['cmake','--version'],['/usr/lib/linux-tools/6.8.0-147-generic/perf','version','--build-options']]
    evidence={'solver_commit':'f8138727a45f7213898a87b0a10c94a57eb33c04','source_unchanged':not subprocess.check_output(['git','diff','f8138727a45f7213898a87b0a10c94a57eb33c04','--','src','include','apps','CMakeLists.txt'],cwd=a.repo),
      'text_identity':read(raw/'text_identity.json'),'sampling':sampling,'counter_run':count_run,'counts':counts,'probe_manifest':manifest,'allocation':alloc,
      'analysis':analysis,'machine':{'cpuinfo':Path('/proc/cpuinfo').read_text(),'os_release':Path('/etc/os-release').read_text(),'commands':[]},
      'baseline_B':baseline,'accepted_Stage_C':accepted,'counter_regression':read(raw/'full-500ms/regression.json'),'sampling_regression':read(raw/'cpu-sampling-500ms/regression.json'),
      'limitations':['CPU shares are sampling estimates, not guaranteed 1% relative error','Only selected outlined functions have true invocation counts','Heavy paired-probe CPU stacks are excluded from primary CPU analysis','Allocator counts public API requests; not a live heap map','Observer delegated API nesting fixed after capture; all affected delegated APIs had zero uses in the captured solver run','/proc/PID/io unavailable; first telemetry incomplete, second contains 618 valid records'],
      'raw_artifacts':{}}
    for c in commands:
        q=subprocess.run(c,capture_output=True,text=True);evidence['machine']['commands'].append({'command':c,'returncode':q.returncode,'stdout':q.stdout,'stderr':q.stderr})
    for path in sorted(raw.rglob('*')):
        if path.is_file():evidence['raw_artifacts'][str(path.relative_to(raw))]=fingerprint(path)
    (out/'EVIDENCE.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Report and compact artifacts ready:',out,'; raw files:',len(evidence['raw_artifacts']))


if __name__=='__main__':main()
