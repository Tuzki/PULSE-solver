# PULSE 事件流文件协议草案

## 1. 基本编码

| 项目 | 格式 |
|---|---|
| 文件扩展名 | `.pevt` |
| 整数 | Little-endian |
| 连续数值 | IEEE 754 binary64，保存原始位 |
| 时间 T128 | `int64 whole + uint64 tick + uint64 subtick`，共 24 B |
| JSON | UTF-8 |
| 矩阵 | 列主序 binary64 |
| 二进制空引用 | `0xFFFFFFFF`；事件空引用为 `0xFFFFFFFFFFFFFFFF` |
| 记录排列 | 按表中字段顺序紧密排列 |
| 压缩编码 | `0=原始数据，1=gzip` |
| SHA256 | 对解压后的段负载计算 |

## 2. 文件头

固定 16 B。

| 字段 | 类型 | 内容 |
|---|---|---|
| magic | `char[8]` | `PULSEES1` |
| version | `uint16` | `1` |
| section_count | `uint16` | 数据段数量 |
| flags | `uint32` | `0` |

## 3. 数据段头

每个数据段使用固定 64 B 段头，随后为负载。

| 字段 | 类型 | 内容 |
|---|---|---|
| section_type | `uint32` | 数据段类型 |
| codec | `uint32` | 压缩编码 |
| stored_bytes | `uint64` | 实际负载长度 |
| decoded_bytes | `uint64` | 解压后负载长度 |
| record_count | `uint64` | 记录数量；JSON 段为 `1` |
| sha256 | `uint8[32]` | 解压后负载校验值 |

| section_type | 数据段 | 负载格式 |
|---:|---|---|
| 1 | 模型与状态定义 | JSON |
| 2 | 数值块表 | 二进制 |
| 3 | 方程模板表 | JSON |
| 4 | 动态值集表 | 二进制 |
| 5 | 方程实例表 | 二进制 |
| 6 | 状态切片表 | 二进制 |
| 7 | 事件表 | 二进制 |
| 8 | 传播记录表 | 二进制 |
| 9 | 结束记录 | JSON |
| 10 | 详细诊断日志 | JSONL，可选 |

## 4. 模型与状态定义段

JSON 对象。

| 字段 | 格式 | 内容 |
|---|---|---|
| state_dimension | `uint32` | 原内部状态向量维数 `Nx` |
| value_slot_count | `uint32` | 动态值槽数量 `Np` |
| modal_component_count | `uint32` | 模态元件数量 `Nm` |
| state_layout | 对象数组 | 各坐标的 `index、component_id、name、unit、meaning` |
| components | 对象数组 | `component_id、name、type` |
| signals | 对象数组 | `signal_id、component_id、name、unit` |
| modal_components | `uint32[Nm]` | 事件表模态数组采用的元件顺序 |
| component_modes | 对象数组 | `component_id、mode_id、definition` |
| value_slots | 对象数组 | `slot_id、name、unit、role` |
| numerical_context | 对象 | 传播实现版本、binary64 精度、long double 有效位及指数范围 |
| atomic_time | JSON number | 原子时间，按 binary64 往返编码 |
| boundary_rule | 字符串 | `POST_MODE`：事件时默认输出使用事后模态 |
| initial_event_id | `uint64` | 初始切片事件编号 |
| default_save_dt | JSON number | 默认波形导出间隔，按 binary64 往返编码 |
| provenance | 对象 | 网表、控制器、求解器身份及哈希 |

`role`：`INPUT、HELD_OUTPUT、COEFFICIENT`。

## 5. 数值块段

每条记录保存一个向量或矩阵。

| 字段 | 类型 | 内容 |
|---|---|---|
| block_id | `uint32` | 数值块 ID |
| rows | `uint32` | 行数 |
| cols | `uint32` | 列数 |
| data | `float64[rows × cols]` | 列主序数据 |

## 6. 方程模板段

JSON 对象数组，每项对应一份静态定义。

| 字段 | 格式 | 内容 |
|---|---|---|
| definition_id | `uint32` | 静态定义 ID |
| state_matrix | 数值块 ID | 原增广状态矩阵 M |
| invariant_lift | 数值块 ID 或 `null` | 原坐标提升矩阵 |
| invariant_generator | 数值块 ID 或 `null` | 原约化传播矩阵 |
| invariant_reduce | 数值块 ID 或 `null` | 原约化坐标映射 |
| observation_rows | 对象数组 | `signal_id、row_block_id` |
| constraints | 数值块 ID 或 `null` | 原约束矩阵 |
| residual_map | 数值块 ID 或 `null` | 原残差映射 |
| residual_reference | 数值块 ID 或 `null` | 原残差参考矩阵 |
| guards | 有序对象数组 | `component_id、row_block_id、direction、kind、knot、segment、step` |
| numerical_strategy | `uint32` | 原数值策略 ID |
| dynamic_bindings | 对象数组 | `slot_id、target_block_id、row、col` |

动态绑定将值集中的原始 binary64 值填入指定位置。绑定后的数值块组成该实例的实际方程与观察映射。

## 7. 动态值集段

每条记录为一份完整动态值集，相同值集共享 ID。

| 字段 | 类型 | 内容 |
|---|---|---|
| value_set_id | `uint32` | 动态值集 ID |
| values | `float64[Np]` | 按 `value_slots` 顺序保存的完整值 |

## 8. 方程实例段

| 字段 | 类型 | 内容 |
|---|---|---|
| equation_id | `uint32` | 实际系统模态方程 ID |
| definition_id | `uint32` | 静态定义引用 |
| value_set_id | `uint32` | 动态值集引用 |

## 9. 状态切片段

每条记录对应一份完整事件时状态。

| 字段 | 类型 | 内容 |
|---|---|---|
| state_id | `uint32` | 状态切片 ID |
| x | `float64[Nx]` | 原内部连续状态向量 |
| value_set_id | `uint32` | 该切片的完整输入、保持值及动态系数 |

各元件电压、电流由该切片与指定侧的观察方程求得；各元件离散模态见事件记录。

## 10. 事件段

每个事件对应一份状态切片，事前与事后模态分别记录。

| 字段 | 类型 | 内容 |
|---|---|---|
| event_id | `uint64` | 事件编号 |
| time | `T128` | 事件执行时间 |
| transaction_id | `uint64` | 提交事务编号 |
| microstep | `uint32` | 同一时刻的执行顺序 |
| event_kind | `uint32` | 事件类型 |
| state_id | `uint32` | 唯一事件时状态切片 |
| before_equation_id | `uint32` | 事前实际系统方程 ID |
| after_equation_id | `uint32` | 事后实际系统方程 ID |
| event_observer_flow_id | `uint32` | 事件点实际采用的 Flow；空引用表示直接使用观察方程 |
| outgoing_flow_id | `uint32` | 到下一事件之间实际采用的传播记录 |
| before_component_modes | `uint32[Nm]` | 全部模态元件的事前模态 ID |
| after_component_modes | `uint32[Nm]` | 全部模态元件的事后模态 ID |
| member_count | `uint32` | 联合事件成员数 |
| members | 成员数组 | 每项为 `component_id:uint32、kind:uint32` |

事件类型：`1=INITIAL、2=CONTROL、3=GATE、4=CONSTITUTIVE、5=JOINT、6=END`。

事件按 `(time, transaction_id, microstep, event_id)` 排列。初始时刻和实际终止时刻均有状态切片事件。

## 11. 传播记录段

| 字段 | 类型 | 内容 |
|---|---|---|
| flow_id | `uint32` | 传播记录 ID |
| reference_event_id | `uint64` | 本记录求值偏移所对应的事件 |
| origin_event_id | `uint64` | 实际传播起点事件；时间由该事件取得 |
| origin_state_id | `uint32` | 原始传播起点状态 |
| equation_id | `uint32` | Flow 实际使用的方程实例 |
| offset | `T128` | 在 reference_event_id 处，原 Flow 实际保留的延续偏移 |

事件中的 `event_observer_flow_id` 对应事件点求值，`outgoing_flow_id` 对应下一事件前的区间求值。两者可以引用同一条传播记录。

## 12. 结束段

JSON 对象。

| 字段 | 格式 | 内容 |
|---|---|---|
| status | 字符串 | `COMPLETED、STOPPED_ERROR、STOPPED_UNRESOLVED` |
| last_event_id | `uint64` | 最后有效事件；其时间为实际终止时间 |
| diagnostic | 对象或 `null` | 终止诊断 |

## 13. 诊断日志段

UTF-8 JSONL。保存事务、控制器调用、联合事件详情及数值诊断。段头记录压缩方式和原文 SHA256。
