# PULSEES1 实现与使用

协议：[Event_Stream_Format.md](Event_Stream_Format.md)。原始协议 SHA256：`fa2ea00f190c4e35fb840a77279988badf2f8b97fbc347da0482a71b9fd19eef`。

## 生成与重建

```sh
pulse-solver netlist.md --output-format trajectory --out result
pulse-replay result/out.pevt --out reconstructed
python scripts/read_pevt.py result/out.pevt --out protocol-summary.json
```

Windows 使用对应 `.exe`。默认 waveform 输出入口保持现状。`pulse-replay` 也接受包含 `out.pevt` 的目录，并保留旧版 trajectory 目录读取入口。

`result/out.pevt` 包含模型、数值块、方程定义、完整值集、方程实例、状态切片、事件、Flow、结束记录和诊断记录；外部 `simulation_report.json` 为便利副本。重建波形使用文件内的数据。

## 字段约定

| 项目 | 实现 |
|---|---|
| 事件状态 | 每个事件引用一个完整状态切片 |
| 模态 | 每个事件保存完整的前、后元件模态 ID 数组及前、后方程 ID |
| 时间 | 原生 T128 三元组，24 字节 |
| 系数和状态 | binary64 原始位；数值块按列存储 |
| 动态参数 | 完整 ValueSet；定义的 dynamic_bindings 指明回填位置 |
| Flow 原点 | 记录真正创建传播的事件、状态、方程及参考事件处的精确时间偏移 |
| 初末事件 | INIT 和 END；END 复用终止状态，可与最后事务同一时间 |
| 日志 | 可选段 10，保存原始诊断 JSONL |
| 编码与校验 | 当前写入 codec=0；逐段校验 decoded_bytes 与 SHA256 |

方程定义 JSON 增加 `component_mode_ids`，用于从元件模态定义恢复数字信号与分段编号。模型元数据增加元件端口、原参数、曲线及源元件索引。坐标名称使用实际内部状态坐标；原模型没有提供物理单位时，单位标为 `internal`，物理坐标变换保存在 provenance。

## 验证范围

原生测试覆盖 RC、Buck、Boost 的逐事件状态和模态、波形逐位重建、软件 ABI 与控制器执行；同时检查截断、损坏校验值、非法引用、数值上下文不兼容和非有限值。

独立 Python 读取器检查段布局、校验、维数、记录数量、引用及事件状态，并支持 codec=0 和 codec=1。当前 C++ 读取器支持 codec=0；外部生成的 gzip 段尚不支持。当前单文件读取上限为 512 MiB。

Flow 增加只用于归档的原点标识。该标识随原有 Flow 延续，用于可靠引用传播原点；状态传播、根定位、数值容差及控制器逻辑沿用原实现。
