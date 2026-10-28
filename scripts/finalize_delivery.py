#!/usr/bin/env python3
import datetime,hashlib,json,pathlib,platform,subprocess
root=pathlib.Path(__file__).resolve().parents[1];reports=root/'reports'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
baseline=load(reports/'migration_baseline.json');old=pathlib.Path(baseline['source'])
changed=[f['path'] for f in baseline['files'] if not (old/f['path']).exists() or sha(old/f['path'])!=f['sha256']]
audit={'source':str(old),'files_checked':len(baseline['files']),'changed_or_missing':changed,'read_only_preserved':not changed}
(reports/'v11_preservation_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
native=load(reports/'validation/all_ledger.json')
refs={p.stem:load(p) for p in (reports/'independent_reference').glob('*_reference.json')}
invariance=load(reports/'event_invariance_ledger.json')
ledger={'execution':native,'independent_reference':refs,'invariance':invariance,
        'completion_is_not_calibration':True,'PLECS_calibration':'NOT_AVAILABLE','V1.1_preservation':audit}
(reports/'test_ledger.json').write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n')
artifacts=[root/'build/pulse-solver',root/'build/libpulse_solver.dylib']
release={'version':'1.15.0-dev','platform':platform.platform(),'machine':platform.machine(),
         'date':datetime.datetime.now().astimezone().isoformat(),'source_sha256':native['cases'][0]['source_sha256'],
         'native_runtime':'C++20; no Python/Boost dependency','other_platforms':'NOT_TESTED',
         'artifacts':[{'path':str(p.relative_to(root)),'sha256':sha(p),'bytes':p.stat().st_size} for p in artifacts]}
identity_files=sorted(p for parent,extensions in [('src',{'.cpp'}),('include',{'.hpp','.h'}),('apps',{'.cpp'})] for p in (root/parent).rglob('*') if p.is_file() and p.suffix in extensions)
identity=''.join(f'{p.relative_to(root).as_posix()}:{sha(p)}\n' for p in identity_files)
identity+='CMakeLists.txt:'+sha(root/'CMakeLists.txt')+'\n'
release['current_source_sha256']=hashlib.sha256(identity.encode()).hexdigest()
release['source_hash_matches_tested_runtime']=release['current_source_sha256']==release['source_sha256']
if not release['source_hash_matches_tested_runtime']:raise RuntimeError('Source changed after recorded native validation')
(reports/'release_manifest.json').write_text(json.dumps(release,ensure_ascii=False,indent=2)+'\n')
manifest=[{'path':str(p.relative_to(root)),'sha256':sha(p)} for parent in ['src','include','apps','tests','examples'] for p in sorted((root/parent).rglob('*')) if p.is_file()]
(reports/'source_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
rows=[]
for c in native['cases']:
 rows.append(f"| {c['case']} | {c['status']} | {c['simulated_seconds']:.9g} | {c['wall_seconds']:.4f} | {c['mode_compilations']} |")
refrows=[]
for name,r in sorted(refs.items()):
 maximum=max(float(x) for x in r['max_amplitude_relative_error_per_physical_coordinate'])
 refrows.append(f"| {name} | {r['segments_checked']} | {r['roots_checked']} | {maximum:.4g} | {r['propagation_test_passed']} |")
text='''# PULSE V1.15 工程重构实施报告

已在独立目录交付可构建、可运行的原生 C++20 开发版。V1.1 源码和历史资料未修改。
本报告记录工程运行与数值验证结果，不声明正式发布、全轨迹数学认证或PLECS校准。

## 实际实现

保留单文件Markdown v1.1、13原语、SUBCKT、类型推断、联合Descriptor/MNA、q/phi/eta、
矩阵指数、T128、CLI、C ABI1/2及PEWave输出。事件运行核心已替换为当前模态预测最近
事件、10fs默认独立原子窗口、旧模态推进、候选导数联合换模、数字微步骤与事务提交。
旧全历史包络认证不参与产品Runtime。详见docs/Engineering_Contract.md和系统框图。

候选不等于实际切换：新模态使候选反向时保留原模态。零/不可分辨导数、方向冲突、
模式循环、物理状态不相容和未支持的代数跳变有诊断并回滚。REG/动态延时读取同一快照。
保存网格与默认原子时间解耦；显式旧atom-exponent保留兼容时间策略。

## 构建和测试

- 本机macOS ARM64原生编译成功，CLI、共享库和测试程序均已生成。
- 7/7 CTest目标通过，包含15项独立工程事件测试。
- 继承事件不变性3项场景通过，含720种声明顺序，累计37772项断言、0失败。
- 12个历史电路和8个原始pF电路均到达原终点；网表物理参数和初态未改动。
- 首轮19/20：整流器pF因近重根指数抵消导致搜索预算停止；修复并完整重跑后20/20。
  首轮原始失败台账保留在validation/iteration01_ledger.json。
- 独立测试先发现零导数误触发、REG跳变CMP/PWA换段遗漏及日志覆盖；均修复并重跑。

### 原生电路执行台账

下表仅评价完成性；耗时为本机单次端到端运行，不能据此宣称相对V1.1的可比速度比。
新默认T_atom=10fs，旧pF测试默认为0.1fs，时间接受合同已经变化。

| 电路 | 执行状态 | 实际物理时长/s | 端到端耗时/s | 模态编译次数 |
|---|---|---:|---:|---:|
'''+ '\n'.join(rows)+'''

### 独立80位数值复核

使用mpmath的80位矩阵指数、原始binary64编译矩阵/因子和权威T128时间，沿已记录的
工程切换时刻重放，检查各段共同物理状态。相对误差采用每个物理坐标的轨迹幅值归一化，
测试门槛2e-6。该复核隔离传播数值误差；没有独立重算完整事件序列，不是混合轨迹认证。

| 复核轨迹 | 段数 | 阈值事件数 | 最大幅值归一化误差 | 传播测试通过 |
|---|---:|---:|---:|---|
'''+ '\n'.join(refrows)+'''

原始trace和复核JSON均在independent_reference/。根的残差/导数时间偏差仅为数值估计，
不作为完整物理事件时间误差界。初始Buck/RLC另有解析解和首次事件顺序测试。

## 有限关断模型示例

examples/buck_finite_turnoff.md用现有SW、SENSOR、REG、INT、MATH、CMP、SEL、I、C
组成受限正向电流MOS关断模型。OFF采样旧通道电流，按固定最大下降斜率形成有限坡段，
Coss/Cj负责换流；不增加红色原语。已运行到5us，原始输出在validation/buck_finite_turnoff。
OFF表示开始关断；D_ON与FALL_END的实际顺序由模型产生，允许通道下降与二极管接流重叠。
该例不代表完整MOS门极电荷、开通、反向恢复、雪崩或双向器件模型。

## 兼容性和证据边界

输入仍使用PULSE Netlist v1.1头；产品版本为1.15.0-dev。C ABI版本/结构保持2，ABI1符号保留。
ABI2显式atom_exponent使用旧策略；NULL运行选项使用新默认10fs。NPZ保持time f8、模拟f4、
数字u1、Unicode metadata以及原有四个输出文件。事件先后以T128日志为准。

V1.0不是正确性Oracle。当前没有PLECS原始波形，所以不声称已进行PLECS校准。
V1.1旧118/69认证断言不被自动计为新版本通过；其与新合同不兼容部分保留作迁移参考。
Linux和Windows尚未实测。模型和数值支持限制见Open_Issues.md。

## 复现

```sh
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel 3
ctest --test-dir build --output-on-failure
python3 scripts/run_validation.py --suite all
./build/pulse-solver examples/buck_finite_turnoff.md --out out-finite
```

本机构建工具位置见README。复核程序需可选mpmath；原生产品无需Python。
源码与二进制哈希见release_manifest.json/source_manifest.json；V1.1保留审计见v11_preservation_audit.json。
'''
(reports/'Implementation_Report.md').write_text(text)
issues='''# V1.15 未决问题与支持边界

1. PLECS校准尚未进行，需要同模型、同初态、同控制参数的真实参考数据。
2. 测量到的高精度误差只覆盖指定模型与轨迹。原子窗口不是全轨迹误差界。
3. 新初始化采用确定的点值/方向迭代；尚未提供独立的用户初始模态覆盖接口，
   不支持任意多稳定初态的全局唯一性判定。循环或无法初始化时停止。
4. 有限关断示例仅支持正向通道电流与固定最大下降斜率；primitive SW仍瞬时选Ron/Roff。
   通用门极电荷、反向恢复、雪崩、有限开通过程和最短驻留约束未自动实现。
5. 有缺陷/严重病态谱、非常小的非零斜率、切触、高指数DAE、冲激、滑模和未建模
   的代数阈值跳变可能明确停止；不通过隐式物理正则化或状态重置强行完成。
6. 旧严格认证测试的迁移尚未全部完成；本轮7组产品测试和20个电路的实际结果详见台账。
7. 目前仅macOS ARM64实测；其他平台尚未构建验证。
8. 单次性能记录不满足严格同配置V1.1速度比条件；没有发布速度提升倍数。
'''
(reports/'Open_Issues.md').write_text(issues)
print('Finalized reports, manifests and read-only preservation audit:',audit)
