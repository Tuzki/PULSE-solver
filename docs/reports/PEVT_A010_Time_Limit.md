# A010 当前事件版：五倍用时上限测试

日期：2026-11-02，Asia/Shanghai。

## 结果

按用户要求：事件文件生成超过本轮 PLECS 用时的五倍时，终止该仿真并停止整批测试；波形重建独立于仿真用时。

| 项目 | 本轮结果 |
|---|---|
| 案例 | rohm-a010-dot-totem-pole-pfc-sync |
| 目标仿真时长 | 原始完整 0.5 s |
| PLECS | COMPLETED，13.287746 s |
| 事件生成上限 | 66.438728 s（5 × PLECS） |
| Linux 当前事件版 | TIME_LIMIT_EXCEEDED，启动至进程退出 66.654397 s |
| Windows 当前事件版 | 未运行，按五倍上限停止策略取消 |
| 波形重建 | 未运行 |
| 本轮精度检查 | 未执行；缺少完整事件文件及重建结果 |
| 完整事件文件大小 | 未取得；终止时未生成 `.pevt` 文件 |

Linux 为 WSL2 Ubuntu 24.04 中原生 x86-64 ELF，使用 `.so` 控制模块。GNU timeout 对原生求解进程设置 66.438728 s 上限；Windows 侧观测时间包含 WSL 启动和退出，因而略大于上限。终止信号为 SIGKILL，WSL 返回码为 9；后续进程查询确认该求解器已退出。没有启动后续仿真。

此次只能确定完整事件生成未在五倍上限内完成，不能据此推算完整运行时间。Boost 的速度结论不能直接推广到 A010。

## 输入与比较基线

读取案例库原网表、控制器与参考文件，启动前核对 provenance 中的 SHA256。`--t-end 0.5` 对应原始 PLECS 完整时长，保留原 SAVE_DT。未改求解器、数值策略、容差或物理模型。

原版 PULSE 数据复用先前完整运行，已重新核对原版可执行文件及所有输出文件 SHA256；以下用时不是本轮重新测量：

| 平台 | 原版完整用时 | 原版状态 |
|---|---:|---|
| Windows | 857.685719 s | COMPLETED，0.5 s |
| Linux | 622.207272 s | COMPLETED，0.5 s |

本轮 PLECS 重新运行并完成。此前原版精度统计不计为本轮事件版通过结果。

## 复现与证据

测试入口：`scripts/benchmark_pevt_a010.py`。先测实时 PLECS，再按 Linux、Windows 顺序生成事件文件；任一事件生成超时则退出，取消后续步骤。脚本已补充 WSL 将 SIGKILL 映射为退出码 9 的识别。此次没有为此重跑仿真。

```powershell
python scripts/benchmark_pevt_a010.py --case-set ../PULSE-case-set --baseline reports/all-platforms-full-20261101 --out reports/pevt-a010-20261102
```

重新执行时使用新的 `--out` 和 `--native-out`，保留已有证据。

- [输入、二进制身份和停止证据](PEVT_A010_Time_Limit_Evidence.json)
- 本地完整记录：`reports/pevt-a010-20261102/ledger.json`
- 当前求解器源码：`2f3a18a0fed7ece0471b4a0a77bddbaba2e084d2`
- Linux 二进制 SHA256：`b9722c00ace91d7abe1b6e4c0639b480a87aab61bf335fa606465d9779c33b1f`

强制终止时求解器尚未输出最终报告，无法从此次 stdout 取得最后已提交仿真时间、事务数或状态切片。没有把空输出目录的 0 B 当作有效事件文件大小。
