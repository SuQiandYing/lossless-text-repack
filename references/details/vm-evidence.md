> **完整规格，不是摘要。** 保留对应原章节、布局、代码和验收；仅登记的技术错误被校订。
> [章节/保全清单](../PRESERVATION.md)；[当前CLI与schema](../validation.md)。历史实测数字是原文案例，非本次重测。

## 1. VM 分析与理解深度申报

字节码反汇编前调查目标 VM 并产出 `vm_analysis.md`，作为证据台账；源字节仍是保真基准。
纯数据资源做结构分析，不伪造 VM。记录体系结构、指令编码、大小端、对齐、定长/变长和边界依据。

### 1.1 Opcode 字典

每条至少：`opcode`、`byte_pattern`+`mask`、`length`（定长值或变长计算规则）、`operand_schema`
（`imm8`/`imm16`/`strref`/`rel_offset`/`reg`）、`sub_opcode`（位置 + 全部合法子码语义）、
`variants`（同主码因操作数格式而语义不同时的全部变体及切换条件）、`evidence_refs`、`confidence`。

变长指令必须明确边界判定依据。子码必须全部枚举并路由到正确解释器，**不得当无关数据丢弃**。

### 1.2 decode_tier

较高等级须具备相应边界与语义证据；非 VM 数据可由结构字段证明 T2，不伪造定长 cell。
每区记可追溯证据，优先独立交叉验证，至少一条 observed/derived（T0 可无语义证据）；缺交叉证据明示。

| Tier | 已证明 | 必须保存 | 不得声称 |
|---|---|---|---|
| T0 `byte-span` | 区间边界与原始字节 | `start,end,raw_sha256,status` | 任何内部结构 |
| T1 `cell-stream` | 定长单元切分 | `cell_size,cell_count,endianness` | 单元语义、指令边界 |
| T2 `anchor-resolved` | 锚点已识别定位 | `anchor_kind,pattern+mask,offsets,operand_slots` | 锚点间的指令边界 |
| T3 `instruction-stream` | 完整指令边界，无缝无重叠 | `offset,size,raw_bytes,opcode,variant,operands` | 可达性、跳转语义 |
| T4 `semantic-cfg` | 基本块、跳转目标、调用图、栈效应 | `labels,targets,basic_blocks,cfg_edges` | 运行时行为等价 |

没有 `T1-partial`。切分或锚点解析不完整就降一级，剩余字节记 `unknown_opaque_block` 并在证书中
单列。

**T1 不是「猜它 4 字节一组」。** 两条独立证据从下列取：长度对 `cell_size` 整除且不整除即解析
失败（不得截断或补齐）；已知锚点值只出现在对齐位置；宿主以该步长读取；引用键只在对齐位置命中。
T1 已足以逐字节往返——每个 cell 原样写回即恢复原流，是合法交付物。

### 1.3 能力矩阵

允许申报的能力由本次操作**影响闭包**的区域与依赖证据决定，不由无关区域的最低 tier 否决：

| 能力 | 最低 tier | 附加前置 |
|---|---|---|
| 覆盖证书 + `byte_coverage=1.0` | T0 | 每段 `raw_sha256` 可从源复算 |
| 零编辑逐字节往返 | T0 | 全部原始字节可原样重放 |
| 文本发现与双行文件导出 | T2 | 来源为已解析结构或已证明的引用连接 |
| `in_place` 回封（等长） | T2 | 目标编码字节数 ≤ 原槽容量 |
| `pointer-rewrite` 回封（变长） | T2 | 全部引用槽已定位并经独立约束二次验证 |
| `full-layout` 重排 | 数据 T2 / 指令布局 T3 | 全部指针/跳转/表容量/校验依赖已解析 |
| 控制流改写、指令插删 | T4 | 影响闭包无 `unresolved` |

反向仍是硬规则：**影响闭包证据不足即不得执行能力。** 数据重排需 T2 结构证据；
指令布局需 T3，控制流修改/指令增删需 T4。说明缺项，不以策略回退掩盖未知依赖。

### 1.4 未定义 Opcode：排查后降级

遇到 `vm_analysis.md` 未记录的疑似操作码，按序排查：

1. 回溯宿主可执行文件，查找该字节序列的直接处理逻辑。
2. 检查邻近指令边界是否因长度误判产生连锁偏移——当前「opcode」可能实为前一条指令操作数的一部分。
3. 修正定义回写 `vm_analysis.md`，重跑全量反汇编。

三步都不成立时：**回溯到最后一条已验证指令，记录并降级；不猜测后继续，也不判定案件失败。**

```text
tier_blocked_at: {attempted: "T3", settled: "T2", offset: 0x1A40,
                  last_verified_instruction_offset: 0x1A2C, reason: "UNDEFINED_OPCODE"}
```

`tier_blocked` 不为空**不影响**严格成功。指令对象只存在于 T3+ 区域；T1/T2 用 cell 与锚点记录——
**不得**为填满指令表把 cell 伪装成单字长度的「指令」。

### 1.5 跳转标签化

跳转/条件跳转/调用/返回都提取解析后的目标，在 asm 中生成符号标签（`loc_00001200`），指令引用
标签而非硬编码偏移。文档中明确偏移基准（相对指令起始 / 指令末尾 / PC）与地址空间范围。变长文本
重写导致指令流长度变化时**必须通过标签重定位**。

### 1.6 窗口常量必须显式有据

前瞻长度、块最大跨度、扫描窗口是**方言参数**。每个在 `opcodelist.py` 中有名字、带 `evidence`
（实测最大跨度加余量，记录实测值）、带 `on_exceed`（`stop` 放弃候选 / `blocked` 需更多证据）。
**不得静默截断后继续。** 触达上限次数写 `window_hits.json`——不为零说明可能正在丢弃真实结构，
必须暴露。优先用结构终止条件（显式开/闭调用）替代固定窗口。

---

