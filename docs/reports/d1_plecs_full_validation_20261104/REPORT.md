# PULSE D1 与 PLECS 全时验证报告

固定分支：`fix/stage-d1-runtime-repair-20261104`；提交：`9f49f733863b90d8356aee22595e71e72fcc2c2b`。该提交相对 D1 算法修复提交 `05fb315` 仅增加报告，求解器源码相同。案例参考：[PULSE-case-set 固定提交](https://github.com/Tuzki/PULSE-case-set/tree/13660577132de41c37c1c47576c02941d21c532a)。

案例集共有 20 例，其中 19 例有 PULSE 网表。已记录 20/20 例；完整生成轨迹 9 例，完成全区间精度对照 9 例。

## 主要发现

- 19 个有网表案例中，9 例完整生成事件流；6 例超时，1 例归档失败，3 例数值或初始化失败。另有 1 例无网表。
- 20 点中最大偏差出现在 C-011-D CH001 的 0.4 s：PLECS=9.71974，PULSE=2.16689e-05，按该通道 PLECS 全波绝对值均值归一化为 215.105%。
- 全波 RMS 统计偏差最大的是 C-010-D CH001，同一归一化口径下为 22.372%。各案例的最大值可能来自不同通道。

## 对照口径

- PULSE 用时为本次云实例单次进程墙钟：包含 CLI 启动、解析、求解和完整轨迹写出；排除控制模块编译及波形重建。串行运行，不取多次最优值。
- PLECS 用时是 case-set 在 2026-11-01 保存的 PLECS 4.8.2 simulate RPC 测量，来自另一台机器和另一轮执行。用时比只描述这两条记录，不是同机加速比。
- 体积用十进制 MB。事件轨迹占用包括 out.pevt 和 simulation_report.json；另列出核心 out.pevt 大小。重建波形和本次诊断日志不计入轨迹占用。PLECS 体积为原始未压缩参考 CSV 各分片总和；两种存储格式不同。
- 完整仿真窗口使用原厂 PLECS 时长，通过 CLI --t-end 指定，不改网表及控制源。案例库包含历史未通过候选，不能据有网表认定通过。
- 重建单独运行，并指定 1 µs 网格与 PLECS 对齐。时间轴逐点核对，无时轴平移、无开关边沿剔除。若 PULSE 在终点额外输出相隔小于 1 ps 的两个样本，保留最后提交状态与 PLECS 终点对齐。
- 20 点取完整 PLECS 网格中近似等距的 20 个索引，含首尾；逐通道 E(t)=100×|PULSE(t)−PLECS(t)|/mean(|PLECS|)。分母为完整 1 µs 参考网格（含首尾）的绝对值算术平均，零分母百分比留空。
- 另对全波均值、RMS、最小值、最大值逐通道计算差异，百分比同样除以全波绝对值均值。未指定验收阈值，报告偏差而不自行宣布精度通过。
- PULSE 重建的模拟通道以 float32 保存，PLECS CSV 以 17 位有效数字保存；微小差异包含输出量化，1 µs 网格上的结果不构成连续时间精度证明。
- 每进程内存地址空间限制 8 GiB；生成墙钟预算为对应历史 PLECS 用时的 5 倍（超过即停止并标记超时）；重建预算600秒。超时不计作全时长完成，不以有效前缀代替全段精度。
- A002 的 PULSE 是既有20 µs ZOH控制，而PLECS为原厂连续控制；其偏差包含模型/控制差别，不能仅归因于数值算法。
- A021-D 的本轮求解报告列出14个模拟通道，而 PLECS 参考有18个；缺少 MOS_JUNCTION_TEMP_C、MOS_HEATSINK_TEMP_C、DIODE_JUNCTION_TEMP_C、DIODE_HEATSINK_TEMP_C 四个热通道。本轮事件流归档也未完成。

## 完整轨迹结果

| Case | 仿真时长 s | PLECS历史用时 s | PULSE轨迹生成 s | PLECS/PULSE用时比¹ | PLECS CSV MB | 轨迹总 MB | PEVT MB | 精度状态 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| A-002-D | 0.5 | 48.065 | 11.955 | 4.020 | 68.365 | 59.396 | 59.383 | COMPARED |
| A-010-DOT | 0.5 | 13.755 | 47.071 | 0.292 | 68.367 | 162.854 | 162.837 | COMPARED |
| A-011-D | 0.5 | 47.171 | 28.332 | 1.665 | 67.890 | 147.218 | 147.203 | COMPARED |
| B-004-D | 0.5 | 10.396 | 7.195 | 1.445 | 81.124 | 42.319 | 42.305 | COMPARED |
| B-004-DOT | 0.5 | 10.608 | 7.698 | 1.378 | 81.449 | 42.421 | 42.407 | COMPARED |
| C-002-D | 0.3 | 10.237 | 2.724 | 3.758 | 35.788 | 17.491 | 17.481 | COMPARED |
| C-006-D | 0.3 | 11.946 | 2.583 | 4.624 | 31.155 | 16.865 | 16.854 | COMPARED |
| C-010-D | 0.3 | 11.328 | 5.490 | 2.064 | 31.264 | 33.447 | 33.436 | COMPARED |
| C-011-D | 0.4 | 42.258 | 30.225 | 1.398 | 56.848 | 205.407 | 205.394 | COMPARED |

¹ 不同机器和批次的测量比，不能解释为同机性能提升。

## 精度摘要

下表取各案例所有已对齐电气通道中最大的20点百分比偏差；逐通道、逐时刻数值见 POINTS20.csv。全波统计见 STATISTICS.csv。单个汇总数不代替逐通道结果。

| Case | 已对照通道数 | 20点最大偏差 % | 缺失通道 |
|---|---:|---:|---|
| A-002-D | 7 | 0.317105 | 无 |
| A-010-DOT | 7 | 0.000045 | 无 |
| A-011-D | 7 | 101.233478 | 无 |
| B-004-D | 10 | 0.000018 | 无 |
| B-004-DOT | 10 | 0.000019 | 无 |
| C-002-D | 7 | 0.000063 | 无 |
| C-006-D | 7 | 0.000053 | 无 |
| C-010-D | 7 | 0.000329 | 无 |
| C-011-D | 9 | 215.105409 | 无 |

### 全波统计值偏差摘要

逐通道统计值差异除以对应 PLECS 全波绝对值均值。下表每列取本案例已比较通道中的最大值（%）。完整原始统计值及差异见 STATISTICS.csv。

| Case | 均值偏差 % | RMS偏差 % | 最小值偏差 % | 最大值偏差 % |
|---|---:|---:|---:|---:|
| A-002-D | 0.002392 | 0.002742 | 0.000118 | 0.000173 |
| A-010-DOT | 0.000111 | 0.000112 | 0.000041 | 0.000039 |
| A-011-D | 0.010828 | 0.000898 | 0.000783 | 0.001560 |
| B-004-D | 0.000009 | 0.000004 | 0.000010 | 0.000014 |
| B-004-DOT | 0.004802 | 0.005087 | 0.000011 | 0.000013 |
| C-002-D | 0.796101 | 1.132207 | 0.000020 | 8.042120 |
| C-006-D | 7.506239 | 11.013096 | 0.000018 | 0.000008 |
| C-010-D | 16.506952 | 22.371941 | 0.000006 | 0.000377 |
| C-011-D | 10.224466 | 7.548684 | 0.002602 | 0.002754 |

## 未完整交付的案例

| Case | 目标时长 s | 有效仿真终点 s | 返回/停止用时 s | 5倍上限 s | 残留产物 MB² | 状态/诊断 |
|---|---:|---:|---:|---:|---:|---|
| A-021-D | 0.5 | 0.500000000 | 198.831 | 1658.440 | 0.082 | 归档写出失败：event stream exceeds 512 MiB |
| A-021-DOT | 0.5 | 0.152583000 | 66.478 | 152.822 | 235.849 | ALL_EVENT_ALGORITHMS_FAILED |
| B-009-D | 0.5 | — | 71.673 | 71.647 | 0.000 | 超时（>5×PLECS） |
| B-011-DOT | 0.5 | 0.000000000 | 0.083 | 116.449 | 0.030 | INITIAL_MODE_CYCLE |
| B-012-DOT | 0.5 | — | 168.215 | 168.180 | 0.000 | 超时（>5×PLECS） |
| C-012-D | 0.3 | — | 219.757 | 219.632 | 0.000 | 超时（>5×PLECS） |
| C-012-DOT | 0.3 | — | 566.953 | 566.707 | 0.000 | 超时（>5×PLECS） |
| C-014-D | 0.2 | — | 255.435 | 255.356 | 0.000 | 超时（>5×PLECS） |
| C-014-DOT | 0.2 | — | 272.100 | 272.020 | 0.000 | 超时（>5×PLECS） |
| C-019-D | 0.2 | 0.000000100 | 0.044 | 636.024 | 0.128 | ALL_EVENT_ALGORITHMS_FAILED |
| C-019-DOT | 0.15 | — | — | 464.538 | 0.000 | NO_NETLIST |

² 失败或超时后残留的轨迹目录文件，可能缺少元数据或完整性校验，不是可交付的完整事件流；不计算其压缩比或精度。

所有超时标签按原厂 PLECS 历史记录用时的5倍计算。

## 验证与文件

- [CTEST.log](CTEST.log)：本轮 Linux Release 原生测试 36/36 通过；[MACHINE.json](MACHINE.json) 记录环境与编译工具。
- [AUDIT.log](AUDIT.log) 记录统计与逐点数值、图件、源文件哈希和报告链接的独立检查。
- 所有已运行案例的原始网表/控制源哈希保持一致：True。
- [SUMMARY.csv](SUMMARY.csv)：逐案例时间和空间占用；[CHANNEL_ACCURACY.csv](CHANNEL_ACCURACY.csv)：逐通道误差；[STATISTICS.csv](STATISTICS.csv)：全波统计；[POINTS20.csv](POINTS20.csv)：20点明细。
- [evidence.json](evidence.json)：版本、二进制及输入哈希、命令、独立计时、资源预算、错误信息、轨迹组件字节数。云环境中的每个案例目录保留原始事件流和重建波形；GitHub 报告只包含统计、逐点数据、图片、证据及复算脚本，不包含大型 PEVT/NPZ 文件。
- 本次没有运行新的 PLECS；没有修改求解算法、网表、控制代码或数值容差。

## 波形叠图

未完整生成或无法重建波形的案例没有完整叠图；缺少 PULSE 通道时，图中仅展示 PLECS 并标注缺失。图中连线连接参考网格采样点，可能漏掉网格之间的开关边沿。

全时图和末 1 ms 图均绘制相应时间范围内参考网格的全部采样点；统计和20点计算均使用完整1 µs 数据。

### A-002-D

[20点逐通道明细](rohm-a002-d-boost-pfc/POINTS20.csv) · [全波统计明细](rohm-a002-d-boost-pfc/STATISTICS.csv)

<details><summary>展开通道叠图</summary>

#### CH001_full

![CH001_full](rohm-a002-d-boost-pfc/plots/CH001_full.png)

#### CH001_last_1ms

![CH001_last_1ms](rohm-a002-d-boost-pfc/plots/CH001_last_1ms.png)

#### CH002_full

![CH002_full](rohm-a002-d-boost-pfc/plots/CH002_full.png)

#### CH002_last_1ms

![CH002_last_1ms](rohm-a002-d-boost-pfc/plots/CH002_last_1ms.png)

#### CH003_full

![CH003_full](rohm-a002-d-boost-pfc/plots/CH003_full.png)

#### CH003_last_1ms

![CH003_last_1ms](rohm-a002-d-boost-pfc/plots/CH003_last_1ms.png)

#### CH004_full

![CH004_full](rohm-a002-d-boost-pfc/plots/CH004_full.png)

#### CH004_last_1ms

![CH004_last_1ms](rohm-a002-d-boost-pfc/plots/CH004_last_1ms.png)

#### CH005_full

![CH005_full](rohm-a002-d-boost-pfc/plots/CH005_full.png)

#### CH005_last_1ms

![CH005_last_1ms](rohm-a002-d-boost-pfc/plots/CH005_last_1ms.png)

#### CH006_full

![CH006_full](rohm-a002-d-boost-pfc/plots/CH006_full.png)

#### CH006_last_1ms

![CH006_last_1ms](rohm-a002-d-boost-pfc/plots/CH006_last_1ms.png)

#### CH007_full

![CH007_full](rohm-a002-d-boost-pfc/plots/CH007_full.png)

#### CH007_last_1ms

![CH007_last_1ms](rohm-a002-d-boost-pfc/plots/CH007_last_1ms.png)

</details>

### A-010-DOT

[20点逐通道明细](rohm-a010-dot-totem-pole-pfc-sync/POINTS20.csv) · [全波统计明细](rohm-a010-dot-totem-pole-pfc-sync/STATISTICS.csv)

<details><summary>展开通道叠图</summary>

#### CH001_full

![CH001_full](rohm-a010-dot-totem-pole-pfc-sync/plots/CH001_full.png)

#### CH001_last_1ms

![CH001_last_1ms](rohm-a010-dot-totem-pole-pfc-sync/plots/CH001_last_1ms.png)

#### CH002_full

![CH002_full](rohm-a010-dot-totem-pole-pfc-sync/plots/CH002_full.png)

#### CH002_last_1ms

![CH002_last_1ms](rohm-a010-dot-totem-pole-pfc-sync/plots/CH002_last_1ms.png)

#### CH003_full

![CH003_full](rohm-a010-dot-totem-pole-pfc-sync/plots/CH003_full.png)

#### CH003_last_1ms

![CH003_last_1ms](rohm-a010-dot-totem-pole-pfc-sync/plots/CH003_last_1ms.png)

#### CH004_full

![CH004_full](rohm-a010-dot-totem-pole-pfc-sync/plots/CH004_full.png)

#### CH004_last_1ms

![CH004_last_1ms](rohm-a010-dot-totem-pole-pfc-sync/plots/CH004_last_1ms.png)

#### CH005_full

![CH005_full](rohm-a010-dot-totem-pole-pfc-sync/plots/CH005_full.png)

#### CH005_last_1ms

![CH005_last_1ms](rohm-a010-dot-totem-pole-pfc-sync/plots/CH005_last_1ms.png)

#### CH006_full

![CH006_full](rohm-a010-dot-totem-pole-pfc-sync/plots/CH006_full.png)

#### CH006_last_1ms

![CH006_last_1ms](rohm-a010-dot-totem-pole-pfc-sync/plots/CH006_last_1ms.png)

#### CH007_full

![CH007_full](rohm-a010-dot-totem-pole-pfc-sync/plots/CH007_full.png)

#### CH007_last_1ms

![CH007_last_1ms](rohm-a010-dot-totem-pole-pfc-sync/plots/CH007_last_1ms.png)

</details>

### A-011-D

[20点逐通道明细](rohm-a011-d-totem-pole-pfc-diode/POINTS20.csv) · [全波统计明细](rohm-a011-d-totem-pole-pfc-diode/STATISTICS.csv)

<details><summary>展开通道叠图</summary>

#### CH001_full

![CH001_full](rohm-a011-d-totem-pole-pfc-diode/plots/CH001_full.png)

#### CH001_last_1ms

![CH001_last_1ms](rohm-a011-d-totem-pole-pfc-diode/plots/CH001_last_1ms.png)

#### CH002_full

![CH002_full](rohm-a011-d-totem-pole-pfc-diode/plots/CH002_full.png)

#### CH002_last_1ms

![CH002_last_1ms](rohm-a011-d-totem-pole-pfc-diode/plots/CH002_last_1ms.png)

#### CH003_full

![CH003_full](rohm-a011-d-totem-pole-pfc-diode/plots/CH003_full.png)

#### CH003_last_1ms

![CH003_last_1ms](rohm-a011-d-totem-pole-pfc-diode/plots/CH003_last_1ms.png)

#### CH004_full

![CH004_full](rohm-a011-d-totem-pole-pfc-diode/plots/CH004_full.png)

#### CH004_last_1ms

![CH004_last_1ms](rohm-a011-d-totem-pole-pfc-diode/plots/CH004_last_1ms.png)

#### CH005_full

![CH005_full](rohm-a011-d-totem-pole-pfc-diode/plots/CH005_full.png)

#### CH005_last_1ms

![CH005_last_1ms](rohm-a011-d-totem-pole-pfc-diode/plots/CH005_last_1ms.png)

#### CH006_full

![CH006_full](rohm-a011-d-totem-pole-pfc-diode/plots/CH006_full.png)

#### CH006_last_1ms

![CH006_last_1ms](rohm-a011-d-totem-pole-pfc-diode/plots/CH006_last_1ms.png)

#### CH007_full

![CH007_full](rohm-a011-d-totem-pole-pfc-diode/plots/CH007_full.png)

#### CH007_last_1ms

![CH007_last_1ms](rohm-a011-d-totem-pole-pfc-diode/plots/CH007_last_1ms.png)

</details>

### B-004-D

[20点逐通道明细](rohm-b004-d-single-phase-inverter/POINTS20.csv) · [全波统计明细](rohm-b004-d-single-phase-inverter/STATISTICS.csv)

<details><summary>展开通道叠图</summary>

#### CH001_full

![CH001_full](rohm-b004-d-single-phase-inverter/plots/CH001_full.png)

#### CH001_last_1ms

![CH001_last_1ms](rohm-b004-d-single-phase-inverter/plots/CH001_last_1ms.png)

#### CH002_full

![CH002_full](rohm-b004-d-single-phase-inverter/plots/CH002_full.png)

#### CH002_last_1ms

![CH002_last_1ms](rohm-b004-d-single-phase-inverter/plots/CH002_last_1ms.png)

#### CH003_full

![CH003_full](rohm-b004-d-single-phase-inverter/plots/CH003_full.png)

#### CH003_last_1ms

![CH003_last_1ms](rohm-b004-d-single-phase-inverter/plots/CH003_last_1ms.png)

#### CH004_full

![CH004_full](rohm-b004-d-single-phase-inverter/plots/CH004_full.png)

#### CH004_last_1ms

![CH004_last_1ms](rohm-b004-d-single-phase-inverter/plots/CH004_last_1ms.png)

#### CH005_full

![CH005_full](rohm-b004-d-single-phase-inverter/plots/CH005_full.png)

#### CH005_last_1ms

![CH005_last_1ms](rohm-b004-d-single-phase-inverter/plots/CH005_last_1ms.png)

#### CH006_full

![CH006_full](rohm-b004-d-single-phase-inverter/plots/CH006_full.png)

#### CH006_last_1ms

![CH006_last_1ms](rohm-b004-d-single-phase-inverter/plots/CH006_last_1ms.png)

#### CH007_full

![CH007_full](rohm-b004-d-single-phase-inverter/plots/CH007_full.png)

#### CH007_last_1ms

![CH007_last_1ms](rohm-b004-d-single-phase-inverter/plots/CH007_last_1ms.png)

#### CH008_full

![CH008_full](rohm-b004-d-single-phase-inverter/plots/CH008_full.png)

#### CH008_last_1ms

![CH008_last_1ms](rohm-b004-d-single-phase-inverter/plots/CH008_last_1ms.png)

#### CH009_full

![CH009_full](rohm-b004-d-single-phase-inverter/plots/CH009_full.png)

#### CH009_last_1ms

![CH009_last_1ms](rohm-b004-d-single-phase-inverter/plots/CH009_last_1ms.png)

#### CH010_full

![CH010_full](rohm-b004-d-single-phase-inverter/plots/CH010_full.png)

#### CH010_last_1ms

![CH010_last_1ms](rohm-b004-d-single-phase-inverter/plots/CH010_last_1ms.png)

</details>

### B-004-DOT

[20点逐通道明细](rohm-b004-dot-single-phase-inverter/POINTS20.csv) · [全波统计明细](rohm-b004-dot-single-phase-inverter/STATISTICS.csv)

<details><summary>展开通道叠图</summary>

#### CH001_full

![CH001_full](rohm-b004-dot-single-phase-inverter/plots/CH001_full.png)

#### CH001_last_1ms

![CH001_last_1ms](rohm-b004-dot-single-phase-inverter/plots/CH001_last_1ms.png)

#### CH002_full

![CH002_full](rohm-b004-dot-single-phase-inverter/plots/CH002_full.png)

#### CH002_last_1ms

![CH002_last_1ms](rohm-b004-dot-single-phase-inverter/plots/CH002_last_1ms.png)

#### CH003_full

![CH003_full](rohm-b004-dot-single-phase-inverter/plots/CH003_full.png)

#### CH003_last_1ms

![CH003_last_1ms](rohm-b004-dot-single-phase-inverter/plots/CH003_last_1ms.png)

#### CH004_full

![CH004_full](rohm-b004-dot-single-phase-inverter/plots/CH004_full.png)

#### CH004_last_1ms

![CH004_last_1ms](rohm-b004-dot-single-phase-inverter/plots/CH004_last_1ms.png)

#### CH005_full

![CH005_full](rohm-b004-dot-single-phase-inverter/plots/CH005_full.png)

#### CH005_last_1ms

![CH005_last_1ms](rohm-b004-dot-single-phase-inverter/plots/CH005_last_1ms.png)

#### CH006_full

![CH006_full](rohm-b004-dot-single-phase-inverter/plots/CH006_full.png)

#### CH006_last_1ms

![CH006_last_1ms](rohm-b004-dot-single-phase-inverter/plots/CH006_last_1ms.png)

#### CH007_full

![CH007_full](rohm-b004-dot-single-phase-inverter/plots/CH007_full.png)

#### CH007_last_1ms

![CH007_last_1ms](rohm-b004-dot-single-phase-inverter/plots/CH007_last_1ms.png)

#### CH008_full

![CH008_full](rohm-b004-dot-single-phase-inverter/plots/CH008_full.png)

#### CH008_last_1ms

![CH008_last_1ms](rohm-b004-dot-single-phase-inverter/plots/CH008_last_1ms.png)

#### CH009_full

![CH009_full](rohm-b004-dot-single-phase-inverter/plots/CH009_full.png)

#### CH009_last_1ms

![CH009_last_1ms](rohm-b004-dot-single-phase-inverter/plots/CH009_last_1ms.png)

#### CH010_full

![CH010_full](rohm-b004-dot-single-phase-inverter/plots/CH010_full.png)

#### CH010_last_1ms

![CH010_last_1ms](rohm-b004-dot-single-phase-inverter/plots/CH010_last_1ms.png)

</details>

### C-002-D

[20点逐通道明细](rohm-c002-d-boost/POINTS20.csv) · [全波统计明细](rohm-c002-d-boost/STATISTICS.csv)

<details><summary>展开通道叠图</summary>

#### CH001_full

![CH001_full](rohm-c002-d-boost/plots/CH001_full.png)

#### CH001_last_1ms

![CH001_last_1ms](rohm-c002-d-boost/plots/CH001_last_1ms.png)

#### CH002_full

![CH002_full](rohm-c002-d-boost/plots/CH002_full.png)

#### CH002_last_1ms

![CH002_last_1ms](rohm-c002-d-boost/plots/CH002_last_1ms.png)

#### CH003_full

![CH003_full](rohm-c002-d-boost/plots/CH003_full.png)

#### CH003_last_1ms

![CH003_last_1ms](rohm-c002-d-boost/plots/CH003_last_1ms.png)

#### CH004_full

![CH004_full](rohm-c002-d-boost/plots/CH004_full.png)

#### CH004_last_1ms

![CH004_last_1ms](rohm-c002-d-boost/plots/CH004_last_1ms.png)

#### CH005_full

![CH005_full](rohm-c002-d-boost/plots/CH005_full.png)

#### CH005_last_1ms

![CH005_last_1ms](rohm-c002-d-boost/plots/CH005_last_1ms.png)

#### CH006_full

![CH006_full](rohm-c002-d-boost/plots/CH006_full.png)

#### CH006_last_1ms

![CH006_last_1ms](rohm-c002-d-boost/plots/CH006_last_1ms.png)

#### CH007_full

![CH007_full](rohm-c002-d-boost/plots/CH007_full.png)

#### CH007_last_1ms

![CH007_last_1ms](rohm-c002-d-boost/plots/CH007_last_1ms.png)

</details>

### C-006-D

[20点逐通道明细](rohm-c006-d-buck/POINTS20.csv) · [全波统计明细](rohm-c006-d-buck/STATISTICS.csv)

<details><summary>展开通道叠图</summary>

#### IDIODE_full

![IDIODE_full](rohm-c006-d-buck/plots/IDIODE_full.png)

#### IDIODE_last_1ms

![IDIODE_last_1ms](rohm-c006-d-buck/plots/IDIODE_last_1ms.png)

#### ID_full

![ID_full](rohm-c006-d-buck/plots/ID_full.png)

#### ID_last_1ms

![ID_last_1ms](rohm-c006-d-buck/plots/ID_last_1ms.png)

#### IIN_full

![IIN_full](rohm-c006-d-buck/plots/IIN_full.png)

#### IIN_last_1ms

![IIN_last_1ms](rohm-c006-d-buck/plots/IIN_last_1ms.png)

#### IOUT_full

![IOUT_full](rohm-c006-d-buck/plots/IOUT_full.png)

#### IOUT_last_1ms

![IOUT_last_1ms](rohm-c006-d-buck/plots/IOUT_last_1ms.png)

#### VDS_full

![VDS_full](rohm-c006-d-buck/plots/VDS_full.png)

#### VDS_last_1ms

![VDS_last_1ms](rohm-c006-d-buck/plots/VDS_last_1ms.png)

#### VINBUS_full

![VINBUS_full](rohm-c006-d-buck/plots/VINBUS_full.png)

#### VINBUS_last_1ms

![VINBUS_last_1ms](rohm-c006-d-buck/plots/VINBUS_last_1ms.png)

#### VOUT_full

![VOUT_full](rohm-c006-d-buck/plots/VOUT_full.png)

#### VOUT_last_1ms

![VOUT_last_1ms](rohm-c006-d-buck/plots/VOUT_last_1ms.png)

</details>

### C-010-D

[20点逐通道明细](rohm-c010-d-flyback/POINTS20.csv) · [全波统计明细](rohm-c010-d-flyback/STATISTICS.csv)

<details><summary>展开通道叠图</summary>

#### CH001_full

![CH001_full](rohm-c010-d-flyback/plots/CH001_full.png)

#### CH001_last_1ms

![CH001_last_1ms](rohm-c010-d-flyback/plots/CH001_last_1ms.png)

#### CH002_full

![CH002_full](rohm-c010-d-flyback/plots/CH002_full.png)

#### CH002_last_1ms

![CH002_last_1ms](rohm-c010-d-flyback/plots/CH002_last_1ms.png)

#### CH003_full

![CH003_full](rohm-c010-d-flyback/plots/CH003_full.png)

#### CH003_last_1ms

![CH003_last_1ms](rohm-c010-d-flyback/plots/CH003_last_1ms.png)

#### CH004_full

![CH004_full](rohm-c010-d-flyback/plots/CH004_full.png)

#### CH004_last_1ms

![CH004_last_1ms](rohm-c010-d-flyback/plots/CH004_last_1ms.png)

#### CH005_full

![CH005_full](rohm-c010-d-flyback/plots/CH005_full.png)

#### CH005_last_1ms

![CH005_last_1ms](rohm-c010-d-flyback/plots/CH005_last_1ms.png)

#### CH006_full

![CH006_full](rohm-c010-d-flyback/plots/CH006_full.png)

#### CH006_last_1ms

![CH006_last_1ms](rohm-c010-d-flyback/plots/CH006_last_1ms.png)

#### CH007_full

![CH007_full](rohm-c010-d-flyback/plots/CH007_full.png)

#### CH007_last_1ms

![CH007_last_1ms](rohm-c010-d-flyback/plots/CH007_last_1ms.png)

</details>

### C-011-D

[20点逐通道明细](rohm-c011-d-forward/POINTS20.csv) · [全波统计明细](rohm-c011-d-forward/STATISTICS.csv)

<details><summary>展开通道叠图</summary>

#### CH001_full

![CH001_full](rohm-c011-d-forward/plots/CH001_full.png)

#### CH001_last_1ms

![CH001_last_1ms](rohm-c011-d-forward/plots/CH001_last_1ms.png)

#### CH002_full

![CH002_full](rohm-c011-d-forward/plots/CH002_full.png)

#### CH002_last_1ms

![CH002_last_1ms](rohm-c011-d-forward/plots/CH002_last_1ms.png)

#### CH003_full

![CH003_full](rohm-c011-d-forward/plots/CH003_full.png)

#### CH003_last_1ms

![CH003_last_1ms](rohm-c011-d-forward/plots/CH003_last_1ms.png)

#### CH004_full

![CH004_full](rohm-c011-d-forward/plots/CH004_full.png)

#### CH004_last_1ms

![CH004_last_1ms](rohm-c011-d-forward/plots/CH004_last_1ms.png)

#### CH005_full

![CH005_full](rohm-c011-d-forward/plots/CH005_full.png)

#### CH005_last_1ms

![CH005_last_1ms](rohm-c011-d-forward/plots/CH005_last_1ms.png)

#### CH006_full

![CH006_full](rohm-c011-d-forward/plots/CH006_full.png)

#### CH006_last_1ms

![CH006_last_1ms](rohm-c011-d-forward/plots/CH006_last_1ms.png)

#### CH007_full

![CH007_full](rohm-c011-d-forward/plots/CH007_full.png)

#### CH007_last_1ms

![CH007_last_1ms](rohm-c011-d-forward/plots/CH007_last_1ms.png)

#### CH008_full

![CH008_full](rohm-c011-d-forward/plots/CH008_full.png)

#### CH008_last_1ms

![CH008_last_1ms](rohm-c011-d-forward/plots/CH008_last_1ms.png)

#### CH009_full

![CH009_full](rohm-c011-d-forward/plots/CH009_full.png)

#### CH009_last_1ms

![CH009_last_1ms](rohm-c011-d-forward/plots/CH009_last_1ms.png)

</details>
